#test_sig_acougue.py
import pytest
from datetime import datetime, timedelta
from io import BytesIO
import os
import sqlite3
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash
from banco_dados import (
    create_venda_item, init_db, get_db_connection, create_user, get_user_by_id, get_user_by_username,
    update_user, delete_user, create_fornecedor, get_fornecedor_by_id, update_fornecedor,
    delete_fornecedor, create_produto, get_produto_by_id, update_produto, excluir_produto,
    create_venda, get_venda_by_id, processar_venda, delete_venda, get_venda_items,
    listar_produtos, get_fornecedores, get_categorias, marcar_venda_pago, get_all_users
)
from flask import Flask

# Fixtures
@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = str(tmp_path / "uploads")
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    return app

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv('DB_PATH', str(db_path))
    init_db()
    return db_path

# Testes Users
def test_create_user(test_db):
    user_id = create_user('testuser', 'test@example.com', 'senha123')
    user = get_user_by_id(user_id)
    assert user['username'] == 'testuser'
    assert user['email'] == 'test@example.com'

def test_create_user_duplicate_username(test_db):
    create_user('user1', 'user1@example.com', 'senha123')
    with pytest.raises(ValueError) as e:
        create_user('user1', 'user2@example.com', 'senha123')
    assert 'Username já está em uso' in str(e.value)

def test_update_user_password(test_db):
    user_id = create_user('updateuser', 'update@example.com', 'oldpass')
    update_user(user_id, password='newpass')
    user = get_user_by_id(user_id)
    assert check_password_hash(user['password_hash'], 'newpass')

# Testes Fornecedores
def test_create_fornecedor(test_db):
    fornecedor_id = create_fornecedor('Fornecedor A', '12345678901234', 'contato@a.com')
    fornecedor = get_fornecedor_by_id(fornecedor_id)
    assert fornecedor['nome'] == 'Fornecedor A'
    assert fornecedor['cnpj'] == '12345678901234'

def test_update_fornecedor_cnpj(test_db):
    fornecedor_id = create_fornecedor('Fornecedor B', '11111111111111', 'contato@b.com')
    update_fornecedor(fornecedor_id, cnpj='22222222222222')
    fornecedor = get_fornecedor_by_id(fornecedor_id)
    assert fornecedor['cnpj'] == '22222222222222'

# Testes Produtos
def test_create_produto(app, test_db):
    with app.app_context():
        produto_id = create_produto(
            nome='Carne', descricao='Bovina', categoria='Carnes',
            preco=30.0, quantidade=10, estoque_minimo=2
        )
        produto = get_produto_by_id(produto_id)
        assert produto['nome'] == 'Carne'
        assert produto['preco'] == 30.0

# Testes Vendas
def test_processar_venda(app, test_db):
    with app.app_context():
        user_id = create_user('vendedor', 'vendedor@example.com', 'senha123')
        produto_id = create_produto('Produto Venda', '', 'Teste', 20.0, 10)
        
        venda_data = {
            'cliente_cpf': '12345678901',
            'cliente_nome': 'Cliente',
            'metodo_pagamento': 'dinheiro',
            'status_pagamento': 'pago',
            'itens': [{'id': produto_id, 'quantidade': 3, 'preco': 20.0}]
        }
        
        processar_venda('VENDA_001', venda_data, user_id)
        
        produto = get_produto_by_id(produto_id)
        assert produto['quantidade'] == 7
        
        venda = get_venda_by_id('VENDA_001')
        assert venda['total'] == 60.0

# Testes Exclusões
def test_delete_venda_cascade(test_db):
    user_id = create_user('user', 'user@example.com', 'senha123')
    produto_id = create_produto('Produto Teste', '', 'Teste', 10, 5)  # Create product
    venda_id = create_venda('VENDA_002', '11111111111', 'Cliente', 100.0, 'cartao', user_id)
    create_venda_item(venda_id, produto_id, 2, 50.0)  # Use valid produto_id
    
    delete_venda(venda_id)
    itens = get_venda_items(venda_id)
    assert len(itens) == 0

# Testes Arquivos
def test_produto_foto(app, test_db):
    with app.app_context():
        file = FileStorage(
            stream=BytesIO(b'test content'),
            filename='test.jpg',
            content_type='image/jpeg'
        )
        produto_id = create_produto(
            'Produto Foto', '', 'Teste', 10, 5, foto_file=file
        )
        produto = get_produto_by_id(produto_id)
        assert produto['foto'] == 'test.jpg'
        assert os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'test.jpg'))

def test_excluir_produto_foto(app, test_db):
    with app.app_context():
        file = FileStorage(
            stream=BytesIO(b'test content'),
            filename='delete.jpg',
            content_type='image/jpeg'
        )
        produto_id = create_produto(
            'Produto Delete', '', 'Teste', 10, 5, foto_file=file
        )
        excluir_produto(produto_id)
        assert not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'delete.jpg'))

# Testes Paginação/Filtros
def test_listar_produtos_paginacao(test_db):
    for i in range(15):
        create_produto(f'Produto {i}', '', 'Cat', i, 10)
    
    produtos, total = listar_produtos(page=1, per_page=10)
    assert len(produtos) == 10
    assert total == 15

# Executar os testes com: pytest -v