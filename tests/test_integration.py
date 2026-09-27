import unittest
import os
import shutil
import tempfile
from banco_dados import (
    init_db, create_user, get_user_by_id, update_user, delete_user,
    create_fornecedor, get_fornecedor_by_id, update_fornecedor, delete_fornecedor,
    create_produto, get_produto_by_id, update_produto, excluir_produto,
    processar_venda, get_venda_by_id, get_venda_items, delete_venda,
    get_all_produtos, listar_produtos_simples, get_db_connection
)
from werkzeug.security import check_password_hash
from unittest.mock import patch, MagicMock


class TestBase(unittest.TestCase):
    def setUp(self):
        # Banco e uploads em pasta temporária própria de cada teste
        self.pasta = tempfile.mkdtemp(prefix='acougue-integracao-')
        self.db_anterior = os.environ.get('DB_PATH')
        os.environ['DB_PATH'] = os.path.join(self.pasta, 'teste.db')
        self.upload_folder = os.path.join(self.pasta, 'uploads')
        os.makedirs(self.upload_folder)
        init_db()

    def tearDown(self):
        if self.db_anterior is None:
            os.environ.pop('DB_PATH', None)
        else:
            os.environ['DB_PATH'] = self.db_anterior
        shutil.rmtree(self.pasta, ignore_errors=True)

class TestUserDB(TestBase):
    def test_create_user_success(self):
        user_id = create_user('testuser', 'test@example.com', 'senha1234', 'gerente')
        user = get_user_by_id(user_id)
        self.assertEqual(user['role'], 'gerente')

    def test_create_user_duplicate_username(self):
        create_user('user1', 'email1@test.com', 'senha1234')  # Senha >= 8
        with self.assertRaises(ValueError) as context:
            create_user('user1', 'email2@test.com', 'senha1234')
        self.assertIn("Username já está em uso", str(context.exception))

    def test_update_user_password(self):
        user_id = create_user('update_user', 'update@test.com', 'oldpass1')  # Senha >= 8
        update_user(user_id, password='newpass1')  # Senha >= 8
        user = get_user_by_id(user_id)
        self.assertTrue(check_password_hash(user['password_hash'], 'newpass1'))

    def test_delete_user(self):
        user_id = create_user('delete_me', 'delete@test.com', 'pass1234')  # Corrigido: senha >= 8
        delete_user(user_id)
        user = get_user_by_id(user_id)
        self.assertIsNone(user)


class TestFornecedorDB(TestBase):
    def test_create_fornecedor_success(self):
        fornecedor_id = create_fornecedor('Fornecedor A', '123456789', 'contato@a.com', 'Endereço X')
        fornecedor = get_fornecedor_by_id(fornecedor_id)
        self.assertEqual(fornecedor['nome'], 'Fornecedor A')
        self.assertEqual(fornecedor['cnpj'], '123456789')

    def test_create_fornecedor_duplicate_cnpj(self):
        create_fornecedor('Fornecedor B', '111111111', 'contato@b.com')
        with self.assertRaises(ValueError) as context:
            create_fornecedor('Fornecedor C', '111111111', 'contato@c.com')
        self.assertIn("CNPJ já cadastrado", str(context.exception))

    def test_update_fornecedor(self):
        fornecedor_id = create_fornecedor('Fornecedor D', '222222222', 'contato@d.com')
        update_fornecedor(fornecedor_id, nome='Fornecedor E', contato='novo@contato.com')
        fornecedor = get_fornecedor_by_id(fornecedor_id)
        self.assertEqual(fornecedor['nome'], 'Fornecedor E')
        self.assertEqual(fornecedor['contato'], 'novo@contato.com')



from flask import Flask, current_app

class TestProdutoDB(TestBase):
    def test_create_produto_with_photo(self):
        # Criar app fake e contexto
        app = Flask(__name__)
        app.config['UPLOAD_FOLDER'] = self.upload_folder
        
        with app.app_context():
            # Mock do current_app dentro do contexto
            with patch('banco_dados.current_app', current_app):
                # Simular arquivo
                mock_file = MagicMock()
                mock_file.filename = 'test.jpg'
                mock_file.save = lambda path: open(path, 'w').close()
                
                produto_id = create_produto(
                    'Carne Bovina', 'Descrição', 'Carnes', 45.99, 20,
                    foto_file=mock_file, fornecedor_id=None
                )
                produto = get_produto_by_id(produto_id)
                self.assertEqual(produto['nome'], 'Carne Bovina')
                self.assertTrue(produto['foto'].endswith('test.jpg'))
                self.assertTrue(os.path.exists(
                    os.path.join(self.upload_folder, produto['foto'])
                ))
        
    def test_update_produto_estoque(self):
        produto_id = create_produto('Produto Teste', '', 'Categoria', 10.0, 50)
        
        # Forçar diferença de tempo
        with get_db_connection() as conn:
            conn.execute("UPDATE produtos SET created_at = '2023-01-01 00:00:00' WHERE id = ?", (produto_id,))
            conn.commit()
        
        update_produto(produto_id, quantidade=30)
        produto = get_produto_by_id(produto_id)
        self.assertEqual(produto['quantidade'], 30)
        self.assertNotEqual(produto['created_at'], produto['updated_at'])  # Agora deve passar

class TestVendaDB(TestBase):
    def setUp(self):
        super().setUp()
        # Criar dados necessários
        self.user_id = create_user('venda_user', 'venda@test.com', 'senha1234')  # Corrigido: senha >= 8
        self.produto_id = create_produto('Produto Venda', 'Desc', 'Cat', 15.0, 100)

    def test_processar_venda_success(self):
        venda_data = {
            'cliente_cpf': '12345678900',
            'cliente_nome': 'Cliente Teste',
            'metodo_pagamento': 'dinheiro',
            'status_pagamento': 'pago',
            'itens': [{'id': self.produto_id, 'quantidade': 3, 'preco': 15.0}]
        }
        processar_venda('venda_1', venda_data, self.user_id)
        
        venda = get_venda_by_id('venda_1')
        self.assertEqual(venda['total'], 45.0)
        
        produto = get_produto_by_id(self.produto_id)
        self.assertEqual(produto['quantidade'], 97)
        
        itens = get_venda_items('venda_1')
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]['quantidade'], 3)

    def test_venda_estoque_insuficiente(self):
        venda_data = {
            'cliente_cpf': '123',
            'cliente_nome': 'Cliente',
            'metodo_pagamento': 'dinheiro',
            'itens': [{'id': self.produto_id, 'quantidade': 150, 'preco': 15.0}]
        }
        with self.assertRaises(ValueError):
            processar_venda('venda_2', venda_data, self.user_id)
        
        produto = get_produto_by_id(self.produto_id)
        self.assertEqual(produto['quantidade'], 100)


if __name__ == '__main__':
    unittest.main()