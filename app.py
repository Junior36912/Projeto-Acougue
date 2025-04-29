from app_logging import registrar_log
from decorators import login_required, role_required
import os
import json
import logging
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, jsonify, render_template, request, redirect, url_for,
    send_from_directory, session, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from banco_dados import (
    init_db, get_db_connection, get_user_by_id, create_user,
    update_user_role, delete_user, get_all_users
)

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_key')
    UPLOAD_FOLDER = 'static/uploads/produtos'
    DATABASE = 'acougue.db'
app.config.from_object(Config)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ---------------------------------------------------------------
# Sistema de Autenticação
# ---------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[4]
                registrar_log(
                    user[0],
                    'login',
                    'INFO',
                    {'result': 'success'},
                    request=request
                )
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Credenciais inválidas')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        registrar_log(user_id, 'logout')  
    session.clear()
    return redirect(url_for('login'))

# ---------------------------------------------------------------
# Gestão de Produtos
# ---------------------------------------------------------------

@app.route('/produtos')
@login_required
@role_required('gerente')
def listar_produtos():
    search = request.args.get('search', '')
    categoria = request.args.get('categoria', '')
    
    query = '''SELECT p.*, f.nome as fornecedor 
               FROM produtos p 
               LEFT JOIN fornecedores f ON p.fornecedor_id = f.id 
               WHERE 1=1'''
    params = []
    
    if search:
        query += " AND (p.nome LIKE ? OR p.codigo_barras = ?)"
        params.extend([f'%{search}%', search])
    
    if categoria:
        query += " AND p.categoria = ?"
        params.append(categoria)
    
    query += " ORDER BY p.nome"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        produtos = [dict(zip([column[0] for column in cursor.description], row)) 
                    for row in cursor.fetchall()]
    
    return render_template('produtos/listar.html', 
                         produtos=produtos,
                         categorias=get_categorias())

def get_categorias():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT categoria FROM produtos")
        return [row[0] for row in cursor.fetchall()]

@app.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_produto():
    if request.method == 'POST':
        try:
            produto_data = {
                'nome': request.form['nome'],
                'descricao': request.form.get('descricao', ''),
                'categoria': request.form['categoria'],
                'preco': float(request.form['preco']),
                'quantidade': int(request.form['quantidade']),
                'estoque_minimo': int(request.form.get('estoque_minimo', 0)),
                'codigo_barras': request.form.get('codigo_barras'),
                'fornecedor_id': request.form.get('fornecedor_id'),
                'data_validade': request.form.get('data_validade')
            }
            
            foto = request.files.get('foto')
            if foto and foto.filename != '':
                filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                produto_data['foto'] = filename
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                columns = ', '.join(produto_data.keys())
                placeholders = ', '.join(['?'] * len(produto_data))
                cursor.execute(
                    f"INSERT INTO produtos ({columns}) VALUES ({placeholders})",
                    list(produto_data.values())
                )
                conn.commit()
            
            return redirect(url_for('listar_produtos'))
        
        except Exception as e:
            logging.error(f"Erro ao cadastrar produto: {str(e)}")
            return render_template('produtos/novo.html', 
                                error="Erro ao cadastrar produto",
                                fornecedores=get_fornecedores())
    
    return render_template('produtos/novo.html', fornecedores=get_fornecedores())

def get_fornecedores():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM fornecedores")
        return cursor.fetchall()

# ---------------------------------------------------------------
# Edição de Produtos
# ---------------------------------------------------------------

@app.route('/produtos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_produto(id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Busca o produto
        cursor.execute('''
            SELECT * FROM produtos WHERE id = ?
        ''', (id,))
        produto = cursor.fetchone()
        
        if not produto:
            abort(404)

        if request.method == 'POST':
            try:
                update_data = {
                    'nome': request.form['nome'],
                    'descricao': request.form.get('descricao', ''),
                    'categoria': request.form['categoria'],
                    'preco': float(request.form['preco']),
                    'quantidade': int(request.form['quantidade']),
                    'estoque_minimo': int(request.form.get('estoque_minimo', 0)),
                    'codigo_barras': request.form.get('codigo_barras'),
                    'fornecedor_id': request.form.get('fornecedor_id') or None,
                    'data_validade': request.form.get('data_validade') or None,
                    'tipo_venda': request.form['tipo_venda']
                }

                # Atualiza foto se fornecida
                foto = request.files.get('foto')
                if foto and foto.filename != '':
                    filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
                    foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    update_data['foto'] = filename
                else:
                    update_data['foto'] = produto['foto']

                # Monta a query de atualização
                set_clause = ', '.join([f"{key} = ?" for key in update_data.keys()])
                values = list(update_data.values()) + [id]

                cursor.execute(f'''
                    UPDATE produtos 
                    SET {set_clause}
                    WHERE id = ?
                ''', values)
                
                conn.commit()
                return redirect(url_for('listar_produtos'))

            except Exception as e:
                logging.error(f"Erro ao atualizar produto: {str(e)}")
                return render_template('produtos/editar.html', 
                                    produto=produto,
                                    fornecedores=get_fornecedores(),
                                    error="Erro ao atualizar produto")

        return render_template('produtos/editar.html', 
                             produto=produto,
                             fornecedores=get_fornecedores())

# ---------------------------------------------------------------
# Exclusão de Produtos
# ---------------------------------------------------------------

@app.route('/produtos/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_produto(id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Busca o produto para excluir a foto
            cursor.execute('SELECT foto FROM produtos WHERE id = ?', (id,))
            foto = cursor.fetchone()['foto']
            
            # Exclui o produto
            cursor.execute('DELETE FROM produtos WHERE id = ?', (id,))
            conn.commit()
            
            # Exclui a foto se existir
            if foto:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], foto))
                
        return redirect(url_for('listar_produtos'))
    
    except Exception as e:
        logging.error(f"Erro ao excluir produto: {str(e)}")
        return redirect(url_for('listar_produtos', error="Erro ao excluir produto"))

# ---------------------------------------------------------------
# Gestão de Fornecedores
# ---------------------------------------------------------------

@app.route('/fornecedores')
@login_required
@role_required('gerente')
def listar_fornecedores():
    search = request.args.get('search', '')
    
    query = '''SELECT * FROM fornecedores WHERE 1=1'''
    params = []
    
    if search:
        query += " AND (nome LIKE ? OR cnpj = ?)"
        params.extend([f'%{search}%', search])
    
    query += " ORDER BY nome"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        fornecedores = [dict(zip([column[0] for column in cursor.description], row)) 
                       for row in cursor.fetchall()]
    
    return render_template('fornecedores/listar.html', 
                         fornecedores=fornecedores)

@app.route('/fornecedores/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_fornecedor():
    if request.method == 'POST':
        try:
            fornecedor_data = {
                'nome': request.form['nome'],
                'cnpj': request.form['cnpj'],
                'contato': request.form['contato'],
                'endereco': request.form.get('endereco', '')
            }
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO fornecedores (nome, cnpj, contato, endereco)
                    VALUES (?, ?, ?, ?)
                ''', list(fornecedor_data.values()))
                conn.commit()
            
            return redirect(url_for('listar_fornecedores'))
        
        except sqlite3.IntegrityError as e:
            error = 'CNPJ já cadastrado' if 'UNIQUE' in str(e) else 'Erro ao cadastrar'
            return render_template('fornecedores/novo.html', 
                                  error=error,
                                  form_data=request.form)
    
    return render_template('fornecedores/novo.html')

@app.route('/fornecedores/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_fornecedor(id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM fornecedores WHERE id = ?', (id,))
        fornecedor = cursor.fetchone()
        
        if not fornecedor:
            abort(404)

        if request.method == 'POST':
            try:
                update_data = {
                    'nome': request.form['nome'],
                    'cnpj': request.form['cnpj'],
                    'contato': request.form['contato'],
                    'endereco': request.form.get('endereco', '')
                }

                cursor.execute('''
                    UPDATE fornecedores 
                    SET nome = ?, cnpj = ?, contato = ?, endereco = ?
                    WHERE id = ?
                ''', list(update_data.values()) + [id])
                
                conn.commit()
                return redirect(url_for('listar_fornecedores'))

            except sqlite3.IntegrityError as e:
                error = 'CNPJ já cadastrado' if 'UNIQUE' in str(e) else 'Erro ao atualizar'
                return render_template('fornecedores/editar.html', 
                                      fornecedor=fornecedor,
                                      error=error)

        return render_template('fornecedores/editar.html', 
                             fornecedor=fornecedor)

@app.route('/fornecedores/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_fornecedor(id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM fornecedores WHERE id = ?', (id,))
            conn.commit()
        return redirect(url_for('listar_fornecedores'))
    
    except sqlite3.IntegrityError:
        return redirect(url_for('listar_fornecedores', 
                              error='Não é possível excluir fornecedor com produtos vinculados'))
# ---------------------------------------------------------------
# Gestão de Vendas
# ---------------------------------------------------------------

@app.route('/vendas/nova', methods=['GET', 'POST'])
@login_required
def nova_venda():
    if request.method == 'POST':
        try:
            data = request.get_json()
            venda_data = {
                'cliente_cpf': data.get('cpf'),
                'metodo_pagamento': data['metodo_pagamento'],
                'itens': data['itens']
            }
            
            total = sum(item['preco'] * item['quantidade'] for item in venda_data['itens'])
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                venda_id = f"V{datetime.now().strftime('%Y%m%d%H%M%S')}"
                cursor.execute('''
                    INSERT INTO vendas (id, cliente_cpf, total, metodo_pagamento, usuario_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (venda_id, venda_data['cliente_cpf'], total, 
                     venda_data['metodo_pagamento'], session['user_id']))
                
                # Stock update loop (only once)
                for item in venda_data['itens']:
                    cursor.execute('SELECT tipo_venda FROM produtos WHERE id = ?', (item['id'],))
                    tipo = cursor.fetchone()['tipo_venda']
                    
                    if tipo == 'quilo':
                        cursor.execute('''
                            UPDATE produtos 
                            SET quantidade = quantidade - ?
                            WHERE id = ? AND tipo_venda = 'quilo'
                        ''', (item['quantidade'], item['id']))
                    else:
                        cursor.execute('''
                            UPDATE produtos 
                            SET quantidade = quantidade - ?
                            WHERE id = ? AND tipo_venda = 'unidade'
                        ''', (item['quantidade'], item['id']))
                    
                    # Insert sale item
                    cursor.execute('''
                        INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario)
                        VALUES (?, ?, ?, ?)
                    ''', (venda_id, item['id'], item['quantidade'], item['preco']))
                
                conn.commit()
            
            return jsonify({'success': True, 'venda_id': venda_id})
        
        except Exception as e:
            logging.error(f"Erro ao registrar venda: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
    
    # GET: Exibir interface de venda
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, quantidade FROM produtos")
        produtos = [dict(zip([column[0] for column in cursor.description], row)) 
                   for row in cursor.fetchall()]
    
    return render_template('vendas/nova.html', produtos=produtos)

# ---------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------

@app.route('/relatorios')
@login_required
@role_required('gerente')
def relatorios():
    return render_template('relatorios/dashboard.html')

@app.route('/relatorios/vendas')
@login_required
@role_required('gerente')
def relatorio_vendas():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = '''
        SELECT v.id, v.data, v.total, v.metodo_pagamento, u.username as operador
        FROM vendas v
        JOIN users u ON v.usuario_id = u.id
        WHERE 1=1
    '''
    params = []
    
    if start_date:
        query += " AND v.data >= ?"
        params.append(start_date)
    
    if end_date:
        query += " AND v.data <= ?"
        params.append(end_date)
    
    query += " ORDER BY v.data DESC"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        vendas = [dict(zip([column[0] for column in cursor.description], row)) 
                 for row in cursor.fetchall()]
    
    return render_template('relatorios/vendas.html', vendas=vendas)

# ---------------------------------------------------------------
# Admin (Gerente)
# ---------------------------------------------------------------

@app.route('/admin/usuarios')
@login_required
@role_required('gerente')
def admin_usuarios():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, role FROM users")
        usuarios = [dict(zip([column[0] for column in cursor.description], row)) 
                   for row in cursor.fetchall()]
    
    return render_template('admin/usuarios.html', usuarios=usuarios)

@app.route('/admin/estoque')
@login_required
@role_required('gerente')
def admin_estoque():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT nome, quantidade, estoque_minimo 
            FROM produtos 
            ORDER BY quantidade ASC
        ''')
        estoque = [dict(zip([column[0] for column in cursor.description], row)) 
                  for row in cursor.fetchall()]
    
    return render_template('admin/estoque.html', estoque=estoque)

# ---------------------------------------------------------------
# Dashboard Principal
# ---------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'gerente':
        return render_template('dashboard_gerente.html')
    else:
        # Dashboard para funcionários
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT nome, quantidade, estoque_minimo 
                FROM produtos 
                WHERE quantidade < estoque_minimo
                ORDER BY quantidade ASC
            ''')
            alertas_estoque = cursor.fetchall()
        
        return render_template('dashboard_funcionario.html', alertas=alertas_estoque)

# ---------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------

@app.context_processor
def utility_processor():
    return {
        'format_currency': lambda value: f"R$ {value:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'),
        'now': datetime.now
    }

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)