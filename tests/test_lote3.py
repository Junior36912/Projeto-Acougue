"""Testes de regressão do terceiro lote de correções (PROBLEMAS_E_MELHORIAS.md).

Itens: BUG-26, BUG-17, BUG-20, NEG-10, NEG-11, REL-01, SEC-04, SEC-06, INF-01,
UI-04, DB-02, CODE-01, TEST-02. Cada teste cita o ID do item que protege.
"""
import ast
import collections
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from PIL import Image

import app as modulo_app
from app_logging import registrar_log
from banco_dados import (
    atualizar_produto, create_produto, create_user, fetch_vendas_prazo, get_db_connection,
    get_produto_by_id, init_db, update_fornecedor, update_produto, update_user, update_venda,
)
from test_criticos import criar_banco_antigo, criar_gerente, criar_produto, imagem_png, logar, vender

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOJE = date.today().isoformat()


def texto(resposta):
    return resposta.get_data(as_text=True)


def consulta(sql, *params):
    with get_db_connection() as conn:
        return conn.execute(sql, params).fetchall()


def criar_fornecedor_direto(nome='Frigorífico', cnpj='12.345.678/0001-99', endereco='Rua A, 1'):
    with get_db_connection() as conn:
        cursor = conn.execute("INSERT INTO fornecedores (nome, cnpj, contato, endereco) VALUES (?, ?, ?, ?)",
                              (nome, cnpj, '(11) 99999-0000', endereco))
        conn.commit()
        return cursor.lastrowid


@pytest.fixture
def fuso(monkeypatch):
    """Troca o fuso do processo (Python e SQLite) e restaura no fim."""
    original = os.environ.get('TZ')

    def aplicar(nome):
        os.environ['TZ'] = nome
        time.tzset()
    yield aplicar
    if original is None:
        os.environ.pop('TZ', None)
    else:
        os.environ['TZ'] = original
    time.tzset()


@pytest.fixture
def data_local_diferente_da_utc(fuso):
    """Fuso em que, agora, a data local não é a data UTC — como no Brasil entre 21h e 24h."""
    fuso('Etc/GMT-14' if datetime.now(timezone.utc).hour >= 12 else 'Etc/GMT+12')  # UTC+14 / UTC-12
    assert datetime.now().date() != datetime.now(timezone.utc).date()


# ---------------------------------------------------------------- BUG-26

def test_bug26_edicao_limpa_campos_opcionais(client):
    logar(client, criar_gerente())
    fornecedor_id = criar_fornecedor_direto()
    produto_id = create_produto('Picanha', 'Maturada', 'BOI', 69.9, 5, codigo_barras='789123',
                                fornecedor_id=fornecedor_id, data_validade='2030-01-01', tipo_venda='quilo')
    dados = {'nome': 'Picanha', 'categoria': 'BOI', 'preco': '69.90', 'quantidade': '5', 'tipo_venda': 'quilo',
             'estoque_minimo': '', 'codigo_barras': '', 'fornecedor_id': '', 'data_validade': '', 'descricao': ''}
    assert client.post(f'/produtos/editar/{produto_id}', data=dados).status_code == 302
    produto = get_produto_by_id(produto_id)
    assert produto['codigo_barras'] is None
    assert produto['fornecedor_id'] is None
    assert produto['data_validade'] is None
    assert produto['descricao'] is None


def test_bug26_campo_ausente_mantem_o_valor(app):
    produto_id = create_produto('Picanha', '', 'BOI', 69.9, 5, codigo_barras='789123', tipo_venda='quilo')
    with app.app_context():
        atualizar_produto(produto_id, {'nome': 'Picanha', 'preco': '70', 'quantidade': '4'}, None)
    produto = get_produto_by_id(produto_id)
    assert produto['codigo_barras'] == '789123' and produto['preco'] == 70


# ---------------------------------------------------------------- BUG-17

@pytest.mark.parametrize('cnpj, valido', [
    ('12.345.678/0001-95', True), ('11.222.333/0001-81', True), ('11222333000181', True),
    ('12.345.678/0001-99', False), ('11.111.111/1111-11', False), ('12345678', False), ('', False),
])
def test_bug17_validar_cnpj(cnpj, valido):
    assert modulo_app.validar_cnpj(cnpj) is valido


def test_bug17_cadastro_padroniza_e_valida(client):
    logar(client, criar_gerente())
    resposta = client.post('/fornecedores/novo', data={
        'nome': '  Frigorífico Boi Bom  ', 'cnpj': '11222333000181',
        'contato': 'vendas@boibom.com.br', 'endereco': '  Rua das Carnes, 10  '})
    assert resposta.status_code == 302
    fornecedor = consulta('SELECT * FROM fornecedores')[0]
    assert fornecedor['nome'] == 'Frigorífico Boi Bom'
    assert fornecedor['cnpj'] == '11.222.333/0001-81'
    assert fornecedor['contato'] == 'vendas@boibom.com.br'   # e-mail aceito como contato
    assert fornecedor['endereco'] == 'Rua das Carnes, 10'

    html = texto(client.post('/fornecedores/novo', data={
        'nome': 'Outro', 'cnpj': '12.345.678/0001-99', 'contato': '11 99999', 'endereco': ''}))
    assert 'CNPJ inválido' in html
    assert len(consulta('SELECT * FROM fornecedores')) == 1


def test_bug17_editar_nao_corrompe_endereco_nem_trava_cnpj_antigo(client):
    logar(client, criar_gerente())
    fornecedor_id = criar_fornecedor_direto(cnpj='12.345.678/0001-99', endereco='Av. das Carnes, 456')
    html = texto(client.get(f'/fornecedores/editar/{fornecedor_id}'))
    assert '>Av. das Carnes, 456</textarea>' in html   # sem espaços e quebras em volta
    assert 'padEnd' not in html
    assert 'for="cnpj"' in html and 'for="endereco"' in html

    # o navegador reenvia a tela como veio: salvar duas vezes não altera nada
    dados = {'nome': 'Frigorífico', 'cnpj': '12.345.678/0001-99', 'contato': '(11) 99999-0000',
             'endereco': 'Av. das Carnes, 456'}
    for _ in range(2):
        assert client.post(f'/fornecedores/editar/{fornecedor_id}', data=dados).status_code == 302
    fornecedor = consulta('SELECT * FROM fornecedores WHERE id = ?', fornecedor_id)[0]
    assert fornecedor['endereco'] == 'Av. das Carnes, 456'
    assert fornecedor['cnpj'] == '12.345.678/0001-99'   # CNPJ antigo mantido é aceito

    html = texto(client.post(f'/fornecedores/editar/{fornecedor_id}', data=dict(dados, cnpj='11.111.111/1111-11')))
    assert 'CNPJ inválido' in html


# ---------------------------------------------------------------- BUG-20 / NEG-10

@pytest.mark.parametrize('valor, formato, esperado', [
    ('2025-05-14 16:12:02.682109', '%d/%m/%Y %H:%M', '14/05/2025 16:12'),
    ('2025-05-29 08:05:00', '%H:%M', '08:05'),
    ('2025-05-29', '%d/%m/%Y %H:%M', '29/05/2025'),
    ('2025-05-29', '%H:%M', '—'),
    (None, '%d/%m/%Y', ''),
])
def test_bug20_formatar_datas_de_qualquer_formato(valor, formato, esperado):
    assert modulo_app.format_datetime(valor, formato) == esperado


def test_bug20_vendas_a_prazo_com_data_em_microssegundos(client):
    user_id = criar_gerente()
    logar(client, user_id)
    with get_db_connection() as conn:
        conn.execute("INSERT INTO vendas (id, data, total, metodo_pagamento, usuario_id, status_pagamento, "
                     "data_vencimento, cliente_nome) VALUES ('V1', '2025-05-14 16:12:02.682109', 10, "
                     "'pagamento_prazo', ?, 'pendente', '2025-06-14', 'Ana')", (user_id,))
        conn.commit()
    vendas = fetch_vendas_prazo()[0]
    assert vendas[0]['data'] == datetime(2025, 5, 14, 16, 12, 2, 682109)
    html = texto(client.get('/vendas/listar_vendas_prazo'))
    assert '14/05/2025' in html and '16:12' in html


def test_neg10_venda_de_hoje_guarda_a_hora(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    venda_id = vender(client, [{'id': produto_id, 'quantidade': 1}]).get_json()['venda_id']
    gravada = consulta('SELECT data FROM vendas WHERE id = ?', venda_id)[0][0]
    assert re.fullmatch(rf'{datetime.now().date().isoformat()} \d\d:\d\d:\d\d', gravada)


def test_neg10_venda_retroativa_guarda_so_o_dia(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    venda_id = vender(client, [{'id': produto_id, 'quantidade': 1}], data_venda=ontem).get_json()['venda_id']
    assert consulta('SELECT data FROM vendas WHERE id = ?', venda_id)[0][0] == ontem


# ---------------------------------------------------------------- NEG-11

def test_neg11_dashboard_usa_a_data_local(client, data_local_diferente_da_utc):
    logar(client, criar_gerente())
    produto_id = criar_produto(preco=50, quantidade=10)
    resposta = vender(client, [{'id': produto_id, 'quantidade': 1}], nome_cliente='Cliente da Noite',
                      data_venda=datetime.now().date().isoformat())
    assert resposta.status_code == 200
    html = texto(client.get('/dashboard'))
    assert 'Cliente da Noite' in html
    assert 'Vendas de Hoje: R$ 50,00' in html


def test_neg11_logs_gravados_em_horario_local(db_path, data_local_diferente_da_utc):
    registrar_log(1, 'teste_fuso', 'INFO')
    gravado = consulta("SELECT timestamp FROM logs WHERE action = 'teste_fuso'")[0][0]
    assert gravado.startswith(datetime.now().date().isoformat())


def test_neg11_produto_que_vence_hoje_aparece_no_relatorio(client):
    logar(client, criar_gerente())
    create_produto('Linguiça', '', 'CONGELADOS', 20, 5, data_validade=date.today().isoformat())
    html = texto(client.get('/relatorios/estoque_validade'))
    assert 'Linguiça' in html


def test_neg11_migracao_converte_logs_antigos_para_hora_local(tmp_path, monkeypatch, fuso):
    fuso('America/Sao_Paulo')
    caminho = tmp_path / 'legado.db'
    criar_banco_antigo(caminho)
    conn = sqlite3.connect(caminho)
    conn.executescript("""
        CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER, action TEXT NOT NULL, level TEXT NOT NULL, details TEXT, ip_address TEXT, user_agent TEXT);
        INSERT INTO logs (timestamp, user_id, action, level) VALUES ('2025-06-08 13:10:24', 1, 'login', 'INFO');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()
    assert consulta('SELECT timestamp FROM logs')[0][0] == '2025-06-08 10:10:24'   # UTC-3
    init_db()   # rodar de novo não converte outra vez
    assert consulta('SELECT timestamp FROM logs')[0][0] == '2025-06-08 10:10:24'


# ---------------------------------------------------------------- REL-01

def test_rel01_contagens_nao_aparecem_como_dinheiro(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(preco=10, quantidade=20)
    for _ in range(3):
        vender(client, [{'id': produto_id, 'quantidade': 1}])
    html = texto(client.get('/relatorios/vendas_periodo'))
    assert '<th class="text-end">Vendas</th>' in html and 'Ticket médio' in html
    assert '<td class="text-end">3</td>' in html        # número de vendas
    assert 'R$ 3,00' not in html
    assert '<td class="text-end">R$ 30,00</td>' in html  # valor total


def test_rel01_estoque_em_kg_com_virgula_e_titulos_em_portugues(client):
    logar(client, criar_gerente())
    criar_produto('Alcatra', quantidade=2.357, estoque_minimo=5, tipo_venda='quilo')
    html = texto(client.get('/relatorios/estoque_nivel'))
    assert '<td class="text-end">2,357</td>' in html
    assert 'Estoque mínimo' in html
    html = texto(client.get('/relatorios/movimentacao_caixa'))
    assert 'Valor A Vista' not in html


def test_rel07_grafico_de_categorias_usa_json(client):
    logar(client, criar_gerente())
    produto_id = create_produto("Pão d'alho", '', "Açougue d'Ouro", 10, 10)
    vender(client, [{'id': produto_id, 'quantidade': 1}])
    html = texto(client.get('/relatorios/vendas_categorias'))
    assert "name: 'Açougue" not in html   # antes: interpolado como texto dentro do JS
    assert '"A\\u00e7ougue d\\u0027Ouro"' in html or '"Açougue d\\u0027Ouro"' in html


# ---------------------------------------------------------------- SEC-04

def tentar(client, username, senha):
    return client.post('/login', data={'username': username, 'password': senha})


def test_sec04_bloqueia_apos_5_erros_e_libera_depois(client):
    create_user('maria', 'maria@teste.com', 'senha-certa', 'gerente')
    for _ in range(5):
        assert 'Credenciais inválidas' in texto(tentar(client, 'maria', 'errada'))
    resposta = tentar(client, 'maria', 'senha-certa')
    assert resposta.status_code == 429
    assert 'Muitas tentativas' in texto(resposta)
    assert consulta("SELECT COUNT(*) FROM logs WHERE action = 'login_falha'")[0][0] == 5

    # passados 15 minutos, libera
    with get_db_connection() as conn:
        conn.execute("UPDATE login_falhas SET momento = datetime(momento, '-16 minutes')")
        conn.commit()
    assert tentar(client, 'maria', 'senha-certa').status_code == 302
    assert consulta('SELECT COUNT(*) FROM login_falhas')[0][0] == 0   # sucesso zera os erros


def test_sec04_bloqueio_e_por_usuario(client):
    create_user('maria', 'maria@teste.com', 'senha-certa', 'gerente')
    create_user('joao', 'joao@teste.com', 'senha-joao', 'funcionario')
    for _ in range(5):
        tentar(client, 'maria', 'errada')
    assert tentar(client, 'joao', 'senha-joao').status_code == 302


def test_sec04_muitos_erros_do_mesmo_ip_bloqueiam_qualquer_usuario(client):
    create_user('joao', 'joao@teste.com', 'senha-joao', 'funcionario')
    for i in range(20):
        tentar(client, f'usuario{i}', 'errada')
    assert tentar(client, 'joao', 'senha-joao').status_code == 429


def test_sec04_cookie_de_sessao_com_samesite_e_validade(client):
    create_user('maria', 'maria@teste.com', 'senha-certa', 'gerente')
    resposta = tentar(client, 'maria', 'senha-certa')
    cookie = resposta.headers['Set-Cookie']
    assert 'SameSite=Lax' in cookie and 'HttpOnly' in cookie and 'Expires=' in cookie


# ---------------------------------------------------------------- SEC-06

@pytest.mark.parametrize('funcao, chave', [
    (update_user, "role = 'gerente', username"),
    (update_fornecedor, 'nome = nome; DROP TABLE vendas; --'),
    (update_venda, 'total = 0 WHERE 1=1; --'),
    (update_produto, 'preco = 0, nome'),
])
def test_sec06_colunas_fora_da_lista_sao_recusadas(db_path, funcao, chave):
    with pytest.raises(ValueError, match='inválido'):
        funcao(1, **{chave: 'x'})


def test_sec06_colunas_validas_continuam_funcionando(db_path):
    user_id = criar_gerente()
    update_user(user_id, email='novo@teste.com', password='outra-senha')
    assert consulta('SELECT email FROM users WHERE id = ?', user_id)[0][0] == 'novo@teste.com'


# ---------------------------------------------------------------- INF-01

# Nome do import -> nome do pacote no requirements
_PACOTES = {'flask': 'flask', 'flask_wtf': 'flask-wtf', 'werkzeug': 'werkzeug', 'jinja2': 'jinja2',
            'apscheduler': 'apscheduler', 'reportlab': 'reportlab', 'PIL': 'pillow', 'wtforms': 'wtforms'}


def test_inf01_requirements_em_utf8_e_enxuto():
    bruto = open(os.path.join(RAIZ, 'requirements.txt'), 'rb').read()
    assert not bruto.startswith((b'\xff\xfe', b'\xfe\xff', b'\xef\xbb\xbf'))   # sem BOM / UTF-16
    linhas = [l.strip() for l in bruto.decode('utf-8').splitlines() if l.strip() and not l.startswith('#')]
    pacotes = {l.split('==')[0].lower() for l in linhas}
    assert all('==' in l for l in linhas)
    assert not pacotes & {'pygame', 'moviepy', 'pytube', 'pywebview', 'pythonnet', 'pyinstaller', 'numpy'}
    assert len(pacotes) <= 10


def test_inf01_todo_import_externo_esta_no_requirements():
    requisitos = {l.split('==')[0].strip().lower()
                  for l in open(os.path.join(RAIZ, 'requirements.txt'), encoding='utf-8')
                  if l.strip() and not l.startswith('#')}
    locais = {os.path.splitext(n)[0] for n in os.listdir(RAIZ) if n.endswith('.py')}
    externos = set()
    for nome in os.listdir(RAIZ):
        if not nome.endswith('.py'):
            continue
        arvore = ast.parse(open(os.path.join(RAIZ, nome), encoding='utf-8').read())
        for no in ast.walk(arvore):
            modulos = ([a.name for a in no.names] if isinstance(no, ast.Import)
                       else [no.module] if isinstance(no, ast.ImportFrom) and no.module and no.level == 0 else [])
            for modulo in modulos:
                raiz = modulo.split('.')[0]
                if raiz not in sys.stdlib_module_names and raiz not in locais:
                    externos.add(raiz)
    faltando = {m for m in externos if _PACOTES.get(m, m).lower() not in requisitos}
    assert faltando == set()


# ---------------------------------------------------------------- UI-04 / UI-05

def criar_foto_grande(pasta, nome='grande.png', tamanho=(2000, 1500)):
    caminho = os.path.join(pasta, nome)
    Image.new('RGB', tamanho, (180, 30, 30)).save(caminho)
    return caminho


def test_ui04_upload_gera_miniatura_pequena(client, app):
    logar(client, criar_gerente())
    import io
    buffer = io.BytesIO()
    Image.new('RGB', (2000, 1500), (180, 30, 30)).save(buffer, 'PNG')
    buffer.seek(0)
    dados = {'nome': 'Picanha', 'descricao': '', 'categoria': 'BOI', 'preco': '70', 'quantidade': '3',
             'tipo_venda': 'quilo', 'estoque_minimo': '', 'codigo_barras': '', 'fornecedor_id': '',
             'data_validade': '', 'foto': (buffer, 'picanha.png')}
    assert client.post('/produtos/novo', data=dados, content_type='multipart/form-data').status_code == 302
    foto = consulta("SELECT foto FROM produtos")[0][0]
    miniatura = os.path.join(app.config['UPLOAD_FOLDER'], 'miniaturas', foto + '.webp')
    with Image.open(miniatura) as imagem:
        assert max(imagem.size) <= 320
    assert os.path.getsize(miniatura) < os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], foto)) / 5

    for pagina in ('/produtos', '/vendas/nova'):
        assert f'src="/static/uploads/produtos/miniaturas/{foto}.webp"' in texto(client.get(pagina))


def test_ui04_sem_miniatura_usa_a_foto_original(client, app):
    logar(client, criar_gerente())
    criar_produto(foto='sem-miniatura.png')
    assert 'src="/static/uploads/produtos/sem-miniatura.png"' in texto(client.get('/produtos'))


def test_ui04_miniaturas_das_fotos_existentes_e_remocao(client, app):
    pasta = app.config['UPLOAD_FOLDER']
    criar_foto_grande(pasta, 'a.png')
    criar_foto_grande(pasta, 'a.webp')   # mesmo nome-base: miniaturas não podem colidir
    assert modulo_app.gerar_miniaturas_faltantes(pasta) == 2
    assert modulo_app.gerar_miniaturas_faltantes(pasta) == 0   # já existem

    logar(client, criar_gerente())
    produto_id = criar_produto(foto='a.png')
    client.post(f'/produtos/excluir/{produto_id}')
    assert not os.path.exists(os.path.join(pasta, 'miniaturas', 'a.png.webp'))
    assert os.path.exists(os.path.join(pasta, 'miniaturas', 'a.webp.webp'))


def test_ui04_backup_nao_inclui_miniaturas(app):
    import zipfile
    pasta = app.config['UPLOAD_FOLDER']
    criar_foto_grande(pasta, 'b.png', (100, 100))
    modulo_app.gerar_miniaturas_faltantes(pasta)
    with app.app_context():
        criados = modulo_app.backup_db()
    fotos = [n for n in criados if n.startswith(modulo_app.PREFIXO_BACKUP_FOTOS)][0]
    with zipfile.ZipFile(os.path.join(app.config['BACKUP_FOLDER'], fotos)) as zipf:
        assert zipf.namelist() == ['produtos/b.png']


def test_ui05_cabecalho_usa_logo_otimizado(client):
    html = texto(client.get('/login'))
    assert 'img/logo-acougue-200.png' in html and 'img/logo-acougue.png"' not in html
    assert os.path.getsize(os.path.join(RAIZ, 'static', 'img', 'logo-acougue-200.png')) < 100 * 1024


# ---------------------------------------------------------------- DB-02

INDICES_ESPERADOS = {'idx_vendas_data', 'idx_vendas_metodo_status', 'idx_vendas_usuario',
                     'idx_venda_itens_venda', 'idx_venda_itens_produto', 'idx_produtos_categoria',
                     'idx_produtos_nome', 'idx_logs_timestamp', 'idx_login_falhas_usuario', 'idx_login_falhas_ip'}


def indices():
    return {r[0] for r in consulta("SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'")}


def test_db02_indices_em_banco_novo(db_path):
    assert INDICES_ESPERADOS <= indices()


def test_db02_indices_depois_de_migrar_banco_antigo(tmp_path, monkeypatch):
    caminho = tmp_path / 'legado.db'
    criar_banco_antigo(caminho)
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()
    assert INDICES_ESPERADOS <= indices()


def test_db02_consulta_do_dashboard_usa_indice(db_path):
    plano = ' '.join(r[3] for r in consulta(
        'EXPLAIN QUERY PLAN SELECT * FROM vendas v WHERE v.data >= ? AND v.data < ?', '2026-01-01', '2026-01-02'))
    assert 'idx_vendas_data' in plano


# ---------------------------------------------------------------- CODE-01 / TEST-02

@pytest.mark.parametrize('arquivo', ['banco_dados.py', 'app.py', 'gerador_pdf.py', 'imagens.py'])
def test_code01_sem_funcoes_duplicadas(arquivo):
    arvore = ast.parse(open(os.path.join(RAIZ, arquivo), encoding='utf-8').read())
    nomes = [n.name for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert [n for n, c in collections.Counter(nomes).items() if c > 1] == []


def test_test02_todo_arquivo_de_teste_e_coletado():
    pasta = os.path.join(RAIZ, 'tests')
    for nome in os.listdir(pasta):
        if nome.endswith('.py'):
            assert nome == 'conftest.py' or re.fullmatch(r'test_\w+\.py', nome), nome


# ---------------------------------------------------------------- CODE-03

@pytest.mark.parametrize('arquivo', ['app.py', 'banco_dados.py', 'app_logging.py', 'gerador_pdf.py',
                                     'decorators.py', 'imagens.py', 'popular_banco.py'])
def test_code03_sem_imports_sem_uso_nem_nomes_indefinidos(arquivo):
    """Roda o pyflakes (requirements-dev.txt). Teria pegado o BUG-01, os imports apagados."""
    api = pytest.importorskip('pyflakes.api')
    from pyflakes.reporter import Reporter
    import io
    avisos = io.StringIO()
    caminho = os.path.join(RAIZ, arquivo)
    api.check(open(caminho, encoding='utf-8').read(), caminho, Reporter(avisos, avisos))
    assert avisos.getvalue() == ''
