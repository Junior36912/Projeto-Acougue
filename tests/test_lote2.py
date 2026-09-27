"""Testes de regressão do segundo lote de correções (PROBLEMAS_E_MELHORIAS.md).

Itens: BUG-07, BUG-08, NEG-07, REL-03, SEC-05, BUG-14, NEG-12, SEC-03, REL-02,
NEG-05, NEG-06, BUG-19, UI-01, PERF-01 (e os vizinhos BUG-28 e BUG-29).
Cada teste cita o ID do item que protege.
"""
import glob
import io
import os
import re
import sqlite3
import subprocess
import time
import zipfile
from datetime import date, datetime, timedelta

import pytest

import app as modulo_app
from banco_dados import (
    arredondar_dinheiro, create_produto, create_user, get_db_connection,
    get_produto_by_id, init_db,
)
from test_criticos import criar_banco_antigo, criar_gerente, criar_produto, logar, vender

HOJE = date.today().isoformat()
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def consulta(sql, *params):
    with get_db_connection() as conn:
        return conn.execute(sql, params).fetchall()


def vender_fiado(client, itens, vencimento=None):
    vencimento = vencimento or (date.today() + timedelta(days=10)).isoformat()
    return vender(client, itens, metodo_pagamento='pagamento_prazo',
                  data_vencimento=vencimento, nome_cliente='Cliente Fiado')


def texto(resposta):
    return resposta.get_data(as_text=True)


# ---------------------------------------------------------------- BUG-07 / BUG-08

def test_bug07_rota_duplicada_de_pagamento_removida(client):
    logar(client, criar_gerente())
    assert client.post('/vendas/pagamento_prazo/pagar/V1').status_code == 404


def test_bug08_pagar_fiado_registra_pagamento_e_mostra_sucesso(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    venda_id = vender_fiado(client, [{'id': produto_id, 'quantidade': 2}]).get_json()['venda_id']

    resposta = client.post(f'/vendas/listar_vendas_prazo/pagar/{venda_id}', follow_redirects=True)
    assert resposta.status_code == 200
    html = texto(resposta)
    assert html.count(f'Pagamento da venda {venda_id} registrado') == 1
    assert 'não é a prazo' not in html
    venda = consulta('SELECT status_pagamento, data_pagamento FROM vendas WHERE id = ?', venda_id)[0]
    assert venda['status_pagamento'] == 'pago'
    assert venda['data_pagamento'].startswith(HOJE)


def test_bug08_pagar_de_novo_ou_venda_a_vista_informa_erro(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    fiado = vender_fiado(client, [{'id': produto_id, 'quantidade': 1}]).get_json()['venda_id']
    a_vista = vender(client, [{'id': produto_id, 'quantidade': 1}]).get_json()['venda_id']
    client.post(f'/vendas/listar_vendas_prazo/pagar/{fiado}')

    for venda_id in (fiado, a_vista, 'NAO-EXISTE'):
        html = texto(client.post(f'/vendas/listar_vendas_prazo/pagar/{venda_id}', follow_redirects=True))
        assert 'não é a prazo ou já estava paga' in html
    # a venda à vista continua como estava
    assert consulta('SELECT metodo_pagamento FROM vendas WHERE id = ?', a_vista)[0][0] == 'pix'


# ---------------------------------------------------------------- NEG-07

def test_neg07_tela_de_venda_envia_valores_fixos(client):
    logar(client, criar_gerente())
    html = texto(client.get('/vendas/nova'))
    for valor in ('dinheiro', 'debito', 'credito', 'pix', 'pagamento_prazo'):
        assert f'<option value="{valor}">' in html


@pytest.mark.parametrize('enviado, gravado', [
    ('dinheiro', 'dinheiro'), ('Dinheiro', 'dinheiro'), ('PIX', 'pix'), ('debito', 'debito'),
    ('Cartão Crédito', 'credito'),
])
def test_neg07_forma_de_pagamento_gravada_padronizada(client, enviado, gravado):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    resposta = vender(client, [{'id': produto_id, 'quantidade': 1}], metodo_pagamento=enviado)
    assert resposta.status_code == 200
    assert consulta('SELECT metodo_pagamento FROM vendas')[0][0] == gravado


def test_neg07_forma_de_pagamento_desconhecida_rejeitada(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    resposta = vender(client, [{'id': produto_id, 'quantidade': 1}], metodo_pagamento='Cheque')
    assert resposta.status_code == 400
    assert 'Forma de pagamento inválida' in resposta.get_json()['error']
    assert get_produto_by_id(produto_id)['quantidade'] == 10


def test_neg07_relatorio_mostra_nome_da_forma(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    vender(client, [{'id': produto_id, 'quantidade': 1}], metodo_pagamento='debito')
    assert 'Cartão de Débito' in texto(client.get('/relatorios/vendas_totais'))


# ---------------------------------------------------------------- REL-03

def test_rel03_movimentacao_de_caixa_separa_a_vista_fiado_e_recebimento(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(preco=50.0, quantidade=10)
    vender(client, [{'id': produto_id, 'quantidade': 2}])             # R$ 100 à vista
    fiado = vender_fiado(client, [{'id': produto_id, 'quantidade': 1}]).get_json()['venda_id']  # R$ 50
    vender_fiado(client, [{'id': produto_id, 'quantidade': 1}])       # R$ 50, continua pendente
    client.post(f'/vendas/listar_vendas_prazo/pagar/{fiado}')

    linhas = consulta(modulo_app.SQL_MOVIMENTACAO_CAIXA)
    assert len(linhas) == 1
    dia = dict(linhas[0])
    assert dia['data'] == HOJE
    assert dia['valor_a_vista'] == 100
    assert dia['valor_fiado_recebido'] == 50
    assert dia['total_entradas'] == 150
    assert dia['valor_vendido_a_prazo'] == 100

    html = texto(client.get('/relatorios/movimentacao_caixa'))
    assert 'R$ 150,00' in html and 'R$ 100,00' in html


def test_rel03_pdf_gerado_com_nova_movimentacao(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    vender(client, [{'id': produto_id, 'quantidade': 1}])
    resposta = client.get('/relatorios/gerar_pdf')
    assert resposta.status_code == 200
    assert resposta.data.startswith(b'%PDF')


# ---------------------------------------------------------------- SEC-05

def test_sec05_bancos_fora_do_git():
    with open(os.path.join(RAIZ, '.gitignore'), encoding='utf-8') as arquivo:
        assert '*.db' in arquivo.read().split()
    if not os.path.isdir(os.path.join(RAIZ, '.git')):
        pytest.skip('cópia sem repositório git')
    versionados = subprocess.run(['git', 'ls-files', '--cached', '*.db'], cwd=RAIZ,
                                 capture_output=True, text=True, check=True).stdout.split()
    assert versionados == []


def entrar(client, username, senha):
    return client.post('/login', data={'username': username, 'password': senha})


def test_sec05_senha_padrao_obriga_troca(client):
    create_user('admin', 'admin@teste.com', 'admin123', 'gerente')
    resposta = entrar(client, 'admin', 'admin123')
    assert resposta.headers['Location'].endswith('/conta/senha')
    # enquanto não trocar, qualquer página leva para a troca de senha
    assert client.get('/produtos').headers['Location'].endswith('/conta/senha')

    erros = [
        ({'senha_atual': 'errada', 'nova_senha': 'nova-senha-1', 'confirmacao': 'nova-senha-1'}, 'Senha atual incorreta'),
        ({'senha_atual': 'admin123', 'nova_senha': 'admin123', 'confirmacao': 'admin123'}, 'diferente'),
        ({'senha_atual': 'admin123', 'nova_senha': '123', 'confirmacao': '123'}, 'pelo menos 6'),
        ({'senha_atual': 'admin123', 'nova_senha': 'nova-senha-1', 'confirmacao': 'outra'}, 'não confere'),
    ]
    for dados, mensagem in erros:
        assert mensagem in texto(client.post('/conta/senha', data=dados))

    resposta = client.post('/conta/senha', data={
        'senha_atual': 'admin123', 'nova_senha': 'nova-senha-1', 'confirmacao': 'nova-senha-1'})
    assert resposta.status_code == 302
    assert client.get('/produtos').status_code == 200

    client.get('/logout')
    assert 'Credenciais inválidas' in texto(entrar(client, 'admin', 'admin123'))
    assert entrar(client, 'admin', 'nova-senha-1').headers['Location'].endswith('/')


def test_sec05_senha_normal_nao_obriga_troca(client):
    create_user('maria', 'maria@teste.com', 'senha-forte', 'gerente')
    assert entrar(client, 'maria', 'senha-forte').headers['Location'].endswith('/')
    assert client.get('/produtos').status_code == 200


# ---------------------------------------------------------------- BUG-14 / BUG-29

def test_bug14_editar_produto_mantem_a_categoria(client):
    logar(client, criar_gerente())
    produto_id = create_produto('Pepsi 2L', '', 'BEBIDAS', 9.5, 10)
    html = texto(client.get(f'/produtos/editar/{produto_id}'))
    assert 'id="categoria" name="categoria" list="lista-categorias"' in html
    assert 'value="BEBIDAS"' in html
    # nenhum campo vazio é preenchido com o texto "None"
    assert 'value="None"' not in html and '>None</textarea>' not in html

    # o navegador reenvia o formulário como veio da tela
    dados = {'nome': 'Pepsi 2L', 'categoria': 'BEBIDAS', 'preco': '9.5', 'quantidade': '10',
             'estoque_minimo': '', 'codigo_barras': '', 'tipo_venda': 'unidade',
             'descricao': '', 'fornecedor_id': '', 'data_validade': ''}
    assert client.post(f'/produtos/editar/{produto_id}', data=dados).status_code == 302
    produto = get_produto_by_id(produto_id)
    assert produto['categoria'] == 'BEBIDAS'
    assert produto['codigo_barras'] is None


def test_bug14_formularios_sugerem_categorias_existentes(client):
    logar(client, criar_gerente())
    create_produto('Picanha', '', 'BOI', 60, 5)
    create_produto('Skol', '', 'BEBIDAS', 4, 5)
    for pagina in ('/produtos/novo', '/produtos/editar/1'):
        html = texto(client.get(pagina))
        assert '<option value="BOI">' in html and '<option value="BEBIDAS">' in html


def criar_banco_legado_completo(caminho):
    """Banco antigo com os dados problemáticos encontrados no acougue.db real."""
    criar_banco_antigo(caminho)
    conn = sqlite3.connect(caminho)
    conn.executescript('''
        INSERT INTO produtos (nome, categoria, preco, quantidade, descricao, codigo_barras)
            VALUES ('Bacon', 'Bovino', 30, 5.636, 'None', 'None');
        INSERT INTO produtos (nome, categoria, preco, quantidade, descricao) VALUES ('Pepsi 2L', 'Bovino', 10, 4, 'None');
        INSERT INTO produtos (nome, categoria, preco, quantidade) VALUES ('Picanha', 'Bovino', 69.9, 3);
        INSERT INTO produtos (nome, categoria, preco, quantidade) VALUES ('Heineken Original 250ml', 'BEBIDA', 6, 12);
        INSERT INTO produtos (nome, categoria, preco, quantidade) VALUES ('sdfghjk', 'Bovino', 1, 1);
        INSERT INTO produtos (nome, categoria, preco, quantidade) VALUES ('Alcatra', 'FRIOS', 40, 1);
        INSERT INTO vendas (id, total, metodo_pagamento, usuario_id, data) VALUES ('V2', 96.998, 'Dinheiro', 1, '2025-06-01');
        INSERT INTO vendas (id, total, metodo_pagamento, usuario_id, data) VALUES ('V3', 13.008, 'Cartão Débito', 1, '2025-06-01');
        INSERT INTO vendas (id, total, metodo_pagamento, usuario_id, status_pagamento, data_vencimento, data)
            VALUES ('V4', 30.008, 'pagamento_prazo', 1, 'pendente', '2025-07-01', '2025-06-01');
    ''')
    conn.commit()
    conn.close()


@pytest.fixture
def banco_legado(tmp_path, monkeypatch):
    caminho = tmp_path / 'legado.db'
    criar_banco_legado_completo(caminho)
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()
    return caminho


def test_bug14_migracao_restaura_categorias_trocadas(banco_legado):
    categorias = {r['nome']: r['categoria'] for r in consulta('SELECT nome, categoria FROM produtos')}
    assert categorias['Bacon'] == 'CONGELADOS'
    assert categorias['Pepsi 2L'] == 'BEBIDAS'
    assert categorias['Picanha'] == 'BOI'
    assert categorias['Heineken Original 250ml'] == 'BEBIDAS'
    assert categorias['sdfghjk'] == 'Bovino'   # sem correspondência: fica como estava
    assert categorias['Alcatra'] == 'FRIOS'    # só corrige o que o formulário antigo trocou


def test_bug29_migracao_limpa_textos_none(banco_legado):
    bacon = consulta("SELECT descricao, codigo_barras FROM produtos WHERE nome = 'Bacon'")[0]
    assert bacon['descricao'] is None and bacon['codigo_barras'] is None


def test_neg07_migracao_padroniza_formas_de_pagamento(banco_legado):
    formas = {r['id']: r['metodo_pagamento'] for r in consulta('SELECT id, metodo_pagamento FROM vendas')}
    assert formas == {'V1': 'pix', 'V2': 'dinheiro', 'V3': 'debito', 'V4': 'pagamento_prazo'}
    # à vista já pagas ganham data de pagamento; o fiado pendente não
    pagamentos = {r['id']: r['data_pagamento'] for r in consulta('SELECT id, data_pagamento FROM vendas')}
    assert pagamentos['V2'] == '2025-06-01' and pagamentos['V4'] is None


def test_neg06_migracao_arredonda_valores_em_centavos(banco_legado):
    totais = {r['id']: r['total'] for r in consulta('SELECT id, total FROM vendas')}
    assert totais['V2'] == 97.0 and totais['V3'] == 13.01 and totais['V4'] == 30.01


def test_neg05_migracao_usa_colunas_decimais_e_preserva_dados(banco_legado):
    with get_db_connection() as conn:
        tipos = {r['name']: r['type'] for r in conn.execute('PRAGMA table_info(produtos)')}
        assert tipos['quantidade'] == 'REAL' and tipos['estoque_minimo'] == 'REAL'
        tipos_itens = {r['name']: r['type'] for r in conn.execute('PRAGMA table_info(venda_itens)')}
        assert tipos_itens['quantidade'] == 'REAL'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute('SELECT COUNT(*) FROM produtos').fetchone()[0] == 8
        assert conn.execute('SELECT COUNT(*) FROM venda_itens').fetchone()[0] == 1
        # o trigger de updated_at voltou depois da recriação da tabela
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'trigger' "
                            "AND name = 'trg_update_produtos_updated_at'").fetchone()
    assert consulta("SELECT quantidade FROM produtos WHERE nome = 'Bacon'")[0][0] == 5.636


# ---------------------------------------------------------------- NEG-12 / SEC-03

def test_neg12_gerente_rebaixado_perde_acesso_na_hora(client):
    gerente = criar_gerente()
    criar_gerente('outro')
    logar(client, gerente)
    assert client.get('/produtos').status_code == 200
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET role = 'funcionario' WHERE id = ?", (gerente,))
        conn.commit()
    assert client.get('/produtos').status_code == 403


def test_neg12_usuario_desativado_e_deslogado(client):
    gerente = criar_gerente()
    logar(client, gerente)
    with get_db_connection() as conn:
        conn.execute('UPDATE users SET ativo = 0 WHERE id = ?', (gerente,))
        conn.commit()
    resposta = client.get('/vendas/nova')
    assert resposta.status_code == 302 and resposta.headers['Location'].endswith('/login')
    with client.session_transaction() as sessao:
        assert 'user_id' not in sessao


def test_neg12_gerente_nao_exclui_a_propria_conta(client):
    gerente = criar_gerente()
    criar_gerente('outro')
    logar(client, gerente)
    html = texto(client.post(f'/admin/usuarios/excluir/{gerente}', follow_redirects=True))
    assert 'não pode excluir a própria conta' in html
    assert consulta('SELECT ativo FROM users WHERE id = ?', gerente)[0][0] == 1


def test_sec03_funcionario_recebe_acesso_negado_sem_ser_deslogado(client):
    funcionario = create_user('caixa', 'caixa@teste.com', 'senha123', 'funcionario')
    logar(client, funcionario, role='funcionario')
    resposta = client.get('/produtos')
    assert resposta.status_code == 403
    assert 'Acesso restrito' in texto(resposta)
    assert client.get('/vendas/nova').status_code == 200  # continua logado


def test_sec03_menu_do_funcionario_so_mostra_o_que_ele_pode_usar(client):
    funcionario = create_user('caixa', 'caixa@teste.com', 'senha123', 'funcionario')
    logar(client, funcionario, role='funcionario')
    html = texto(client.get('/'))
    assert 'href="/produtos"' not in html and 'href="/vendas/listar_vendas_prazo"' not in html
    assert 'href="/vendas/nova"' in html


def test_bug24_tela_de_login_sem_menu(client):
    html = texto(client.get('/login'))
    assert 'href="/produtos"' not in html and 'href="/logout"' not in html


# ---------------------------------------------------------------- REL-02

RELATORIOS = ['vendas_totais', 'vendas_periodo', 'vendas_categorias', 'top_produtos',
              'estoque_nivel', 'estoque_validade', 'clientes_fieis', 'fornecedores_produtos',
              'movimentacao_caixa', 'comparativo']


@pytest.mark.parametrize('relatorio', RELATORIOS)
def test_rel02_parametros_invalidos_nao_derrubam_relatorio(client, relatorio):
    logar(client, criar_gerente())
    url = (f'/relatorios/{relatorio}?limit=abc&dias=xyz&start_date=abc'
           '&end_date=2020-99-99&periodo=zzz')
    assert client.get(url).status_code == 200


def test_rel02_limite_e_respeitado(client):
    logar(client, criar_gerente())
    for i in range(5):
        produto_id = criar_produto(f'Produto {i}', quantidade=10)
        vender(client, [{'id': produto_id, 'quantidade': 1}])
    html = texto(client.get('/relatorios/top_produtos?limit=2'))
    assert len(re.findall(r'<td>\s*Produto \d', html)) == 2
    assert client.get('/relatorios/top_produtos?limit=-5').status_code == 200


# ---------------------------------------------------------------- NEG-05

def cadastrar(client, **campos):
    dados = {'nome': 'Coxão Mole', 'descricao': '', 'categoria': 'BOI', 'preco': '39,90',
             'quantidade': '2,5', 'tipo_venda': 'quilo', 'estoque_minimo': '1.25',
             'codigo_barras': '', 'fornecedor_id': '', 'data_validade': ''}
    dados.update(campos)
    return client.post('/produtos/novo', data=dados)


def test_neg05_produto_por_quilo_aceita_estoque_fracionado(client):
    logar(client, criar_gerente())
    assert cadastrar(client).status_code == 302
    produto = dict(consulta("SELECT * FROM produtos WHERE nome = 'Coxão Mole'")[0])
    assert produto['quantidade'] == 2.5
    assert produto['estoque_minimo'] == 1.25
    assert produto['preco'] == 39.9

    dados = {'nome': 'Coxão Mole', 'categoria': 'BOI', 'preco': '39.90', 'quantidade': '18.235',
             'estoque_minimo': '2', 'tipo_venda': 'quilo', 'codigo_barras': '', 'descricao': '',
             'fornecedor_id': '', 'data_validade': ''}
    assert client.post(f"/produtos/editar/{produto['id']}", data=dados).status_code == 302
    assert get_produto_by_id(produto['id'])['quantidade'] == 18.235


def test_neg05_produto_por_unidade_so_aceita_inteiros(client):
    logar(client, criar_gerente())
    resposta = cadastrar(client, nome='Skol', tipo_venda='unidade', quantidade='2.5', estoque_minimo='')
    assert resposta.status_code == 200
    assert 'por unidade aceitam só números inteiros' in texto(resposta)
    assert consulta("SELECT COUNT(*) FROM produtos WHERE nome = 'Skol'")[0][0] == 0


def test_neg05_erro_de_validacao_mantem_o_formulario(client):
    logar(client, criar_gerente())
    html = texto(cadastrar(client, nome='Fraldinha', preco='abc'))
    assert 'Preço inválido' in html
    assert 'value="Fraldinha"' in html  # BUG-16: o que foi digitado não se perde


def test_neg05_formulario_permite_decimais(client):
    logar(client, criar_gerente())
    html = texto(client.get('/produtos/novo'))
    assert re.search(r'id="quantidade"[^>]*step="0.001"', html)


# ---------------------------------------------------------------- NEG-06

def test_neg06_arredondamento_em_centavos_meio_para_cima():
    assert arredondar_dinheiro(2.675) == 2.68       # round() do Python daria 2.67
    assert arredondar_dinheiro('96,998') == 97.0
    assert arredondar_dinheiro(0.125) == 0.13


def test_neg06_venda_por_quilo_grava_centavos(client):
    logar(client, criar_gerente())
    produto_id = criar_produto('Alcatra', preco=29.90, quantidade=10, tipo_venda='quilo')
    resposta = vender(client, [{'id': produto_id, 'quantidade': 0.333},
                               {'id': produto_id, 'quantidade': 0.335}])
    assert resposta.status_code == 200
    total = consulta('SELECT total FROM vendas')[0][0]
    # 0,333 kg x 29,90 = 9,9567 -> 9,96 ; 0,335 kg x 29,90 = 10,0165 -> 10,02
    assert total == 19.98
    assert get_produto_by_id(produto_id)['quantidade'] == 9.332


# ---------------------------------------------------------------- BUG-19

@pytest.mark.parametrize('acao', ['fornecedor', 'produto', 'usuario', 'observacao'])
def test_bug19_mensagem_aparece_uma_vez_apos_a_acao(client, acao):
    logar(client, criar_gerente())
    if acao == 'fornecedor':
        resposta = client.post('/fornecedores/novo', data={
            'nome': 'Frigorífico X', 'cnpj': '11.222.333/0001-81', 'contato': '(11) 90000-0000'},
            follow_redirects=True)
        esperado = 'Fornecedor &#34;Frigorífico X&#34; cadastrado.'
    elif acao == 'produto':
        resposta = cadastrar(client)
        resposta = client.get('/produtos')
        esperado = 'Produto &#34;Coxão Mole&#34; cadastrado.'
    elif acao == 'usuario':
        resposta = client.post('/admin/usuarios/novo', data={
            'username': 'caixa9', 'email': 'c9@teste.com', 'password': 'segredo1',
            'role': 'funcionario'}, follow_redirects=True)
        esperado = 'Usuário caixa9 criado com sucesso.'
    else:
        produto_id = criar_produto(quantidade=10)
        venda_id = vender_fiado(client, [{'id': produto_id, 'quantidade': 1}]).get_json()['venda_id']
        resposta = client.post(f'/vendas/listar_vendas_prazo/adicionar_observacao/{venda_id}',
                               data={'observacao': 'paga dia 10'}, follow_redirects=True)
        esperado = 'Observação salva.'
    assert texto(resposta).count(esperado) == 1


def test_bug19_excluir_fornecedor_avisa_produtos_sem_fornecedor(client):
    logar(client, criar_gerente())
    with get_db_connection() as conn:
        conn.execute("INSERT INTO fornecedores (nome, cnpj, contato) VALUES ('Frigo', '1', '2')")
        conn.commit()
    produto_id = create_produto('Picanha', '', 'BOI', 60, 5, fornecedor_id=1)
    html = texto(client.post('/fornecedores/excluir/1', follow_redirects=True))
    assert '1 produto(s) ficaram sem fornecedor' in html
    assert get_produto_by_id(produto_id)['fornecedor_id'] is None


def test_bug19_texto_na_url_nao_vira_mensagem_do_sistema(client):
    logar(client, criar_gerente())
    html = texto(client.get('/produtos?error=Sistema+bloqueado+ligue+para+0800'))
    assert 'Sistema bloqueado' not in html
    html = texto(client.get('/admin/usuarios?success=Mensagem+falsa'))
    assert 'Mensagem falsa' not in html


# ---------------------------------------------------------------- UI-01

# Classes usadas só como gancho de JavaScript/semântica, ou montadas dinamicamente
_CLASSES_SEM_ESTILO = {
    'produto-item', 'quantidade-input', 'cnpj-mask', 'phone-mask', 'no-image', 'total-info',
    'alertas-section', 'metodos-pagamento', 'top-produtos', 'vendas-section',
    'metricas-principais', 'dashboard-title', 'alert-', 'bg-', 'nivel-', 'success', 'warning',
}
# Templates sem uso (REL-06), fora da verificação
_TEMPLATES_MORTOS = {'relatorios/relatorios.html', 'relatorios/relatorio_unificado.html'}


def _classes_definidas(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    definidas, pilha, seletor = set(), [], ''
    for caractere in css:
        if caractere == '{':
            pais = pilha[-1] if pilha else []
            atuais = []
            for parte in (p.strip() for p in seletor.split(',')):
                if re.match(r'&[\w-]', parte):
                    continue  # "&-sufixo" é sintaxe do Sass: o navegador descarta a regra
                atuais.extend(pai + parte[1:] for pai in pais) if parte.startswith('&') else atuais.append(parte)
            for item in atuais:
                definidas.update(re.findall(r'\.([a-zA-Z_][\w-]*)', item))
            pilha.append([item for item in atuais if item.startswith('.')] or pais)
            seletor = ''
        elif caractere == '}':
            if pilha:
                pilha.pop()
            seletor = ''
        elif caractere == ';':
            seletor = ''
        else:
            seletor += caractere
    return definidas


def test_ui01_toda_classe_dos_templates_tem_estilo():
    with open(os.path.join(RAIZ, 'static', 'styles.css'), encoding='utf-8') as arquivo:
        globais = _classes_definidas(arquivo.read())
    faltando = {}
    pasta = os.path.join(RAIZ, 'templates')
    for caminho in glob.glob(os.path.join(pasta, '**', '*.html'), recursive=True):
        nome = os.path.relpath(caminho, pasta)
        if nome in _TEMPLATES_MORTOS:
            continue
        with open(caminho, encoding='utf-8') as arquivo:
            html = arquivo.read()
        locais = _classes_definidas(''.join(re.findall(r'<style>(.*?)</style>', html, flags=re.S)))
        for valor in re.findall(r'class="([^"]*)"', html):
            for classe in re.sub(r'\{\{.*?\}\}|\{%.*?%\}', ' ', valor).split():
                if (classe not in globais and classe not in locais
                        and classe not in _CLASSES_SEM_ESTILO and not classe.startswith('fa')):
                    faltando.setdefault(classe, set()).add(nome)
    assert faltando == {}


def test_ui01_sem_icones_do_bootstrap_icons():
    pasta = os.path.join(RAIZ, 'templates')
    for caminho in glob.glob(os.path.join(pasta, '**', '*.html'), recursive=True):
        if os.path.relpath(caminho, pasta) in _TEMPLATES_MORTOS:
            continue
        with open(caminho, encoding='utf-8') as arquivo:
            assert 'class="bi ' not in arquivo.read(), caminho


# ---------------------------------------------------------------- PERF-01 / BUG-28

def test_perf01_backup_do_banco_comprimido_e_fotos_so_quando_mudam(app):
    pasta = app.config['BACKUP_FOLDER']
    foto = os.path.join(app.config['UPLOAD_FOLDER'], 'picanha.png')
    with open(foto, 'wb') as arquivo:
        arquivo.write(b'imagem' * 1000)

    with app.app_context():
        primeiro = modulo_app.backup_db()
        segundo = modulo_app.backup_db()
    assert [n.split('_')[1] for n in primeiro] == ['banco', 'fotos']
    assert [n.split('_')[1] for n in segundo] == ['banco']  # fotos não mudaram

    with zipfile.ZipFile(os.path.join(pasta, primeiro[0])) as zipf:
        info = zipf.getinfo('acougue.db')
        assert info.compress_type == zipfile.ZIP_DEFLATED
        conn = sqlite3.connect(':memory:')
        conn.deserialize(zipf.read('acougue.db'))
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'vendas'").fetchone()[0] == 1
    with zipfile.ZipFile(os.path.join(pasta, primeiro[1])) as zipf:
        assert zipf.namelist() == ['produtos/picanha.png']

    with open(foto, 'ab') as arquivo:  # foto trocada
        arquivo.write(b'nova versao')
    with app.app_context():
        terceiro = modulo_app.backup_db()
    assert [n.split('_')[1] for n in terceiro] == ['banco', 'fotos']


def test_bug28_dois_backups_no_mesmo_segundo_nao_se_sobrescrevem(app):
    with app.app_context():
        nomes = modulo_app.backup_db()[:1] + modulo_app.backup_db()[:1]
    assert len(set(nomes)) == 2
    assert all(os.path.exists(os.path.join(app.config['BACKUP_FOLDER'], n)) for n in nomes)


def test_perf01_inicializacao_nao_refaz_backup_recente(app):
    with app.app_context():
        assert modulo_app.backup_se_necessario()      # nenhum backup ainda: faz
        assert modulo_app.backup_se_necessario() is None  # último tem menos de 24h: pula


def criar_backup_falso(pasta, prefixo, quando):
    nome = f"{prefixo}{quando:%Y%m%d_%H%M%S_%f}.zip"
    with zipfile.ZipFile(os.path.join(pasta, nome), 'w') as zipf:
        zipf.writestr('x', 'x')
    return nome


def test_perf01_retencao_mantem_7_dias_e_4_semanas(app):
    pasta = app.config['BACKUP_FOLDER']
    os.makedirs(pasta)
    agora = datetime(2026, 9, 26, 12, 0)
    # dois backups por dia nos últimos 60 dias
    for dias in range(60):
        for hora in (8, 20):
            criar_backup_falso(pasta, modulo_app.PREFIXO_BACKUP_BANCO,
                               agora - timedelta(days=dias) + timedelta(hours=hora - 12))
    for i in range(5):
        criar_backup_falso(pasta, modulo_app.PREFIXO_BACKUP_FOTOS, agora - timedelta(days=i * 10))
    legado = os.path.join(pasta, 'acougue_system_backup_20250529_012859.zip')
    open(legado, 'wb').close()

    with app.app_context():
        modulo_app.aplicar_retencao(agora)

    banco = sorted(n for n in os.listdir(pasta) if n.startswith(modulo_app.PREFIXO_BACKUP_BANCO))
    datas = [modulo_app._data_do_backup(n) for n in banco]
    dias_recentes = {d.date() for d in datas if d >= agora - timedelta(days=7)}
    assert len(dias_recentes) == 7                      # um por dia na última semana
    assert len({d.isocalendar()[:2] for d in datas}) == 4  # cobre as 4 semanas mais recentes
    assert len(banco) <= 7 + 4 + 2                      # + os das últimas 24h
    assert all(d >= agora - timedelta(days=28) for d in datas)
    assert max(datas).date() == agora.date()            # o mais recente sempre fica
    fotos = [n for n in os.listdir(pasta) if n.startswith(modulo_app.PREFIXO_BACKUP_FOTOS)]
    assert len(fotos) == 2
    assert os.path.exists(legado)                        # backups antigos não são tocados


def test_perf01_download_gera_backup_completo_sem_guardar_arquivo(client, app):
    logar(client, criar_gerente())
    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'foto.png'), 'wb') as arquivo:
        arquivo.write(b'png')
    resposta = client.get('/backup')
    assert resposta.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resposta.data)) as zipf:
        assert set(zipf.namelist()) == {'acougue.db', 'produtos/foto.png'}
    pasta = app.config['BACKUP_FOLDER']
    assert not os.path.isdir(pasta) or os.listdir(pasta) == []
