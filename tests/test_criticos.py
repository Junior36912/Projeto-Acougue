"""Testes de regressão dos problemas críticos listados em PROBLEMAS_E_MELHORIAS.md.

Cada teste cita o ID do item que protege. Se algum falhar, o problema voltou.
"""
import io
import json
import os
import sqlite3
import stat
from datetime import date

import pytest
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash

import app as modulo_app
from app_logging import registrar_log
from banco_dados import (
    SCHEMA_VERSION, create_produto, create_user, get_db_connection, get_produto_by_id,
    get_user_by_id, init_db, listar_logs, processar_venda, update_user,
)

HOJE = date.today().isoformat()


# ---------------------------------------------------------------- utilitários

def logar(client, user_id, role='gerente', username='teste'):
    with client.session_transaction() as sessao:
        sessao.update(user_id=user_id, username=username, role=role)


def criar_gerente(username='gerente'):
    return create_user(username, f'{username}@teste.com', 'senha123', 'gerente')


def criar_produto(nome='Picanha', preco=50.0, quantidade=10, tipo_venda='unidade',
                  estoque_minimo=0, foto=None):
    produto_id = create_produto(nome, '', 'BOI', preco, quantidade,
                                estoque_minimo=estoque_minimo, tipo_venda=tipo_venda)
    if foto:
        with get_db_connection() as conn:
            conn.execute('UPDATE produtos SET foto = ? WHERE id = ?', (foto, produto_id))
            conn.commit()
    return produto_id


def vender(client, itens, **extra):
    corpo = {'metodo_pagamento': 'PIX', 'data_venda': HOJE, 'itens': itens}
    corpo.update(extra)
    return client.post('/vendas/nova', json=corpo)


def estoque(produto_id):
    return get_produto_by_id(produto_id)['quantidade']


def contar(tabela):
    with get_db_connection() as conn:
        return conn.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]


def imagem_png():
    # PNG mínimo válido (1x1)
    return io.BytesIO(bytes.fromhex(
        '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
        '1f15c4890000000d49444154789c6300010000000500010d0a2db40000'
        '000049454e44ae426082'))


def formulario_produto(**campos):
    """Formulário como o navegador envia: campos opcionais vão vazios."""
    dados = {'nome': 'Alcatra', 'descricao': '', 'categoria': 'BOI', 'preco': '45.90',
             'quantidade': '8', 'tipo_venda': 'quilo', 'estoque_minimo': '',
             'codigo_barras': '', 'fornecedor_id': '', 'data_validade': ''}
    dados.update(campos)
    return dados


# ---------------------------------------------------------------- BUG-01

def test_bug01_criar_usuario_pela_tela(client):
    logar(client, criar_gerente())
    resposta = client.post('/admin/usuarios/novo', data={
        'username': 'caixa1', 'email': 'caixa1@teste.com',
        'password': 'segredo1', 'role': 'funcionario'})
    assert resposta.status_code == 302
    assert '/admin/usuarios' in resposta.headers['Location']
    with get_db_connection() as conn:
        usuario = conn.execute("SELECT * FROM users WHERE username = 'caixa1'").fetchone()
    assert usuario is not None
    assert check_password_hash(usuario['password_hash'], 'segredo1')


def test_bug01_trocar_senha(db_path):
    user_id = criar_gerente()
    update_user(user_id, password='nova-senha')
    assert check_password_hash(get_user_by_id(user_id)['password_hash'], 'nova-senha')


def test_bug01_trocar_foto_na_edicao(client, app):
    logar(client, criar_gerente())
    produto_id = criar_produto()
    dados = formulario_produto(nome='Picanha', tipo_venda='unidade', foto=(imagem_png(), 'nova.png'))
    resposta = client.post(f'/produtos/editar/{produto_id}', data=dados,
                           content_type='multipart/form-data')
    assert resposta.status_code == 302
    foto = get_produto_by_id(produto_id)['foto']
    assert foto and foto.endswith('nova.png')
    assert os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], foto))


# ---------------------------------------------------------------- BUG-02

def test_bug02_foto_salva_no_cadastro(client, app):
    logar(client, criar_gerente())
    dados = formulario_produto(foto=(imagem_png(), 'alcatra.png'))
    resposta = client.post('/produtos/novo', data=dados, content_type='multipart/form-data')
    assert resposta.status_code == 302, resposta.data
    with get_db_connection() as conn:
        produto = conn.execute("SELECT * FROM produtos WHERE nome = 'Alcatra'").fetchone()
    assert produto['foto'] and produto['foto'].endswith('alcatra.png')
    assert '/' not in produto['foto']  # só o nome do arquivo (BUG-03)
    assert os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], produto['foto']))


def test_bug02_cadastro_sem_foto_e_sem_estoque_minimo(client):
    """O navegador envia 'Estoque mínimo' vazio; antes isso impedia o cadastro."""
    logar(client, criar_gerente())
    resposta = client.post('/produtos/novo', data=formulario_produto())
    assert resposta.status_code == 302, resposta.data
    with get_db_connection() as conn:
        produto = conn.execute("SELECT * FROM produtos WHERE nome = 'Alcatra'").fetchone()
    assert produto['foto'] is None
    assert produto['estoque_minimo'] == 0


# ---------------------------------------------------------------- BUG-03

def test_bug03_telas_montam_url_da_foto_corretamente(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(foto='picanha.webp')
    url = 'src="/static/uploads/produtos/picanha.webp"'
    assert url in client.get('/produtos').get_data(as_text=True)
    assert url in client.get('/vendas/nova').get_data(as_text=True)
    assert url in client.get(f'/produtos/editar/{produto_id}').get_data(as_text=True)


def criar_banco_antigo(caminho):
    """Banco no formato das versões anteriores (sem migrações, user_version 0)."""
    conn = sqlite3.connect(caminho)
    conn.executescript('''
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'funcionario', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE fornecedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
            cnpj TEXT UNIQUE NOT NULL, contato TEXT NOT NULL, endereco TEXT);
        CREATE TABLE produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
            descricao TEXT, categoria TEXT NOT NULL, preco DECIMAL(10,2) NOT NULL,
            quantidade INTEGER NOT NULL, estoque_minimo INTEGER DEFAULT 0, codigo_barras TEXT UNIQUE,
            foto TEXT, fornecedor_id INTEGER REFERENCES fornecedores(id) ON DELETE SET NULL,
            data_validade DATE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, tipo_venda TEXT NOT NULL DEFAULT 'unidade');
        CREATE TABLE vendas (id TEXT PRIMARY KEY, data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cliente_cpf TEXT, cliente_nome TEXT, total DECIMAL(10,2) NOT NULL,
            metodo_pagamento TEXT NOT NULL,
            usuario_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status_pagamento TEXT NOT NULL DEFAULT 'pago', data_vencimento DATE, observacao TEXT);
        CREATE TABLE venda_itens (id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id TEXT NOT NULL REFERENCES vendas(id),
            produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
            quantidade INTEGER NOT NULL, preco_unitario DECIMAL(10,2) NOT NULL);
        INSERT INTO users (username, email, password_hash, role) VALUES ('antigo', 'a@a', 'x', 'gerente');
        INSERT INTO produtos (nome, categoria, preco, quantidade, foto)
            VALUES ('Coração', 'BOI', 14, 5, 'uploads/produtos/coracao.png');
        INSERT INTO produtos (nome, categoria, preco, quantidade, foto)
            VALUES ('Heineken', 'BEBIDAS', 9, 5, '1748723703.866579_Heineken.jpg');
        INSERT INTO vendas (id, total, metodo_pagamento, usuario_id) VALUES ('V1', 28, 'PIX', 1);
        INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario) VALUES ('V1', 1, 2, 14);
    ''')
    conn.commit()
    conn.close()


def test_bug03_migracao_padroniza_caminho_das_fotos(tmp_path, monkeypatch):
    caminho = tmp_path / 'antigo.db'
    criar_banco_antigo(caminho)
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()
    with get_db_connection() as conn:
        fotos = [r['foto'] for r in conn.execute('SELECT foto FROM produtos ORDER BY id')]
    assert fotos == ['coracao.png', '1748723703.866579_Heineken.jpg']


# ---------------------------------------------------------------- BUG-04

def test_bug04_pagina_de_estoque_baixo(client):
    logar(client, criar_gerente())
    criar_produto('Fígado', quantidade=1, estoque_minimo=5)
    criar_produto('Alcatra', quantidade=50, estoque_minimo=5)
    resposta = client.get('/admin/estoque')
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'Fígado' in html
    assert 'Alcatra' not in html


# ---------------------------------------------------------------- BUG-05

def test_bug05_listar_logs_com_filtros_conta_certo(db_path):
    registrar_log(1, 'login', 'INFO', {'result': 'success'})
    registrar_log(1, 'logout', 'INFO')
    registrar_log('Sistema', 'alerta_validade', 'WARNING', {'nome': 'Coração'})

    logs, total = listar_logs(level='WARNING')
    assert total == 1 and logs[0]['action'] == 'alerta_validade'
    assert listar_logs(user_id='1')[1] == 2
    assert listar_logs(search='Coração')[1] == 1
    assert listar_logs(action='login', start_date='2000-01-01', end_date='2999-12-31')[1] == 1


@pytest.mark.parametrize('filtro', [
    'level=INFO', 'search=login', 'user_id=1', 'action=login',
    'start_date=2000-01-01&end_date=2999-12-31', 'level=INFO&search=x&user_id=Sistema&page=3',
])
def test_bug05_pagina_de_logs_aceita_filtros(client, filtro):
    logar(client, criar_gerente())
    registrar_log(1, 'login', 'INFO')
    assert client.get(f'/logs?{filtro}').status_code == 200


# ---------------------------------------------------------------- BUG-06

def test_bug06_logs_mostra_registros_reais(client):
    user_id = criar_gerente('maria')
    logar(client, user_id)
    registrar_log(user_id, 'acao_unica_de_teste', 'INFO', {'produto': 'Picanha'})
    html = client.get('/logs').get_data(as_text=True)
    assert 'acao_unica_de_teste' in html
    assert 'maria' in html  # nome do usuário, não o id
    assert 'Picanha' in html  # detalhes do JSON
    # dados fictícios da maquete antiga
    assert 'João Silva' not in html
    assert '1,248' not in html


def test_bug06_logs_paginam_e_filtram(client):
    logar(client, criar_gerente())
    for i in range(25):
        registrar_log(1, f'acao_{i:02d}', 'INFO')
    registrar_log(1, 'problema_grave', 'ERROR')

    html = client.get('/logs').get_data(as_text=True)
    assert 'Página 1 de 2' in html
    assert 'page=2' in html

    html = client.get('/logs?level=ERROR').get_data(as_text=True)
    assert '<td>problema_grave</td>' in html
    assert '<td>acao_00</td>' not in html  # (acao_00 continua como opção do filtro de ação)


def test_bug06_home_do_gerente_tem_link_para_logs_e_estoque(client):
    logar(client, criar_gerente())
    html = client.get('/').get_data(as_text=True)
    assert 'href="/logs"' in html
    assert 'href="/admin/estoque"' in html


# ---------------------------------------------------------------- NEG-01

def test_neg01_preco_enviado_pelo_navegador_e_ignorado(client):
    logar(client, criar_gerente(), role='funcionario')
    produto_id = criar_produto(preco=50.0, quantidade=10)
    resposta = vender(client, [{'id': produto_id, 'preco': 0.01, 'quantidade': 2}])
    assert resposta.status_code == 200, resposta.get_json()
    venda_id = resposta.get_json()['venda_id']
    with get_db_connection() as conn:
        venda = conn.execute('SELECT total FROM vendas WHERE id = ?', (venda_id,)).fetchone()
        item = conn.execute('SELECT preco_unitario FROM venda_itens WHERE venda_id = ?',
                            (venda_id,)).fetchone()
    assert venda['total'] == 100.0
    assert item['preco_unitario'] == 50.0


def test_neg01_produto_por_quilo_usa_preco_do_cadastro(client):
    logar(client, criar_gerente())
    produto_id = criar_produto('Alcatra', preco=39.90, quantidade=10, tipo_venda='quilo')
    resposta = vender(client, [{'id': produto_id, 'preco': 1, 'quantidade': 1.5}])
    assert resposta.status_code == 200, resposta.get_json()
    with get_db_connection() as conn:
        total = conn.execute('SELECT total FROM vendas').fetchone()['total']
    assert total == 59.85  # 1,5 kg x R$ 39,90, arredondado em centavos
    assert estoque(produto_id) == 8.5


def test_neg01_produto_sem_preco_nao_pode_ser_vendido(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(preco=0, quantidade=10)
    resposta = vender(client, [{'id': produto_id, 'preco': 10, 'quantidade': 1}])
    assert resposta.status_code == 400
    assert 'sem preço' in resposta.get_json()['error']
    assert estoque(produto_id) == 10


# ---------------------------------------------------------------- NEG-02

@pytest.mark.parametrize('quantidade', [-50, 0, 'abc', None, float('nan')])
def test_neg02_quantidade_invalida_rejeitada(client, quantidade):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    item = {'id': produto_id, 'quantidade': quantidade}
    resposta = client.post('/vendas/nova', data=json.dumps(
        {'metodo_pagamento': 'PIX', 'data_venda': HOJE, 'itens': [item]}, allow_nan=True),
        content_type='application/json')
    assert resposta.status_code == 400
    assert estoque(produto_id) == 10
    assert contar('vendas') == 0


def test_neg02_venda_acima_do_estoque_rejeitada(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=16)
    resposta = vender(client, [{'id': produto_id, 'quantidade': 99999}])
    assert resposta.status_code == 400
    assert 'Estoque insuficiente' in resposta.get_json()['error']
    assert estoque(produto_id) == 16


def test_neg02_venda_do_estoque_exato_permitida(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=3)
    assert vender(client, [{'id': produto_id, 'quantidade': 3}]).status_code == 200
    assert estoque(produto_id) == 0


def test_neg02_mesmo_produto_repetido_nao_passa_do_estoque(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=5)
    resposta = vender(client, [{'id': produto_id, 'quantidade': 3},
                               {'id': produto_id, 'quantidade': 3}])
    assert resposta.status_code == 400
    assert estoque(produto_id) == 5


def test_neg02_falha_em_um_item_desfaz_a_venda_inteira(client):
    logar(client, criar_gerente())
    primeiro = criar_produto('Picanha', quantidade=10)
    segundo = criar_produto('Fígado', quantidade=1)
    resposta = vender(client, [{'id': primeiro, 'quantidade': 2},
                               {'id': segundo, 'quantidade': 5}])
    assert resposta.status_code == 400
    assert estoque(primeiro) == 10  # a baixa do primeiro item foi desfeita
    assert contar('vendas') == 0
    assert contar('venda_itens') == 0


def test_neg02_carrinho_vazio_rejeitado(client):
    logar(client, criar_gerente())
    assert vender(client, []).status_code == 400
    assert contar('vendas') == 0


def test_neg02_produto_inexistente_rejeitado(client):
    logar(client, criar_gerente())
    resposta = vender(client, [{'id': 424242, 'quantidade': 1}])
    assert resposta.status_code == 400
    assert 'não encontrado' in resposta.get_json()['error']


def test_neg02_quantidade_fracionada_em_produto_por_unidade(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10, tipo_venda='unidade')
    assert vender(client, [{'id': produto_id, 'quantidade': 1.5}]).status_code == 400
    assert estoque(produto_id) == 10


@pytest.mark.parametrize('corpo', [
    {'data_venda': HOJE, 'itens': []},  # sem forma de pagamento
    'isto não é json',
    ['lista', 'em', 'vez', 'de', 'objeto'],
])
def test_neg02_corpo_invalido_retorna_400(client, corpo):
    logar(client, criar_gerente())
    if isinstance(corpo, str):
        resposta = client.post('/vendas/nova', data=corpo, content_type='application/json')
    else:
        resposta = client.post('/vendas/nova', json=corpo)
    assert resposta.status_code == 400


def test_neg02_processar_venda_valida_mesmo_sem_a_rota(db_path):
    user_id = criar_gerente()
    produto_id = criar_produto(quantidade=5)
    with pytest.raises(ValueError):
        processar_venda('V-X', {'metodo_pagamento': 'PIX',
                                'itens': [{'id': produto_id, 'quantidade': -3}]}, user_id)
    assert estoque(produto_id) == 5


def test_bug13_duas_vendas_seguidas_nao_colidem(client):
    logar(client, criar_gerente())
    produto_id = criar_produto(quantidade=10)
    primeira = vender(client, [{'id': produto_id, 'quantidade': 1}])
    segunda = vender(client, [{'id': produto_id, 'quantidade': 1}])
    assert primeira.status_code == segunda.status_code == 200
    assert primeira.get_json()['venda_id'] != segunda.get_json()['venda_id']
    assert estoque(produto_id) == 8


# ---------------------------------------------------------------- NEG-03

def registrar_venda_direta(user_id, produto_id, venda_id='V1'):
    with get_db_connection() as conn:
        conn.execute("INSERT INTO vendas (id, total, metodo_pagamento, usuario_id) "
                     "VALUES (?, 50, 'PIX', ?)", (venda_id, user_id))
        conn.execute("INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario) "
                     "VALUES (?, ?, 1, 50)", (venda_id, produto_id))
        conn.commit()


def test_neg03_excluir_funcionario_com_vendas_preserva_o_historico(client):
    gerente = criar_gerente()
    funcionario = create_user('caixa', 'caixa@teste.com', 'senha123', 'funcionario')
    registrar_venda_direta(funcionario, criar_produto())
    logar(client, gerente)

    resposta = client.post(f'/admin/usuarios/excluir/{funcionario}', follow_redirects=True)
    assert resposta.status_code == 200
    assert 'desativado' in resposta.get_data(as_text=True)
    assert contar('vendas') == 1
    assert contar('venda_itens') == 1
    assert get_user_by_id(funcionario)['ativo'] == 0
    assert 'caixa@teste.com' not in client.get('/admin/usuarios').get_data(as_text=True)


def test_neg03_usuario_desativado_nao_consegue_entrar(client):
    gerente = criar_gerente()
    funcionario = create_user('caixa', 'caixa@teste.com', 'senha123', 'funcionario')
    registrar_venda_direta(funcionario, criar_produto())
    logar(client, gerente)
    client.post(f'/admin/usuarios/excluir/{funcionario}')

    anonimo = client.application.test_client()
    resposta = anonimo.post('/login', data={'username': 'caixa', 'password': 'senha123'})
    assert resposta.status_code == 200
    assert 'Credenciais inválidas' in resposta.get_data(as_text=True)


def test_neg03_excluir_usuario_sem_vendas_apaga_de_fato(client):
    gerente = criar_gerente()
    funcionario = create_user('novato', 'novato@teste.com', 'senha123', 'funcionario')
    logar(client, gerente)
    client.post(f'/admin/usuarios/excluir/{funcionario}')
    assert get_user_by_id(funcionario) is None


def test_neg03_banco_bloqueia_apagar_usuario_com_vendas(db_path):
    user_id = criar_gerente()
    registrar_venda_direta(user_id, criar_produto())
    with get_db_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))


def test_neg03_excluir_produto_vendido_desativa_e_preserva_itens(client):
    logar(client, criar_gerente())
    produto_id = criar_produto('Coração')
    registrar_venda_direta(1, produto_id)

    resposta = client.post(f'/produtos/excluir/{produto_id}')
    assert resposta.status_code == 302
    assert 'error' not in resposta.headers['Location']
    assert get_produto_by_id(produto_id)['ativo'] == 0
    assert contar('venda_itens') == 1
    assert 'Coração' not in client.get('/produtos').get_data(as_text=True)
    assert 'Coração' not in client.get('/vendas/nova').get_data(as_text=True)
    assert client.get(f'/produtos/editar/{produto_id}').status_code == 404
    # e não pode mais ser vendido
    assert vender(client, [{'id': produto_id, 'quantidade': 1}]).status_code == 400


def test_neg03_excluir_produto_nunca_vendido_apaga_produto_e_foto(client, app):
    logar(client, criar_gerente())
    foto = 'foto-exclusiva.png'
    open(os.path.join(app.config['UPLOAD_FOLDER'], foto), 'wb').close()
    produto_id = criar_produto(foto=foto)
    client.post(f'/produtos/excluir/{produto_id}')
    assert get_produto_by_id(produto_id) is None
    assert not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], foto))


def test_neg03_foto_compartilhada_nao_e_apagada(client, app):
    logar(client, criar_gerente())
    foto = 'compartilhada.png'
    open(os.path.join(app.config['UPLOAD_FOLDER'], foto), 'wb').close()
    primeiro = criar_produto('Linguiça A', foto=foto)
    criar_produto('Linguiça B', foto=foto)
    client.post(f'/produtos/excluir/{primeiro}')
    assert os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], foto))


def test_neg03_migracao_de_banco_antigo(tmp_path, monkeypatch):
    caminho = tmp_path / 'antigo.db'
    criar_banco_antigo(caminho)
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()

    with get_db_connection() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        fk_vendas = {fk['table']: fk['on_delete']
                     for fk in conn.execute('PRAGMA foreign_key_list(vendas)')}
        fk_itens = {fk['table']: fk['on_delete']
                    for fk in conn.execute('PRAGMA foreign_key_list(venda_itens)')}
        assert fk_vendas['users'] == 'NO ACTION'
        assert fk_itens['produtos'] == 'NO ACTION'
        assert fk_itens['vendas'] == 'CASCADE'
        # dados preservados
        assert conn.execute('SELECT COUNT(*) FROM vendas').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM venda_itens').fetchone()[0] == 1
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        # o banco agora impede apagar histórico
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM users WHERE id = 1')

    # backup automático feito antes da migração
    backups = os.listdir(tmp_path / 'backups')
    assert len(backups) == 1 and backups[0].startswith('antigo_pre_migracao_v0_')

    # rodar de novo não faz nada (idempotente, sem novo backup)
    init_db()
    assert len(os.listdir(tmp_path / 'backups')) == 1


# ---------------------------------------------------------------- SEC-01

def test_sec01_chave_secreta_nao_e_a_padrao_do_codigo():
    assert modulo_app.app.secret_key not in ('dev-key-123', '', None)


def test_sec01_codigo_nao_tem_chave_fixa():
    # Os testes definem SECRET_KEY no ambiente; este teste garante que, sem ela,
    # o app não cai numa chave conhecida escrita no código.
    with open(modulo_app.__file__, encoding='utf-8') as arquivo:
        assert 'dev-key-123' not in arquivo.read()


def assinar_sessao(chave, dados):
    falso = Flask('forjador')
    falso.secret_key = chave
    return SecureCookieSessionInterface().get_signing_serializer(falso).dumps(dados)


def test_sec01_cookie_forjado_com_chave_antiga_e_rejeitado(client, app):
    # o usuário existe: o que decide é a assinatura do cookie
    sessao_de_gerente = {'user_id': criar_gerente(), 'username': 'invasor', 'role': 'gerente'}

    client.set_cookie('session', assinar_sessao('dev-key-123', sessao_de_gerente))
    resposta = client.get('/produtos')
    assert resposta.status_code == 302 and '/login' in resposta.headers['Location']

    # controle: a mesma sessão assinada com a chave real é aceita
    client.set_cookie('session', assinar_sessao(app.secret_key, sessao_de_gerente))
    assert client.get('/produtos').status_code == 200


def test_sec01_chave_gerada_e_reaproveitada(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    pasta = tmp_path / 'instance'
    chave = modulo_app.carregar_secret_key(str(pasta))
    arquivo = pasta / 'secret_key'
    assert len(chave) == 64
    assert arquivo.read_text() == chave
    assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600
    assert modulo_app.carregar_secret_key(str(pasta)) == chave  # mesma chave após reiniciar


def test_sec01_variavel_de_ambiente_tem_prioridade(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'definida-no-ambiente')
    assert modulo_app.carregar_secret_key(str(tmp_path)) == 'definida-no-ambiente'
    assert not (tmp_path / 'secret_key').exists()


# ---------------------------------------------------------------- SEC-02

def test_sec02_debug_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    execucao = modulo_app.configuracao_execucao()
    assert execucao['debug'] is False
    assert execucao['host'] == '127.0.0.1'


@pytest.mark.parametrize('valor, esperado', [('1', True), ('true', True), ('0', False), ('', False)])
def test_sec02_debug_so_liga_quando_pedido(monkeypatch, valor, esperado):
    monkeypatch.setenv('FLASK_DEBUG', valor)
    assert modulo_app.configuracao_execucao()['debug'] is esperado


def test_sec02_codigo_nao_tem_debug_fixo():
    with open(modulo_app.__file__, encoding='utf-8') as arquivo:
        assert 'debug=True' not in arquivo.read()


def test_bug09_pagina_404_personalizada(client):
    resposta = client.get('/pagina-que-nao-existe')
    assert resposta.status_code == 404
    assert 'Página Não Encontrada' in resposta.get_data(as_text=True)
