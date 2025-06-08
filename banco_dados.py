import sqlite3
import os
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from flask import current_app
from datetime import datetime
import logging

DB_PATH = os.environ.get('DB_PATH', 'acougue.db')

@contextmanager
def get_db_connection():
    db_path = os.environ.get('DB_PATH', 'acougue.db')
    # Usar URI para permitir compartilhamento em memória
    conn = sqlite3.connect(f'file:{db_path}', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Inicialização completa do banco de dados, criando tabelas e triggers"""
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
                preco NUMERIC NOT NULL,
                quantidade INTEGER NOT NULL,
                estoque_minimo INTEGER DEFAULT 0,
                codigo_barras TEXT UNIQUE,
                foto TEXT,
                fornecedor_id INTEGER REFERENCES fornecedores(id)
                  ON DELETE SET NULL ON UPDATE CASCADE,
                data_validade DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_venda TEXT NOT NULL DEFAULT 'unidade'
            )
        ''')
        # Within init_db() function, replace the trigger creation with:
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trg_update_produtos_updated_at
            AFTER UPDATE ON produtos
            FOR EACH ROW
            BEGIN
                UPDATE produtos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;
        ''')
        # Tabela de Vendas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vendas (
                id TEXT PRIMARY KEY,
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cliente_cpf TEXT,
                cliente_nome TEXT,
                total NUMERIC NOT NULL,
                metodo_pagamento TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES users(id)
                  ON DELETE CASCADE ON UPDATE CASCADE,
                status_pagamento TEXT NOT NULL DEFAULT 'pago',
                data_vencimento DATE,
                observacao TEXT
            )
        ''')
        # Tabela de Itens de Venda
        # No arquivo banco_dados.py, na criação da tabela venda_itens, altere:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS venda_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id TEXT NOT NULL REFERENCES vendas(id)
                ON DELETE CASCADE ON UPDATE CASCADE, 
                produto_id INTEGER NOT NULL REFERENCES produtos(id)
                ON DELETE CASCADE ON UPDATE CASCADE, 
                quantidade INTEGER NOT NULL,
                preco_unitario NUMERIC NOT NULL
            )
        ''')
        conn.commit()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                action TEXT NOT NULL,
                level TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT
            )
        ''')
        conn.commit()




def get_fornecedores(search=None, page=1, per_page=10):
    query = "SELECT * FROM fornecedores"
    params = []
    if search:
        query += " WHERE nome LIKE ? OR cnpj LIKE ?"
        params.extend([f'%{search}%', f'%{search}%'])
    query += " ORDER BY nome LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


    

# -----------------------
# CRUD: Users
# -----------------------
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

def get_user_by_id(user_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()

def get_user_by_username(username):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()

def get_all_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, role FROM users')
        return cursor.fetchall()

def update_user(user_id, **kwargs):
    fields = []
    params = []
    for key, value in kwargs.items():
        if key == 'password':
            key = 'password_hash'
            value = generate_password_hash(value)
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(user_id)
    with get_db_connection() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

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
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

# -----------------------
# CRUD: Fornecedores
# -----------------------

# Função create_fornecedor atualizada
def create_fornecedor(nome, cnpj, contato, endereco=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO fornecedores (nome, cnpj, contato, endereco) VALUES (?, ?, ?, ?)",
                (nome, cnpj, contato, endereco)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            if 'UNIQUE' in str(e):
                if 'cnpj' in str(e):
                    raise ValueError("CNPJ já cadastrado")
            raise ValueError("Erro ao criar fornecedor")

# Função update_fornecedor atualizada
def update_fornecedor(fornecedor_id, **kwargs):
    fields = []
    params = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(fornecedor_id)
    with get_db_connection() as conn:
        try:
            conn.execute(f"UPDATE fornecedores SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
        except sqlite3.IntegrityError as e:
            if 'UNIQUE' in str(e) and 'cnpj' in str(e):
                raise ValueError("CNPJ já cadastrado")
            raise ValueError("Erro ao atualizar fornecedor")

def get_fornecedor_by_id(fornecedor_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM fornecedores WHERE id = ?", (fornecedor_id,))
        return cursor.fetchone()

def get_all_fornecedores():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM fornecedores ORDER BY nome")
        return cursor.fetchall()

def delete_fornecedor(fornecedor_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM fornecedores WHERE id = ?", (fornecedor_id,))
        conn.commit()

# -----------------------
# CRUD: Produtos
# -----------------------
def create_produto(nome, descricao, categoria, preco, quantidade,
                    estoque_minimo=0, codigo_barras=None, foto_file=None,
                    fornecedor_id=None, data_validade=None, tipo_venda='unidade'):
    foto_filename = None
    if foto_file:
        filename = secure_filename(foto_file.filename)
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        foto_file.save(upload_path)
        foto_filename = filename
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO produtos 
            (nome, descricao, categoria, preco, quantidade, estoque_minimo,
             codigo_barras, foto, fornecedor_id, data_validade, tipo_venda)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (nome, descricao, categoria, preco, quantidade, estoque_minimo,
             codigo_barras, foto_filename, fornecedor_id, data_validade, tipo_venda)
        )
        conn.commit()
        return cursor.lastrowid

def get_produto_by_id(produto_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,))
        return cursor.fetchone()

def update_produto(produto_id, **kwargs):
    fields = []
    params = []
    # handle foto update
    if 'foto_file' in kwargs and kwargs['foto_file']:
        foto_file = kwargs.pop('foto_file')
        filename = secure_filename(foto_file.filename)
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        foto_file.save(upload_path)
        fields.append('foto = ?')
        params.append(filename)
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(produto_id)
    with get_db_connection() as conn:
        conn.execute(f"UPDATE produtos SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

def delete_produto(produto_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        conn.commit()

def excluir_produto(produto_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Remove verificação de venda_itens
        cursor.execute('SELECT foto FROM produtos WHERE id = ?', (produto_id,))
        row = cursor.fetchone()
        foto = row['foto'] if row else None
        
        try:
            cursor.execute('DELETE FROM produtos WHERE id = ?', (produto_id,))
            conn.commit()
        except sqlite3.IntegrityError as e:
            if 'FOREIGN KEY' in str(e):
                raise ValueError("Produto vinculado a registros dependentes")
            raise
    
    if foto:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], foto))
        except Exception as rm_err:
            logging.error(f"Erro ao remover foto: {rm_err}")

# banco_dados.py - Atualização de queries com JOIN
def get_all_produtos():
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT p.*, f.nome as fornecedor 
            FROM produtos p
            LEFT JOIN fornecedores f ON p.fornecedor_id = f.id
            ORDER BY p.nome
        """)
        return [dict(row) for row in cursor.fetchall()]
    
def listar_produtos(search: str = '', categoria: str = '', page: int = 1, per_page: int = 10):
    # Query principal
    base_query = '''
        SELECT p.*, f.nome AS fornecedor
        FROM produtos AS p
        LEFT JOIN fornecedores AS f ON p.fornecedor_id = f.id
        WHERE 1=1
    '''
    count_query = 'SELECT COUNT(*) as total FROM produtos p WHERE 1=1'
    
    params = []
    count_params = []

    # Filtros
    if search:
        base_query += " AND (p.nome LIKE ? OR p.codigo_barras = ?)"
        count_query += " AND (p.nome LIKE ? OR p.codigo_barras = ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search])
        count_params.extend([search_term, search])
    
    if categoria:
        base_query += " AND p.categoria = ?"
        count_query += " AND p.categoria = ?"
        params.append(categoria)
        count_params.append(categoria)

    # Ordenação e paginação
    base_query += " ORDER BY p.nome LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])

    with get_db_connection() as conn:
        # Total de registros
        cursor = conn.cursor()
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        # Dados paginados
        cursor.execute(base_query, params)
        produtos = [dict(row) for row in cursor.fetchall()]
        
        return produtos, total

# -----------------------
# CRUD: Vendas
# -----------------------
def create_venda(venda_id, cliente_cpf, cliente_nome, total,
                 metodo_pagamento, usuario_id, status_pagamento='pago',
                 data_vencimento=None, observacao=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO vendas 
            (id, cliente_cpf, cliente_nome, total, metodo_pagamento,
             usuario_id, status_pagamento, data_vencimento, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (venda_id, cliente_cpf, cliente_nome, total, metodo_pagamento,
             usuario_id, status_pagamento, data_vencimento, observacao)
        )
        conn.commit()
        return venda_id

def get_venda_by_id(venda_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,))
        return cursor.fetchone()

def get_all_vendas():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM vendas ORDER BY data DESC")
        return cursor.fetchall()

def update_venda(venda_id, **kwargs):
    fields = []
    params = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(venda_id)
    with get_db_connection() as conn:
        conn.execute(f"UPDATE vendas SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

def delete_venda(venda_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))
        conn.commit()

def processar_venda(venda_id, venda_data, usuario_id):
    """Insere venda + itens e atualiza estoque em uma transação."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        conn.execute('BEGIN')
        total = sum(item['preco'] * item['quantidade'] for item in venda_data['itens'])
        
        # MODIFICADO: Incluir data_venda na query
        cursor.execute(
            """
            INSERT INTO vendas
            (id, cliente_cpf, cliente_nome, total, metodo_pagamento,
            usuario_id, status_pagamento, data_vencimento, observacao, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                venda_id,
                venda_data['cliente_cpf'],
                venda_data['cliente_nome'],
                total,
                venda_data['metodo_pagamento'],
                usuario_id,
                venda_data['status_pagamento'],
                venda_data.get('data_vencimento'),
                venda_data.get('observacao'),
                venda_data.get('data_venda', datetime.now())  # Usa data atual se não informada
            )
        )
        # itens + estoque
        for item in venda_data['itens']:
            cursor.execute(
                "INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario) VALUES (?, ?, ?, ?)",
                (venda_id, item['id'], item['quantidade'], item['preco'])
            )
            cursor.execute(
                "UPDATE produtos SET quantidade = quantidade - ? WHERE id = ?",
                (item['quantidade'], item['id'])
            )
        conn.commit()
    return True

def listar_produtos_simples():
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, nome, preco, quantidade, tipo_venda, foto 
            FROM produtos
        """)
        return [dict(row) for row in cursor.fetchall()]

# -----------------------
# CRUD: Venda Itens
# -----------------------
def create_venda_item(venda_id, produto_id, quantidade, preco_unitario):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario)
            VALUES (?, ?, ?, ?)
            """,
            (venda_id, produto_id, quantidade, preco_unitario)
        )
        conn.commit()
        return cursor.lastrowid

def get_venda_items(venda_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM venda_itens WHERE venda_id = ?", (venda_id,))
        return cursor.fetchall()

def update_venda_item(item_id, **kwargs):
    fields = []
    params = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        params.append(value)
    params.append(item_id)
    with get_db_connection() as conn:
        conn.execute(f"UPDATE venda_itens SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()


def delete_venda_item(item_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM venda_itens WHERE id = ?", (item_id,))
        conn.commit()


# ================================================================================

def get_all_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, role FROM users')
        return cursor.fetchall()


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
        
# ---------------------------------------------------------------
# CRUD de Produtos
# ---------------------------------------------------------------


def inserir_produto(form: dict, foto):
    # Validações básicas
    nome = form.get('nome', '').strip()
    if not nome:
        raise ValueError('Campo obrigatório faltando: nome')
    try:
        preco = float(form.get('preco', 0))
        if preco <= 0:
            raise ValueError()
    except:
        raise ValueError('Preço inválido. Deve ser um número positivo.')
    try:
        quantidade = int(form.get('quantidade', 0))
        if quantidade < 0:
            raise ValueError()
    except:
        raise ValueError('Quantidade inválida. Deve ser um inteiro não-negativo.')

    # Preparar dados
    produto_data = {
        'nome': nome,
        'descricao': form.get('descricao', '').strip(),
        'categoria': form.get('categoria'),
        'preco': preco,
        'quantidade': quantidade,
        'estoque_minimo': int(form.get('estoque_minimo', 0)),
        'codigo_barras': form.get('codigo_barras') or None,
        'fornecedor_id': form.get('fornecedor_id') or None,
        'data_validade': form.get('data_validade') or None,
        'tipo_venda': form.get('tipo_venda'),
        'foto': None
    }

    # Processar upload de imagem
    saved_filename = None
    if foto and foto.filename:
        filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        path = os.path.join(upload_folder, filename)
        foto.save(path)
        saved_filename = filename
        produto_data['foto'] = filename

    # Inserir no banco
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cols = [k for k in produto_data.keys()]
            placeholders = ','.join(['?'] * len(cols))
            sql = f"INSERT INTO produtos ({','.join(cols)}) VALUES ({placeholders})"
            cursor.execute(sql, [produto_data[k] for k in cols])
            conn.commit()
    except Exception as e:
        # remover imagem salva em caso de erro
        if saved_filename:
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename))
            except Exception as rm_err:
                logging.error(f"Falha ao remover arquivo: {rm_err}")
        raise


def atualizar_produto(produto_id: int, form: dict, foto):
    # Buscar existente
    existing = get_produto_by_id(produto_id)
    if not existing:
        raise ValueError('Produto não encontrado')
    update_data = {}
    # Validar e montar dados
    update_data['nome'] = form.get('nome', '').strip() or existing['nome']
    update_data['descricao'] = form.get('descricao', '').strip()
    update_data['categoria'] = form.get('categoria') or existing['categoria']
    try:
        preco = float(form.get('preco', existing['preco']))
        if preco <= 0:
            raise
        update_data['preco'] = preco
    except:
        raise ValueError('Preço inválido. Deve ser um número positivo.')
    try:
        quantidade = int(form.get('quantidade', existing['quantidade']))
        if quantidade < 0:
            raise
        update_data['quantidade'] = quantidade
    except:
        raise ValueError('Quantidade inválida. Deve ser um inteiro não-negativo.')
    update_data['estoque_minimo'] = int(form.get('estoque_minimo', existing['estoque_minimo']))
    update_data['codigo_barras'] = form.get('codigo_barras') or existing['codigo_barras']
    update_data['fornecedor_id'] = form.get('fornecedor_id') or existing['fornecedor_id']
    update_data['data_validade'] = form.get('data_validade') or existing['data_validade']
    update_data['tipo_venda'] = form.get('tipo_venda') or existing['tipo_venda']

    # Processar nova imagem
    new_filename = None
    if foto and foto.filename:
        filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        path = os.path.join(upload_folder, filename)
        foto.save(path)
        new_filename = filename
        update_data['foto'] = filename
    else:
        update_data['foto'] = existing['foto']

    # Montar UPDATE
    cols = list(update_data.keys())
    set_clause = ', '.join([f"{col} = ?" for col in cols])
    params = [update_data[col] for col in cols] + [produto_id]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE produtos SET {set_clause} WHERE id = ?', params)
            conn.commit()
    except Exception as e:
        # rollback imagem nova
        if new_filename:
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], new_filename))
            except Exception as rm_err:
                logging.error(f"Falha ao remover arquivo: {rm_err}")
        raise

    # remover imagem antiga
    if new_filename and existing['foto']:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], existing['foto']))
        except Exception as rm_err:
            logging.error(f"Falha ao remover arquivo antigo: {rm_err}")


def excluir_produto(produto_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT foto FROM produtos WHERE id = ?', (produto_id,))
        row = cursor.fetchone()
        foto = row['foto'] if row else None
        cursor.execute('DELETE FROM produtos WHERE id = ?', (produto_id,))
        conn.commit()
    # remover foto
    if foto:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], foto))
        except Exception as rm_err:
            logging.error(f"Falha ao remover arquivo: {rm_err}")
            
def get_fornecedores(search=None):
    """Retorna lista de fornecedores com todos os campos, filtrados por busca (nome ou CNPJ)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM fornecedores"
        params = []
        if search:
            query += " WHERE nome LIKE ? OR cnpj LIKE ?"
            search_term = f"%{search}%"
            params.extend([search_term, search_term])
        query += " ORDER BY nome"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_categorias():
    """Retorna lista distinta de categorias de produtos."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT categoria FROM produtos ORDER BY categoria')
        return [row['categoria'] for row in cursor.fetchall()]
    
# -----------------------
# CRUD: Users
# -----------------------
def get_all_users():
    """Retorna todos os usuários com campos essenciais"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT id, username, email, role FROM users ORDER BY username'
        )
        return [dict(row) for row in cursor.fetchall()]

# -----------------------
# CRUD: Produtos
# -----------------------


# -----------------------
# CRUD: Vendas
# -----------------------
def get_all_vendas():
    """Retorna todas as vendas ordenadas pela data decrescente"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM vendas ORDER BY data DESC'
        )
        return [dict(row) for row in cursor.fetchall()]

# -----------------------
# CRUD: Itens de Venda
# -----------------------
def get_venda_items(venda_id=None):
    """Se venda_id for None, retorna todos itens; caso contrário, filtra por venda_id"""
    query = 'SELECT * FROM venda_itens'
    params = []
    if venda_id is not None:
        query += ' WHERE venda_id = ?'
        params.append(venda_id)
    with get_db_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def fetch_vendas_prazo(cliente_filter=None, letra_filter=None):
    """Retorna lista de vendas a prazo e lista de clientes distintos."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # obter clientes
        cursor.execute(
            """
            SELECT DISTINCT cliente_nome 
            FROM vendas 
            WHERE metodo_pagamento = 'pagamento_prazo' 
            ORDER BY cliente_nome
            """
        )
        clientes = [row['cliente_nome'] for row in cursor.fetchall()]

        # consulta principal
        base = '''
            SELECT
                v.id,
                v.cliente_nome,
                v.data,
                v.total,
                v.status_pagamento,
                v.data_vencimento,
                v.observacao,
                p.nome as produto_nome,
                vi.quantidade,
                vi.preco_unitario
            FROM vendas v
            LEFT JOIN venda_itens vi ON v.id = vi.venda_id
            LEFT JOIN produtos p ON vi.produto_id = p.id
            WHERE v.metodo_pagamento = 'pagamento_prazo'
        '''
        params = []
        if cliente_filter:
            base += " AND v.cliente_nome = ?"
            params.append(cliente_filter)
        elif letra_filter and len(letra_filter) == 1:
            base += " AND v.cliente_nome LIKE ?"
            params.append(f"{letra_filter}%")
        base += '''
            ORDER BY
              CASE WHEN v.status_pagamento = 'pendente' THEN 0 ELSE 1 END,
              v.data_vencimento ASC,
              v.cliente_nome ASC
        '''
        cursor.execute(base, params)
        rows = cursor.fetchall()

    # montagem do dicionário de vendas
    from collections import defaultdict
    vendas_map = defaultdict(lambda: {
        'id': None, 'cliente_nome': '', 'data': None, 'total': 0,
        'status_pagamento': '', 'data_vencimento': None,
        'observacao': '', 'vencida': False, 'itens': []
    })
    hoje = datetime.now().date()
    for r in rows:
        vid = r['id']
        # Trata datas com e sem horário
        if r['data']:
            try:
                data = datetime.strptime(r['data'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                data = datetime.strptime(r['data'], '%Y-%m-%d')  # Formato sem horário
        else:
            data = None
        dv = (datetime.strptime(r['data_vencimento'], '%Y-%m-%d').date()
              if r['data_vencimento'] else None)
        vencida = (r['status_pagamento']=='pendente' and dv and dv < hoje)
        vendas_map[vid].update({
            'id': vid, 'cliente_nome': r['cliente_nome'], 'data': data,
            'total': r['total'], 'status_pagamento': r['status_pagamento'],
            'data_vencimento': dv, 'observacao': r['observacao'], 'vencida': vencida
        })
        if r['produto_nome']:
            vendas_map[vid]['itens'].append({
                'nome': r['produto_nome'],
                'quantidade': r['quantidade'],
                'preco_unitario': r['preco_unitario']
            })
    vendas = list(vendas_map.values())
    pendentes = [v for v in vendas if v['status_pagamento']=='pendente']
    return vendas, clientes, len(vendas), len(pendentes), sum(v['total'] for v in pendentes)


def marcar_venda_pago(venda_id):
    """Marca uma venda a prazo como paga."""
    return update_venda(venda_id, status_pagamento='pago')


def adicionar_observacao_venda(venda_id, observacao):
    """Adiciona ou atualiza observação de uma venda."""
    return update_venda(venda_id, observacao=observacao)

# Adicione esta função no banco_dados.py
def listar_logs(page=1, per_page=20, search=None, level=None, user_id=None, action=None, start_date=None, end_date=None):
    offset = (page - 1) * per_page
    query = "SELECT * FROM logs WHERE 1=1"
    params = []

    if search:
        query += " AND (action LIKE ? OR details LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    if level:
        query += " AND level = ?"
        params.append(level)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if start_date:
        query += " AND DATE(timestamp) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND DATE(timestamp) <= ?"
        params.append(end_date)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        logs = [dict(row) for row in cursor.fetchall()]

        # Contar total de registros
        count_query = "SELECT COUNT(*) as total FROM logs WHERE 1=1"
        count_params = params[:-2]  # Remove LIMIT e OFFSET
        if count_params:
            cursor.execute(count_query, count_params)
        else:
            cursor.execute(count_query)
        total = cursor.fetchone()['total']

        return logs, total