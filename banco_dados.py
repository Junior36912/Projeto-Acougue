import sqlite3
import os
from contextlib import contextmanager
from werkzeug.security import generate_password_hash


@contextmanager
def get_db_connection():
    conn = sqlite3.connect('acougue.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Inicialização completa do banco de dados"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        
        # Tabela de Usuários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'funcionario',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de Fornecedores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fornecedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cnpj TEXT UNIQUE NOT NULL,
                contato TEXT NOT NULL,
                endereco TEXT
            )
        ''')
        
        # Tabela de Produtos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descricao TEXT,
                categoria TEXT NOT NULL,
                preco DECIMAL(10,2) NOT NULL,
                quantidade INTEGER NOT NULL,
                estoque_minimo INTEGER DEFAULT 0,
                codigo_barras TEXT UNIQUE,
                foto TEXT,
                fornecedor_id INTEGER REFERENCES fornecedores(id) ON DELETE SET NULL,
                data_validade DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_venda TEXT NOT NULL DEFAULT 'unidade'
            )
        ''')
        
        
        # Tabela de Itens de Venda
        
        # banco_dados.py
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vendas (
                id TEXT PRIMARY KEY,
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cliente_cpf TEXT,
                cliente_nome TEXT,  
                total DECIMAL(10,2) NOT NULL,
                metodo_pagamento TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status_pagamento TEXT NOT NULL DEFAULT 'pago',
                data_vencimento DATE,
                observacao TEXT
            )
        ''')

        # Adicione a tabela venda_itens (que estava faltando):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS venda_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id TEXT NOT NULL REFERENCES vendas(id),
                produto_id INTEGER NOT NULL REFERENCES produtos(id),
                quantidade INTEGER NOT NULL,
                preco_unitario DECIMAL(10,2) NOT NULL
            )
        ''')
     
        conn.commit()



def get_user_by_id(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

def create_user(username, email, password, role='funcionario'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        hashed_pw = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, hashed_pw, role))
        conn.commit()
        return cursor.lastrowid

def get_all_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, role FROM users')
        return cursor.fetchall()

def update_user_role(user_id, new_role):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET role = ?
            WHERE id = ?
        ''', (new_role, user_id))
        conn.commit()

def delete_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        
def create_user(username, email, password, role='funcionario'):
    if len(password) < 6:
        raise ValueError("A senha deve ter pelo menos 6 caracteres")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        hashed_pw = generate_password_hash(password)
        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, hashed_pw, role))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            if 'UNIQUE' in str(e):
                if 'username' in str(e):
                    raise ValueError("Username já está em uso")
                elif 'email' in str(e):
                    raise ValueError("Email já está em uso")
            raise