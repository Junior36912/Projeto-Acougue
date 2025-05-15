import json
import logging
import os
import shutil
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask, jsonify, render_template, request, redirect, url_for,
    send_from_directory, session, abort, send_file  
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app_logging import registrar_log
from banco_dados import (
    fetch_vendas_prazo,
    marcar_venda_pago,
    adicionar_observacao_venda,
    processar_venda,
    listar_produtos_simples,
    get_all_users,
    get_all_produtos,
    get_all_vendas,
    get_venda_items,
    init_db,
    get_db_connection,
    get_user_by_id,
    create_user,
    update_user_role,
    delete_user,
    get_fornecedores,
    create_fornecedor,
    get_fornecedor_by_id,
    update_fornecedor,
    delete_fornecedor,
    get_user_by_username,
    update_user,
    get_all_fornecedores,
    listar_produtos as db_listar_produtos,
    inserir_produto,
    atualizar_produto,
    excluir_produto,
    get_categorias,
    get_produto_by_id
)
from decorators import login_required, role_required
from gerador_pdf import gerar_relatorio_pdf

from flask_wtf.csrf import CSRFProtect

# Configuração de logging
logging.basicConfig(level=logging.INFO)


def format_datetime(value, format='%d/%m/%Y %H:%M'):
    if value is None:
        return ''
    if isinstance(value, str):
        # Se for string, converte para datetime primeiro
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                value = datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                return value
    return value.strftime(format)


app = Flask(__name__)
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    UPLOAD_FOLDER = 'static/uploads/produtos'
    DATABASE = 'acougue.db'
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    MAX_FILE_SIZE_MB = 2
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
app.config.from_object(Config)

app.jinja_env.filters['format_datetime'] = format_datetime

# Garantir caminho absoluto para upload
app.config['UPLOAD_FOLDER'] = os.path.abspath(app.config['UPLOAD_FOLDER'])
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

csrf = CSRFProtect(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def backup_db():
    """Rotina de backup do banco de dados"""
    try:
        # Configurar diretório de backups
        backup_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Gerar nome do arquivo com timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"acougue_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_name)
        
        # Usar backup via API do SQLite para maior segurança
        src = sqlite3.connect(app.config['DATABASE'])
        dst = sqlite3.connect(backup_path)
        
        with dst:
            src.backup(dst)
        
        src.close()
        dst.close()
        
        # Manter apenas últimos 7 backups
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        while len(backups) > 7:
            os.remove(os.path.join(backup_dir, backups.pop(0)))
        
        logging.info(f"Backup realizado: {backup_name}")
    except Exception as e:
        logging.error(f"Erro no backup: {str(e)}", exc_info=True)


@app.route('/backup')
@login_required
@role_required('gerente')
def download_backup():
    try:
        backup_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Criar backup temporário do banco
        temp_db_name = f"temp_backup_{timestamp}.db"
        temp_db_path = os.path.join(backup_dir, temp_db_name)
        
        src = sqlite3.connect(app.config['DATABASE'])
        dst = sqlite3.connect(temp_db_path)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        # Criar arquivo zip
        backup_name = f"acougue_system_backup_{timestamp}.zip"
        backup_path = os.path.join(backup_dir, backup_name)
        
        with zipfile.ZipFile(backup_path, 'w') as zipf:
            # Adicionar banco de dados
            zipf.write(temp_db_path, os.path.basename(temp_db_path))
            
            # Adicionar pasta de uploads
            uploads_path = app.config['UPLOAD_FOLDER']
            for root, dirs, files in os.walk(uploads_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=uploads_path)
                    zipf.write(file_path, os.path.join('produtos', arcname))

        # Limpeza
        os.remove(temp_db_path)
        
        # Manter apenas últimos 7 backups
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.endswith('.zip')],
            key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)),
            reverse=True
        )
        while len(backups) > 7:
            old_backup = backups.pop()
            os.remove(os.path.join(backup_dir, old_backup))
            logging.info(f"Removendo backup antigo: {old_backup}")

        return send_from_directory(backup_dir, backup_name, as_attachment=True)

    except Exception as e:
        logging.error(f"Erro ao gerar backup: {str(e)}", exc_info=True)
        abort(500, description="Erro ao gerar backup do sistema")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(backup_db, 'interval', hours=24)


@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))


# Sistema de Autenticação

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


@app.route('/produtos')
@login_required
@role_required('gerente')
def listar_produtos():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '')
    categoria = request.args.get('categoria', '')
    
    produtos, total = db_listar_produtos(search, categoria, page, per_page)
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('produtos/listar.html',
                         produtos=produtos,
                         categorias=get_categorias(),
                         page=page,
                         total_pages=total_pages,
                         search=search,
                         categoria=categoria)

@app.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_produto():
    if request.method == 'POST':
        try:
            form_data = request.form
            foto = request.files.get('foto')
            
            if foto and foto.filename != '':
                # Verificar extensão
                if not allowed_file(foto.filename):
                    error_message = "Apenas arquivos JPG, JPEG e PNG são permitidos!"
                    return render_template('produtos/novo.html',
                                        error=error_message,
                                        fornecedores=get_fornecedores(),
                                        form_data=form_data)
                
                # Verificar tamanho
                foto.stream.seek(0, os.SEEK_END)
                file_size = foto.stream.tell()
                foto.stream.seek(0)  # Resetar posição do arquivo
                
                if file_size > app.config['MAX_FILE_SIZE_MB'] * 1024 * 1024:
                    error_message = f"Arquivo muito grande! Tamanho máximo: {app.config['MAX_FILE_SIZE_MB']}MB"
                    return render_template('produtos/novo.html',
                                        error=error_message,
                                        fornecedores=get_fornecedores(),
                                        form_data=form_data)
        
            # Chama a função do banco_dados.py
            inserir_produto(form_data, foto)
            return redirect(url_for('listar_produtos'))

        except Exception as e:
            logging.error(f"Erro ao cadastrar produto: {str(e)}", exc_info=True)  
            error_message = str(e) if app.debug else "Erro ao cadastrar produto. Verifique os dados."
            return render_template('produtos/novo.html',
                                error=error_message,
                                fornecedores=get_fornecedores(),
                                form_data=request.form)

    return render_template('produtos/novo.html',
                         fornecedores=get_fornecedores())

@app.route('/produtos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_produto(id):
    produto = get_produto_by_id(id)
    if not produto:
        abort(404)

    if request.method == 'POST':
        try:
            form_data = request.form
            foto = request.files.get('foto')
            
            if foto and foto.filename != '':
                # Verificar extensão
                if not allowed_file(foto.filename):
                    error_message = "Apenas arquivos JPG, JPEG e PNG são permitidos!"
                    return render_template('produtos/novo.html',
                                        error=error_message,
                                        fornecedores=get_fornecedores(),
                                        form_data=form_data)
                
                # Verificar tamanho
                foto.stream.seek(0, os.SEEK_END)
                file_size = foto.stream.tell()
                foto.stream.seek(0)  
                
                if file_size > app.config['MAX_FILE_SIZE_MB'] * 1024 * 1024:
                    error_message = f"Arquivo muito grande! Tamanho máximo: {app.config['MAX_FILE_SIZE_MB']}MB"
                    return render_template('produtos/novo.html',
                                        error=error_message,
                                        fornecedores=get_fornecedores(),
                                        form_data=form_data)

            atualizar_produto(id, form_data, foto)
            return redirect(url_for('listar_produtos'))

        except Exception as e:
            logging.error(f"Erro ao atualizar produto: {str(e)}")
            return render_template('produtos/editar.html',
                                produto=produto,
                                fornecedores=get_fornecedores(),
                                error=str(e))

    return render_template('produtos/editar.html',
                         produto=produto,
                         fornecedores=get_fornecedores())

@app.route('/produtos/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_produto_route(id):
    try:
        excluir_produto(id)
        return redirect(url_for('listar_produtos'))
    except ValueError as ve:
        return redirect(url_for('listar_produtos', error=str(ve)))
    except Exception as e:
        logging.error(f"Erro ao excluir produto: {str(e)}", exc_info=True)
        return redirect(url_for('listar_produtos', error="Erro interno ao excluir produto"))
# ---------------------------------------------------------------
# Gestão de Fornecedores
# ---------------------------------------------------------------

@app.route('/fornecedores')
@login_required
@role_required('gerente')
def listar_fornecedores():
    search = request.args.get('search', '')
    # Usa função do banco_dados para buscar fornecedores
    fornecedores = get_fornecedores(search=search)
    return render_template('fornecedores/listar.html', fornecedores=fornecedores)



@app.route('/fornecedores/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_fornecedor():
    if request.method == 'POST':
        dados = {
            'nome': request.form['nome'],
            'cnpj': request.form['cnpj'],
            'contato': request.form['contato'],
            'endereco': request.form.get('endereco', '')
        }
        try:
            create_fornecedor(**dados)
            return redirect(url_for('listar_fornecedores'))
        except ValueError as e:
            # Exibe o erro e mantém os dados do formulário
            return render_template('fornecedores/novo.html', 
                                error=str(e), 
                                form_data=request.form)
    return render_template('fornecedores/novo.html')


@app.route('/fornecedores/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_fornecedor(id):
    fornecedor = get_fornecedor_by_id(id)
    if not fornecedor:
        abort(404)
    if request.method == 'POST':
        dados = {
            'nome': request.form['nome'],
            'cnpj': request.form['cnpj'],
            'contato': request.form['contato'],
            'endereco': request.form.get('endereco', '')
        }
        try:
            update_fornecedor(id, **dados)
            return redirect(url_for('listar_fornecedores'))
        except ValueError as e:
            # Passar form_data para manter dados submetidos
            return render_template('fornecedores/editar.html', 
                                fornecedor=fornecedor, 
                                error=str(e), 
                                form_data=request.form)  # Adicionado form_data
    return render_template('fornecedores/editar.html', fornecedor=fornecedor)


@app.route('/fornecedores/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_fornecedor(id):
    try:
        delete_fornecedor(id)
        return redirect(url_for('listar_fornecedores'))
    except Exception:
        # tratando IntegrityError em delete
        return redirect(url_for('listar_fornecedores', error='Não é possível excluir fornecedor com produtos vinculados'))

# Gestão de Vendas

@app.route('/vendas/nova', methods=['GET', 'POST'])
@login_required
def nova_venda():
    if request.method == 'POST':
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Usuário não autenticado'}), 401

        data = request.get_json()
        metodo_pagamento = data['metodo_pagamento']
        data_vencimento = data.get('data_vencimento')

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
            'cliente_cpf': data.get('cpf'),
            'cliente_nome': data.get('nome_cliente'),
            'metodo_pagamento': data['metodo_pagamento'],
            'itens': data['itens'],
            'status_pagamento': 'pendente' if data['metodo_pagamento']=='pagamento_prazo' else 'pago',
            'data_vencimento': data.get('data_vencimento'),
            'observacao': data.get('observacao')
        }
        venda_id = f"V{datetime.now():%Y%m%d%H%M%S}"

        try:
            processar_venda(venda_id, venda_data, user_id)
            return jsonify({'success': True, 'venda_id': venda_id})
        except ValueError as ve:
            return jsonify({'success': False, 'error': str(ve)}), 400
        except Exception as e:
            logging.error(f"Erro ao processar venda: {e}")
            return jsonify({'success': False, 'error': 'Erro ao registrar venda'}), 500

    # GET: simplesmente listar produtos via função reutilizável
    produtos = listar_produtos_simples()
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('vendas/nova.html', produtos=produtos, current_date=current_date)

    
@app.route('/vendas/pagamento_prazo/pagar/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def pagar_pagamento_prazo(venda_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE vendas
                SET status_pagamento = 'pago'
                WHERE id = ? 
                  AND metodo_pagamento = 'pagamento_prazo' 
                  AND status_pagamento = 'pendente'
                """,
                (venda_id,)
            )
            if cursor.rowcount == 0:
                return redirect(url_for('listar_fiado', error='Venda não encontrada ou já paga'))
            conn.commit()
        return redirect(url_for('listar_fiado', success=True))
    except Exception as e:
        logging.error(f"Erro ao pagar fiado: {e}")
        return redirect(url_for('listar_fiado', error='Erro ao processar pagamento'))

# ---------------------------------------------------------------
# Relatórios

@app.route('/relatorios')
@login_required
@role_required('gerente')
def relatorios():
    return render_template('relatorios/dashboard.html')


# Helper functions para relatórios
def parse_date(date_str, default):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date().isoformat()
    except:
        return default

@app.route('/relatorios/<report_type>')
@login_required
@role_required('gerente')
def relatorios_unificados(report_type):
    report_titles = {
        'vendas_totais': 'Vendas Totais',
        
    }

    # Relatório de Vendas Totais (HTML)
    if report_type == 'vendas_totais':
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    v.id,
                    v.data,
                    v.cliente_nome as cliente,
                    GROUP_CONCAT(p.nome, ', ') as produtos,
                    v.total,
                    v.metodo_pagamento,
                    COUNT(vi.id) as total_itens
                FROM vendas v
                LEFT JOIN venda_itens vi ON v.id = vi.venda_id
                LEFT JOIN produtos p ON vi.produto_id = p.id
                GROUP BY v.id
                ORDER BY v.data DESC
            ''')
            dados = [dict(zip([column[0] for column in cursor.description], row)) 
                    for row in cursor.fetchall()]
        
        return render_template('relatorio_unificado.html',
                            dados=dados,
                            report_type=report_type,
                            titulo_relatorio=report_titles.get(report_type, 'Relatório'))

    # Configurações para relatórios JSON
    reports = {
        'vendas_periodo': {
            'query': '''
                SELECT DATE(v.data) as data, COUNT(*) as total_vendas,
                SUM(v.total) as valor_total, AVG(v.total) as ticket_medio
                FROM vendas v
                WHERE DATE(v.data) BETWEEN ? AND ?
                GROUP BY DATE(v.data) ORDER BY data
            ''',
            'params': (
                request.args.get('start_date', datetime.now().replace(day=1).date().isoformat()),
                request.args.get('end_date', datetime.now().date().isoformat())
            )
        },
        'vendas_categorias': {
            'query': '''
                SELECT p.categoria, SUM(vi.quantidade) as quantidade_vendida,
                SUM(vi.quantidade * vi.preco_unitario) as valor_total
                FROM venda_itens vi JOIN produtos p ON vi.produto_id = p.id
                GROUP BY p.categoria ORDER BY valor_total DESC
            '''
        },
        'top_produtos': {
            'query': '''
                SELECT p.nome, SUM(vi.quantidade) as quantidade_vendida,
                SUM(vi.quantidade * vi.preco_unitario) as valor_total
                FROM venda_itens vi JOIN produtos p ON vi.produto_id = p.id
                GROUP BY p.id ORDER BY valor_total DESC LIMIT ?
            ''',
            'params': (int(request.args.get('limit', 10)),)
        },
        'contas_receber': {
            'query': '''
                SELECT cliente_nome, total, data_vencimento,
                CASE WHEN data_vencimento < DATE('now') THEN 'Vencido' ELSE 'A Vencer' END as status
                FROM vendas WHERE status_pagamento = 'pendente' ORDER BY data_vencimento
            ''',
            'post_process': lambda data: {'contas': data, 'total_pendente': sum(item['total'] for item in data)}
        },
        'estoque_nivel': {
            'query': '''
                SELECT nome, quantidade, estoque_minimo, (quantidade - estoque_minimo) as diferenca
                FROM produtos WHERE quantidade < estoque_minimo ORDER BY diferenca ASC
            '''
        },
        'estoque_validade': {
            'query': '''
                SELECT nome, data_validade,
                JULIANDAY(data_validade) - JULIANDAY('now') as dias_restantes
                FROM produtos WHERE data_validade IS NOT NULL
                AND dias_restantes BETWEEN 0 AND ? ORDER BY data_validade
            ''',
            'params': (int(request.args.get('dias', 30)),)
        },
        'clientes_fieis': {
            'query': '''
                SELECT cliente_nome, COUNT(*) as total_compras, SUM(total) as valor_total_gasto
                FROM vendas WHERE cliente_nome IS NOT NULL
                GROUP BY cliente_nome ORDER BY total_compras DESC LIMIT ?
            ''',
            'params': (int(request.args.get('limit', 10)),)
        },
        'fornecedores_produtos': {
            'query': '''
                SELECT f.nome as fornecedor, COUNT(p.id) as total_produtos, SUM(p.quantidade) as total_estoque
                FROM fornecedores f LEFT JOIN produtos p ON f.id = p.fornecedor_id
                GROUP BY f.id ORDER BY total_produtos DESC
            '''
        },
        'movimentacao_caixa': {
            'query': '''
                SELECT DATE(data) as data,
                SUM(CASE WHEN metodo_pagamento = 'fiado' THEN 0 ELSE total END) as entradas,
                SUM(CASE WHEN metodo_pagamento = 'fiado' THEN total ELSE 0 END) as saidas
                FROM vendas GROUP BY DATE(data) ORDER BY data DESC
            '''
        },
        'comparativo': {
            'query': '''
                SELECT strftime('{group_format}', data) as periodo,
                COUNT(*) as total_vendas, SUM(total) as valor_total
                FROM vendas GROUP BY periodo ORDER BY periodo DESC LIMIT 12
            ''',
            'params': (),
            'pre_process': lambda: {'group_format': '%Y-%m' if request.args.get('periodo', 'month') == 'month' else '%Y'}
        }
    }

    config = reports.get(report_type)
    if not config:
        abort(404, description="Relatório não encontrado")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = config['query']
        
        if 'pre_process' in config:
            pre_processed = config['pre_process']()
            query = query.format(**pre_processed)
        
        params = config.get('params', ())
        cursor.execute(query, params)
        
        dados = [dict(zip([column[0] for column in cursor.description], row)) 
                for row in cursor.fetchall()]
    
    if 'post_process' in config:
        dados = config['post_process'](dados)
    
    return jsonify({
        'report_type': report_type,
        'data': dados,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/relatorios/gerar_pdf', endpoint='gerar_pdf')
@login_required
@role_required('gerente')
def relatorio_pdf():
    return gerar_relatorio_pdf()


# -----------------------
# Admin (Gerente)
# -----------------------

@app.route('/admin/usuarios')
@login_required
@role_required('gerente')
def admin_usuarios():
    success = request.args.get('success')
    error = request.args.get('error')
    # Usa a função do módulo banco_dados
    usuarios = [dict(u) for u in get_all_users()]
    return render_template(
        'admin/usuarios.html',
        usuarios=usuarios,
        success=success,
        error=error
    )

@app.route('/admin/estoque')
@login_required
@role_required('gerente')
def admin_estoque():
    # Obtém todos os produtos e filtra alerta de estoque
    produtos = get_all_produtos()
    estoque = [
        p for p in produtos
        if p['quantidade'] < p['estoque_minimo']
    ]
    return render_template('admin/estoque.html', estoque=estoque)


# Gestão de Usuários (Admin)

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_usuario():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'funcionario')

        # Validações básicas
        if not all([username, email, password]):
            return render_template('admin/novo_usuario.html',
                                   error='Todos os campos são obrigatórios',
                                   form_data=request.form)
        if role not in ['gerente', 'funcionario']:
            return render_template('admin/novo_usuario.html',
                                   error='Cargo inválido',
                                   form_data=request.form)
        try:
            user_id = create_user(username, email, password, role)
            registrar_log(
                session['user_id'],
                'create_user',
                'INFO',
                {'user_id': user_id, 'username': username, 'role': role},
                request=request
            )
            return redirect(url_for('admin_usuarios', success=f'Usuário {username} criado com sucesso'))
        except ValueError as ve:
            return render_template('admin/novo_usuario.html',
                                   error=str(ve),
                                   form_data=request.form)
        except Exception as e:
            logging.error(f"Erro ao criar usuário: {e}")
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




# Dashboard Principal

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        is_gerente = session['role'] == 'gerente'
        data = {'is_gerente': is_gerente}

        # Dados básicos para todos os usuários
        cursor.execute('''
            SELECT 
                v.id, v.data, v.cliente_nome as cliente, v.total,
                v.metodo_pagamento, v.status_pagamento
            FROM vendas v
            WHERE DATE(v.data) = DATE('now')
            ORDER BY v.data DESC
        ''')
        data['vendas_hoje'] = [dict(zip([column[0] for column in cursor.description], row)) 
                       for row in cursor.fetchall()]

        
        cursor.execute('SELECT SUM(total) as total FROM vendas WHERE DATE(data) = DATE("now")')
        data['total_dia'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT nome, quantidade, estoque_minimo
            FROM produtos
            WHERE quantidade < estoque_minimo
            ORDER BY quantidade ASC
        ''')
        data['alertas_estoque'] = cursor.fetchall()

        if is_gerente:
            # Métricas adicionais para gerentes
            cursor.execute("SELECT COUNT(*) as total FROM vendas")
            data['total_vendas'] = cursor.fetchone()['total']

            cursor.execute('''
                SELECT 
                    COUNT(*) as total_vendas_hoje,
                    SUM(total) as total_receita_hoje,
                    AVG(total) as ticket_medio_hoje
                FROM vendas 
                WHERE DATE(data) = DATE('now')
            ''')
            data.update(cursor.fetchone())

            cursor.execute('''
                SELECT metodo_pagamento, COUNT(*) as quantidade,
                       SUM(total) as valor_total
                FROM vendas
                WHERE DATE(data) = DATE('now')
                GROUP BY metodo_pagamento
            ''')
            data['metodos_pagamento'] = cursor.fetchall()

            cursor.execute('''
                SELECT p.nome, SUM(vi.quantidade) as quantidade_vendida
                FROM venda_itens vi
                JOIN produtos p ON vi.produto_id = p.id
                GROUP BY vi.produto_id
                ORDER BY quantidade_vendida DESC
                LIMIT 5
            ''')
            data['top_produtos'] = cursor.fetchall()

        return render_template('dashboard.html', **data)
    


@app.route('/vendas/listar_vendas_prazo')
@login_required
@role_required('gerente')
def listar_vendas_prazo():
    letra_filter = request.args.get('letra', '').upper()
    cliente_filter = request.args.get('cliente_filter')

    vendas, clientes, total_vendas, total_pendentes, total_valor_pendente = \
        fetch_vendas_prazo(cliente_filter, letra_filter)

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
    sucesso = marcar_venda_pago(venda_id)
    if not sucesso:
        return redirect(url_for('listar_vendas_prazo', error='Venda não encontrada ou já paga'))
    return redirect(url_for('listar_vendas_prazo', success=True))

@app.route('/vendas/listar_vendas_prazo/adicionar_observacao/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def adicionar_observacao_venda_prazo(venda_id):
    observacao = request.form.get('observacao', '')
    adicionar_observacao_venda(venda_id, observacao)
    return redirect(url_for('listar_vendas_prazo', success_obs=True))


# Utilitários


@app.template_filter('format_currency')
def format_currency(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

app.jinja_env.filters['format_currency'] = format_currency

def verificar_validades():
    """Verifica produtos próximos do vencimento"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            hoje = datetime.now().date()
            limite = hoje + timedelta(days=30)  # 30 dias de antecedência
            
            cursor.execute('''
                SELECT id, nome, data_validade,
                       JULIANDAY(data_validade) - JULIANDAY(?) AS dias_restantes
                FROM produtos
                WHERE data_validade BETWEEN ? AND ?
                ORDER BY data_validade ASC
            ''', (hoje, hoje, limite))
            
            produtos = cursor.fetchall()
            
            for produto in produtos:
                registrar_log(
                    user_id='Sistema',
                    action='alerta_validade',  
                    level='WARNING',           
                    details={                  
                        'produto_id': produto['id'],
                        'nome': produto['nome'],
                        'data_validade': produto['data_validade'],
                        'dias_para_vencer': produto['dias_restantes']
                    }
                )
            
            logging.info(f"Verificação de validades: {len(produtos)} alertas gerados")
    except Exception as e:
        logging.error(f"Erro na verificação de validades: {str(e)}", exc_info=True)

# Agendar verificação diária
scheduler.add_job(verificar_validades, 'interval', hours=24)


if __name__ == '__main__':
    try:
        scheduler.start()
        backup_db()
        verificar_validades()
        app.run(debug=True)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        
        
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500