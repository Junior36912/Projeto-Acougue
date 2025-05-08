from collections import defaultdict
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

# Garantir caminho absoluto para upload
app.config['UPLOAD_FOLDER'] = os.path.abspath(app.config['UPLOAD_FOLDER'])
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

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
                return redirect(url_for('index'))
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

def get_fornecedores():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM fornecedores")
        return cursor.fetchall()

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
        foto = request.files.get('foto')
        saved_filename = None  # Para controle de rollback

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
                'data_validade': request.form.get('data_validade'),
                'tipo_venda': request.form['tipo_venda']
            }

            # Processar upload da imagem
            if foto and foto.filename != '':
                filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                foto.save(upload_path)
                saved_filename = filename
                produto_data['foto'] = filename

            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Validação de campos obrigatórios
                required_fields = ['nome', 'categoria', 'preco', 'quantidade', 'tipo_venda']
                for field in required_fields:
                    if not produto_data.get(field):
                        raise ValueError(f"Campo obrigatório faltando: {field}")

                # Inserir no banco
                cursor.execute(
                    """INSERT INTO produtos (
                        nome, descricao, categoria, preco, quantidade,
                        estoque_minimo, codigo_barras, fornecedor_id,
                        data_validade, foto, tipo_venda
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        produto_data['nome'],
                        produto_data['descricao'],
                        produto_data['categoria'],
                        produto_data['preco'],
                        produto_data['quantidade'],
                        produto_data['estoque_minimo'],
                        produto_data['codigo_barras'],
                        produto_data['fornecedor_id'],
                        produto_data['data_validade'],
                        produto_data.get('foto'),
                        produto_data['tipo_venda']
                    )
                )
                conn.commit()

            return redirect(url_for('listar_produtos'))

        except Exception as e:
            # Rollback de arquivo em caso de erro
            if saved_filename:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], saved_filename))
                except Exception as file_error:
                    logging.error(f"Erro ao remover arquivo temporário: {file_error}")

            logging.error(f"Erro ao cadastrar produto: {str(e)}", exc_info=True)
            return render_template('produtos/novo.html',
                                error=f"Erro ao cadastrar: {str(e)}",
                                fornecedores=get_fornecedores(),
                                form_data=request.form)
    
    return render_template('produtos/novo.html', fornecedores=get_fornecedores())


@app.route('/produtos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_produto(id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM produtos WHERE id = ?', (id,))
        produto = cursor.fetchone()

        if not produto:
            abort(404)

        if request.method == 'POST':
            old_foto = produto['foto']
            new_filename = None
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

                # Processar nova imagem
                foto = request.files.get('foto')
                if foto and foto.filename != '':
                    # Gerar novo nome e salvar
                    filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
                    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    foto.save(upload_path)
                    new_filename = filename
                    update_data['foto'] = filename
                else:
                    update_data['foto'] = old_foto

                # Atualizar banco
                set_clause = ', '.join([f"{key} = ?" for key in update_data.keys()])
                values = list(update_data.values()) + [id]

                cursor.execute(f'UPDATE produtos SET {set_clause} WHERE id = ?', values)
                conn.commit()

                # Remover imagem antiga após commit bem-sucedido
                if new_filename and old_foto:
                    try:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_foto)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception as e:
                        logging.error(f"Erro ao remover imagem antiga: {str(e)}")

                return redirect(url_for('listar_produtos'))

            except Exception as e:
                # Rollback de arquivo em caso de erro
                if new_filename:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                    except Exception as file_error:
                        logging.error(f"Erro ao remover arquivo temporário: {file_error}")

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

# função de validação de CNPJ
def validar_cnpj(cnpj):
    cnpj = ''.join(filter(str.isdigit, cnpj))
    
    if len(cnpj) != 14:
        return False
    
    # Verifica se todos os dígitos são iguais
    if len(set(cnpj)) == 1:
        return False
    
    # Cálculo do primeiro dígito verificador
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    dig1 = 11 - (soma % 11)
    dig1 = dig1 if dig1 < 10 else 0
    
    # Cálculo do segundo dígito verificador
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    dig2 = 11 - (soma % 11)
    dig2 = dig2 if dig2 < 10 else 0
    
    # Verifica se os dígitos calculados coincidem com os informados
    return int(cnpj[12]) == dig1 and int(cnpj[13]) == dig2


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
                    'cnpj': request.form['cnpj'].replace('.', '').replace('/', '').replace('-', ''),
                    'contato': request.form['contato'],
                    'endereco': request.form.get('endereco', '')
                }

                # Validação do CNPJ
                if not validar_cnpj(update_data['cnpj']):
                    return render_template('fornecedores/editar.html',
                                        fornecedor=fornecedor,
                                        error='CNPJ inválido')

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

            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Verificar se o usuário existe
                user_id = session.get('user_id')
                if not user_id:
                    return jsonify({'success': False, 'error': 'Usuário não autenticado'}), 401
                
                cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                if not user:
                    return jsonify({'success': False, 'error': 'Usuário inválido'}), 400
            
            
            data = request.get_json()
            metodo_pagamento = data['metodo_pagamento']
            data_vencimento = data.get('data_vencimento')

            # Validação server-side
            if metodo_pagamento == 'pagamento_prazo':
                if not data_vencimento:
                    return jsonify({'success': False, 'error': 'Data de vencimento obrigatória'})
                
                vencimento = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
                if vencimento < datetime.today().date():
                    return jsonify({'success': False, 'error': 'Data de vencimento inválida'})

            cliente_cpf = data.get('cpf') 
            cliente_nome = data.get('nome_cliente') 
            status_pagamento = 'pendente' if metodo_pagamento == 'pagamento_prazo' else 'pago'

            venda_data = {
                'cliente_cpf': cliente_cpf,
                'cliente_nome': cliente_nome,
                'metodo_pagamento': metodo_pagamento,
                'itens': data['itens'],
                'status_pagamento': status_pagamento,
                'data_vencimento': data_vencimento
            }
            
            total = sum(item['preco'] * item['quantidade'] for item in venda_data['itens'])
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                venda_id = f"V{datetime.now().strftime('%Y%m%d%H%M%S')}"
                cursor.execute('''
                    INSERT INTO vendas
                    (id, cliente_cpf, cliente_nome, total, metodo_pagamento, 
                    usuario_id, status_pagamento, data_vencimento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    venda_id,
                    venda_data['cliente_cpf'],
                    venda_data['cliente_nome'],
                    total,
                    venda_data['metodo_pagamento'],
                    user_id,  
                    venda_data['status_pagamento'],
                    venda_data['data_vencimento']
                ))
                
                for item in venda_data['itens']:
                    cursor.execute('''
                        INSERT INTO venda_itens 
                        (venda_id, produto_id, quantidade, preco_unitario)
                        VALUES (?, ?, ?, ?)
                    ''', (venda_id, item['id'], item['quantidade'], item['preco']))
                    
                    # Atualiza estoque apenas se for pagamento à vista
                    if status_pagamento == 'pago' or status_pagamento == 'pagamento_prazo':
                        cursor.execute('''
                            UPDATE produtos 
                            SET quantidade = quantidade - ?
                            WHERE id = ?
                        ''', (item['quantidade'], item['id']))
                
                        
                # Verificar existência dos produtos
                for item in venda_data['itens']:
                    cursor.execute('SELECT id FROM produtos WHERE id = ?', (item['id'],))
                    produto = cursor.fetchone()
                    if not produto:
                        return jsonify({'success': False, 'error': f'Produto ID {item["id"]} não encontrado'}), 400
                
                conn.commit()
            
            return jsonify({'success': True, 'venda_id': venda_id})
        
        except Exception as e:
            logging.error(f"Erro ao registrar venda: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
    
    else:  # Adicionar tratamento para GET
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nome, preco, quantidade, tipo_venda FROM produtos")
            produtos = [dict(zip([column[0] for column in cursor.description], row)) 
                      for row in cursor.fetchall()]
        
        return render_template('vendas/nova.html', produtos=produtos)
    
 
@app.route('/vendas/pagamento_prazo/pagar/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def pagar_pagamento_prazo(venda_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE vendas
                SET status_pagamento = 'pago'
                WHERE id = ? AND metodo_pagamento = 'pagamento_prazo' AND status_pagamento = 'pendente'
                RETURNING *
            ''', (venda_id,))
            
            venda = cursor.fetchone()
            if not venda:
                return redirect(url_for('listar_fiado', error='Venda não encontrada ou já paga'))
            
            # Baixar estoque após pagamento
            cursor.execute('''
                SELECT produto_id, quantidade 
                FROM venda_itens 
                WHERE venda_id = ?
            ''', (venda_id,))
            
            for item in cursor.fetchall():
                cursor.execute('''
                    UPDATE produtos 
                    SET quantidade = quantidade - ?
                    WHERE id = ?
                ''', (item['quantidade'], item['produto_id']))
            
            conn.commit()
            
        return redirect(url_for('listar_fiado', success=True))
    
    except Exception as e:
        logging.error(f"Erro ao pagar fiado: {str(e)}")
        return redirect(url_for('listar_fiado', error='Erro ao processar pagamento'))

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
    success = request.args.get('success')
    error = request.args.get('error')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, role FROM users")
        usuarios = [dict(zip([column[0] for column in cursor.description], row)) 
                   for row in cursor.fetchall()]
    
    return render_template('admin/usuarios.html', 
                         usuarios=usuarios,
                         success=success,
                         error=error)

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

# Modificações no app.py - Rota /dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'gerente':
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Métricas Principais
            cursor.execute("SELECT COUNT(*) as total FROM vendas")
            total_vendas = cursor.fetchone()['total']

            cursor.execute("SELECT SUM(total) as total_hoje FROM vendas WHERE DATE(data) = DATE('now')")
            total_hoje = cursor.fetchone()['total_hoje'] or 0

            cursor.execute("SELECT COUNT(*) as hoje FROM vendas WHERE DATE(data) = DATE('now')")
            vendas_hoje = cursor.fetchone()['hoje']

            cursor.execute("SELECT COUNT(*) as falta FROM produtos WHERE quantidade < estoque_minimo")
            total_produtos_falta = cursor.fetchone()['falta']

            # Métricas Financeiras
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(total), 0) as receita_mensal,
                    COALESCE(AVG(total), 0) as media_ticket
                FROM vendas 
                WHERE strftime('%Y-%m', data) = strftime('%Y-%m', 'now')
            """)
            financeiro = cursor.fetchone()
            receita_mensal = financeiro['receita_mensal']
            media_ticket = financeiro['media_ticket']

            # Métricas de Pagamento
            cursor.execute("""
                SELECT metodo_pagamento, COUNT(*) as total, SUM(total) as valor_total
                FROM vendas
                GROUP BY metodo_pagamento
            """)
            sales_por_metodo = [dict(row) for row in cursor.fetchall()]

            # Tendência de Vendas
            cursor.execute("""
                SELECT 
                    DATE(data) as data,
                    COUNT(*) as quantidade_vendas,
                    SUM(total) as total_vendas
                FROM vendas
                WHERE data >= DATE('now', '-7 days')
                GROUP BY DATE(data)
                ORDER BY data ASC
            """)
            vendas_semana = [dict(row) for row in cursor.fetchall()]

            # Dados de Estoque
            cursor.execute('''
                SELECT nome, quantidade, estoque_minimo, preco
                FROM produtos
                WHERE quantidade < estoque_minimo
                ORDER BY quantidade ASC
            ''')
            alertas_estoque = [dict(row) for row in cursor.fetchall()]

            valor_estoque = sum(item['quantidade'] * item['preco'] for item in alertas_estoque)

            # Performance de Produtos
            cursor.execute('''
                SELECT 
                    p.nome,
                    SUM(vi.quantidade) as quantidade_vendida,
                    SUM(vi.quantidade * vi.preco_unitario) as receita_total
                FROM venda_itens vi
                JOIN produtos p ON vi.produto_id = p.id
                GROUP BY vi.produto_id
                ORDER BY quantidade_vendida DESC
                LIMIT 5
            ''')
            ranking_produtos = [dict(row) for row in cursor.fetchall()]

        return render_template('dashboard_gerente.html',
                             total_vendas=total_vendas,
                             vendas_hoje=vendas_hoje,
                             total_produtos_falta=total_produtos_falta,
                             receita_mensal=receita_mensal,
                             media_ticket=media_ticket,
                             total_hoje=total_hoje,
                             sales_por_metodo=sales_por_metodo,
                             vendas_semana=vendas_semana,
                             alertas_estoque=alertas_estoque,
                             valor_estoque=valor_estoque,
                             ranking_produtos=ranking_produtos)
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


@app.template_filter('format_currency')
def format_currency(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"


@app.route('/vendas/listar_vendas_prazo')
@login_required
@role_required('gerente')
def listar_vendas_prazo():
    letra_filter = request.args.get('letra', '').upper()
    cliente_filter = request.args.get('cliente_filter')  # Novo filtro
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Obter lista de clientes distintos
        cursor.execute("""
            SELECT DISTINCT cliente_nome 
            FROM vendas 
            WHERE metodo_pagamento = 'pagamento_prazo' 
            ORDER BY cliente_nome
        """)
        clientes = [row['cliente_nome'] for row in cursor.fetchall()]
        
        # Consulta principal
        base_query = '''
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
        # Aplicar filtro de cliente primeiro
        if cliente_filter:
            base_query += " AND v.cliente_nome = ?"
            params.append(cliente_filter)
        elif letra_filter and len(letra_filter) == 1:
            base_query += " AND v.cliente_nome LIKE ?"
            params.append(f"{letra_filter}%")
        
        # Ordenação mantida
        base_query += '''
            ORDER BY 
                CASE WHEN v.status_pagamento = 'pendente' THEN 0 ELSE 1 END,
                v.data_vencimento ASC,
                v.cliente_nome ASC
        '''
        
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
    
    vendas_dict = defaultdict(lambda: {
        'id': None,
        'cliente_nome': '',
        'data': None,
        'total': 0,
        'status_pagamento': '',
        'data_vencimento': None,
        'observacao': '',
        'vencida': False,
        'itens': []
    })
    
    hoje = datetime.now().date()
    
    for row in rows:
        venda_id = row['id']
        data = datetime.strptime(row['data'], '%Y-%m-%d %H:%M:%S') if row['data'] else None
        data_vencimento = datetime.strptime(row['data_vencimento'], '%Y-%m-%d').date() if row['data_vencimento'] else None
        
        vencida = (
            row['status_pagamento'] == 'pendente' and 
            data_vencimento and 
            data_vencimento < hoje
        )
        
        vendas_dict[venda_id].update({
            'id': venda_id,
            'cliente_nome': row['cliente_nome'],
            'data': data,
            'total': row['total'],
            'status_pagamento': row['status_pagamento'],
            'data_vencimento': data_vencimento,
            'observacao': row['observacao'],
            'vencida': vencida
        })
        
        if row['produto_nome']:
            vendas_dict[venda_id]['itens'].append({
                'nome': row['produto_nome'],
                'quantidade': row['quantidade'],
                'preco_unitario': row['preco_unitario']
            })
    
    vendas = list(vendas_dict.values())
    
    total_vendas = len(vendas)
    total_pendentes = sum(1 for v in vendas if v['status_pagamento'] == 'pendente')
    total_valor_pendente = sum(v['total'] for v in vendas if v['status_pagamento'] == 'pendente')
    
    return render_template(
        'vendas/listar_vendas_prazo.html',
        vendas=vendas,
        total_vendas=total_vendas,
        total_pendentes=total_pendentes,
        total_valor_pendente=total_valor_pendente,
        clientes=clientes
    )


@app.route('/vendas/listar_vendas_prazo/pagar/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def pagar_venda_prazo(venda_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE vendas
                SET status_pagamento = 'pago'
                WHERE id = ? AND metodo_pagamento = 'pagamento_prazo' AND status_pagamento = 'pendente'
            ''', (venda_id,))
            
            if cursor.rowcount == 0:
                return redirect(url_for('listar_vendas_prazo', error='Venda não encontrada ou já paga'))
            
            # Baixar estoque
            cursor.execute('''
                SELECT produto_id, quantidade 
                FROM venda_itens 
                WHERE venda_id = ?
            ''', (venda_id,))
            
            for item in cursor.fetchall():
                cursor.execute('''
                    UPDATE produtos 
                    SET quantidade = quantidade - ?
                    WHERE id = ?
                ''', (item['quantidade'], item['produto_id']))
            
            conn.commit()
            
        return redirect(url_for('listar_vendas_prazo', success=True))
    except Exception as e:
        logging.error(f"Erro ao pagar venda a prazo: {str(e)}")
        return redirect(url_for('listar_vendas_prazo', error='Erro ao processar pagamento'))

@app.route('/vendas/listar_vendas_prazo/adicionar_observacao/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def adicionar_observacao_venda_prazo(venda_id):
    observacao = request.form.get('observacao', '')
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE vendas
                SET observacao = ?
                WHERE id = ?
            ''', (observacao, venda_id))
            conn.commit()
        return redirect(url_for('listar_vendas_prazo', success_obs=True))
    except Exception as e:
        logging.error(f"Erro ao adicionar observação: {str(e)}")
        return redirect(url_for('listar_vendas_prazo', error_obs='Erro ao salvar observação'))



# ---------------------------------------------------------------
# Gestão de Usuários (Admin)
# ---------------------------------------------------------------

# Adicione esta rota no app.py, na seção de Gestão de Usuários
@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_usuario():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            role = request.form['role']
            
            # Validações básicas
            if not all([username, email, password]):
                return render_template('admin/novo_usuario.html', 
                                     error='Todos os campos são obrigatórios',
                                     form_data=request.form)
            
            if role not in ['gerente', 'funcionario']:
                return render_template('admin/novo_usuario.html',
                                     error='Cargo inválido',
                                     form_data=request.form)
            
            # Criar o usuário
            user_id = create_user(username, email, password, role)
            
            registrar_log(
                session['user_id'],
                'create_user',
                'INFO',
                {'user_id': user_id, 'username': username, 'role': role},
                request=request
            )
            
            return redirect(url_for('admin_usuarios', success=f'Usuário {username} criado com sucesso'))
        
        except sqlite3.IntegrityError as e:
            error = 'Username ou email já existente' if 'UNIQUE' in str(e) else 'Erro ao criar usuário'
            return render_template('admin/novo_usuario.html',
                                error=error,
                                form_data=request.form)
        
        except Exception as e:
            logging.error(f"Erro ao criar usuário: {str(e)}")
            return render_template('admin/novo_usuario.html',
                                error='Erro ao criar usuário',
                                form_data=request.form)
    
    return render_template('admin/novo_usuario.html')


@app.route('/admin/usuarios/editar/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def editar_usuario(id):
    try:
        new_role = request.form.get('role')
        if new_role not in ['gerente', 'funcionario']:
            abort(400)
        
        # Impedir que o último gerente seja rebaixado
        if new_role == 'funcionario':
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'gerente'")
                count_gerentes = cursor.fetchone()[0]
                
                if count_gerentes == 1:
                    return redirect(url_for('admin_usuarios', error='Não pode rebaixar o último gerente'))

        update_user_role(id, new_role)
        return redirect(url_for('admin_usuarios'))
    
    except Exception as e:
        logging.error(f"Erro ao atualizar usuário: {str(e)}")
        return redirect(url_for('admin_usuarios', error='Erro ao atualizar usuário'))


@app.route('/admin/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_usuario(id):
    try:
        # Verificar se é o último administrador
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE id = ?", (id,))
            user = cursor.fetchone()
            
            if user['role'] == 'gerente':
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'gerente'")
                count_gerentes = cursor.fetchone()[0]
                
                if count_gerentes == 1:
                    return redirect(url_for('admin_usuarios', error='Não pode excluir o último gerente'))

        delete_user(id)
        return redirect(url_for('admin_usuarios'))
    
    except Exception as e:
        logging.error(f"Erro ao excluir usuário: {str(e)}")
        return redirect(url_for('admin_usuarios', error='Erro ao excluir usuário'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = 'admin'")
            if not cursor.fetchone():
                hashed_pw = generate_password_hash('admin123')
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (?, ?, ?, ?)
                ''', ('admin', 'admin@example.com', hashed_pw, 'gerente'))
                conn.commit()
    app.run(debug=True)