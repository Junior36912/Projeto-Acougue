import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask, jsonify, render_template, request, redirect, url_for,
    session, abort, send_file, flash
)
from werkzeug.security import check_password_hash

from app_logging import registrar_log
from banco_dados import (
    fetch_vendas_prazo,
    marcar_venda_pago,
    adicionar_observacao_venda,
    processar_venda,
    listar_produtos_simples,
    get_all_users,
    get_all_produtos,
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
    update_user,
    listar_produtos as db_listar_produtos,
    inserir_produto,
    atualizar_produto,
    excluir_produto,
    get_categorias,
    get_produto_by_id,
    listar_logs,
    contar_logs_por_nivel,
    listar_acoes_logs,
    FORMAS_PAGAMENTO,
    normalizar_forma_pagamento,
    ler_data_hora,
    registrar_falha_login,
    tempo_bloqueio_login,
    limpar_falhas_login
)
from imagens import caminho_miniatura, gerar_miniaturas_faltantes, PASTA_MINIATURAS
from decorators import login_required, role_required
from gerador_pdf import gerar_relatorio_pdf, SQL_MOVIMENTACAO_CAIXA

from flask_wtf.csrf import CSRFProtect

# Configuração de logging
logging.basicConfig(level=logging.INFO)


def format_datetime(value, format='%d/%m/%Y %H:%M'):
    """Formata datas gravadas com ou sem hora (e com microssegundos).
    Quando o valor não tem hora, a parte de hora do formato é omitida."""
    if value is None or value == '':
        return ''
    momento, tem_hora = ler_data_hora(value)
    if momento is None:
        return value
    if not tem_hora:
        format = re.sub(r'\s*%H:%M(:%S)?', '', format).strip()
        if not format:
            return '—'
    return momento.strftime(format)


def carregar_secret_key(pasta_instancia):
    """SECRET_KEY do ambiente ou, na falta dela, uma chave aleatória gerada uma
    única vez e guardada em instance/secret_key (pasta fora do git).
    Nunca usa uma chave fixa no código: com ela, qualquer um forjaria a sessão."""
    chave = os.environ.get('SECRET_KEY')
    if chave:
        return chave
    caminho = os.path.join(pasta_instancia, 'secret_key')
    try:
        with open(caminho) as arquivo:
            chave = arquivo.read().strip()
        if chave:
            return chave
    except FileNotFoundError:
        pass
    os.makedirs(pasta_instancia, exist_ok=True)
    chave = secrets.token_hex(32)
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, 'w') as arquivo:
        arquivo.write(chave)
    return chave


app = Flask(__name__)
class Config:
    SECRET_KEY = carregar_secret_key(app.instance_path)
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'produtos')
    BACKUP_FOLDER = os.path.join(app.root_path, 'backups')
    DATABASE = 'acougue.db'
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    MAX_FILE_SIZE_MB = 2
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
    # Sessão expira em 12h mesmo com o navegador aberto; o cookie não vai em
    # requisições disparadas por outros sites
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True
app.config.from_object(Config)

init_db() 

app.jinja_env.filters['format_datetime'] = format_datetime

# Garantir caminho absoluto para upload
app.config['UPLOAD_FOLDER'] = os.path.abspath(app.config['UPLOAD_FOLDER'])
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

csrf = CSRFProtect(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ---------------------------------------------------------------
# Backup
# ---------------------------------------------------------------
# O banco (pequeno) vai para um zip comprimido a cada backup; as fotos (~19 MB,
# já comprimidas) só ganham um zip novo quando alguma foto muda.
PREFIXO_BACKUP_BANCO = 'acougue_banco_'
PREFIXO_BACKUP_FOTOS = 'acougue_fotos_'
RETENCAO_RECENTES = timedelta(hours=24)  # tudo das últimas 24h
RETENCAO_DIAS = 7       # último backup de cada um dos 7 dias mais recentes
RETENCAO_SEMANAS = 4    # e de cada uma das 4 semanas mais recentes
RETENCAO_FOTOS = 2      # últimos backups de fotos
INTERVALO_BACKUP = timedelta(hours=24)


def _nome_backup(prefixo):
    # Microssegundos: dois backups no mesmo segundo não se sobrescrevem
    return f"{prefixo}{datetime.now():%Y%m%d_%H%M%S_%f}.zip"


def _backups(prefixo):
    """Backups com o prefixo, do mais novo para o mais antigo (o nome tem a data)."""
    pasta = app.config['BACKUP_FOLDER']
    if not os.path.isdir(pasta):
        return []
    return sorted((nome for nome in os.listdir(pasta)
                   if nome.startswith(prefixo) and nome.endswith('.zip')), reverse=True)


def _data_do_backup(nome):
    carimbo = nome.rsplit('_', 3)[-3:]
    return datetime.strptime('_'.join(carimbo)[:-len('.zip')], '%Y%m%d_%H%M%S_%f')


def _adicionar_banco(zipf):
    """Cópia consistente do banco (API de backup do SQLite), mesmo com o sistema em uso."""
    with tempfile.TemporaryDirectory() as pasta_temporaria:
        copia = os.path.join(pasta_temporaria, 'acougue.db')
        destino = sqlite3.connect(copia)
        try:
            with get_db_connection() as conn:
                conn.backup(destino)
        finally:
            destino.close()
        zipf.write(copia, 'acougue.db', compress_type=zipfile.ZIP_DEFLATED)


def _arquivos_de_fotos():
    pasta = app.config['UPLOAD_FOLDER']
    for raiz, subpastas, arquivos in os.walk(pasta):
        # Miniaturas não entram: são recriadas a partir das fotos (ver imagens.py)
        subpastas[:] = sorted(d for d in subpastas if d != PASTA_MINIATURAS)
        for nome in sorted(arquivos):
            caminho = os.path.join(raiz, nome)
            yield caminho, os.path.join('produtos', os.path.relpath(caminho, pasta))


def _assinatura_fotos():
    """Muda quando alguma foto é adicionada, removida ou trocada."""
    partes = []
    for caminho, nome_no_zip in _arquivos_de_fotos():
        info = os.stat(caminho)
        partes.append(f'{nome_no_zip}|{info.st_size}|{int(info.st_mtime)}')
    return hashlib.sha256('\n'.join(partes).encode()).hexdigest()


def _adicionar_fotos(zipf):
    for caminho, nome_no_zip in _arquivos_de_fotos():
        zipf.write(caminho, nome_no_zip, compress_type=zipfile.ZIP_STORED)


def aplicar_retencao(agora=None):
    """Apaga backups antigos do formato atual. Os arquivos acougue_system_backup_*
    das versões anteriores não são tocados."""
    agora = agora or datetime.now()
    pasta = app.config['BACKUP_FOLDER']
    manter = set(_backups(PREFIXO_BACKUP_FOTOS)[:RETENCAO_FOTOS])
    dias, semanas = set(), set()
    for nome in _backups(PREFIXO_BACKUP_BANCO):
        momento = _data_do_backup(nome)
        if momento >= agora - RETENCAO_RECENTES:
            manter.add(nome)
        if momento.date() not in dias and len(dias) < RETENCAO_DIAS:
            dias.add(momento.date())
            manter.add(nome)
        semana = momento.isocalendar()[:2]
        if semana not in semanas and len(semanas) < RETENCAO_SEMANAS:
            semanas.add(semana)
            manter.add(nome)
    for nome in _backups(PREFIXO_BACKUP_BANCO) + _backups(PREFIXO_BACKUP_FOTOS):
        if nome not in manter:
            os.remove(os.path.join(pasta, nome))
            logging.info(f"Backup antigo removido: {nome}")


def backup_db():
    """Backup do banco e, se alguma foto mudou desde o último, das fotos.
    Retorna a lista de arquivos criados, ou None em caso de erro."""
    try:
        pasta = app.config['BACKUP_FOLDER']
        os.makedirs(pasta, exist_ok=True)
        criados = []

        nome = _nome_backup(PREFIXO_BACKUP_BANCO)
        with zipfile.ZipFile(os.path.join(pasta, nome), 'w') as zipf:
            _adicionar_banco(zipf)
        criados.append(nome)

        assinatura = _assinatura_fotos()
        ultimo_fotos = _backups(PREFIXO_BACKUP_FOTOS)[:1]
        assinatura_anterior = None
        if ultimo_fotos:
            with zipfile.ZipFile(os.path.join(pasta, ultimo_fotos[0])) as zipf:
                assinatura_anterior = zipf.comment.decode()
        if assinatura != assinatura_anterior:
            nome = _nome_backup(PREFIXO_BACKUP_FOTOS)
            with zipfile.ZipFile(os.path.join(pasta, nome), 'w') as zipf:
                _adicionar_fotos(zipf)
                zipf.comment = assinatura.encode()
            criados.append(nome)

        aplicar_retencao()
        return criados

    except Exception as e:
        logging.error(f"Erro ao gerar backup: {str(e)}", exc_info=True)
        return None


def backup_se_necessario():
    """Faz backup só se o último backup do banco tiver mais de 24h
    (evita um backup a cada reinício do sistema)."""
    ultimo = _backups(PREFIXO_BACKUP_BANCO)[:1]
    if ultimo and datetime.now() - _data_do_backup(ultimo[0]) < INTERVALO_BACKUP:
        return None
    return backup_db()


# Rota protegida: download de um backup completo (banco + fotos), gerado na hora
# e entregue sem ficar guardado na pasta de backups
@app.route('/backup')
@login_required
@role_required('gerente')
def download_backup():
    arquivo = tempfile.TemporaryFile()
    try:
        with zipfile.ZipFile(arquivo, 'w') as zipf:
            _adicionar_banco(zipf)
            _adicionar_fotos(zipf)
    except Exception as e:
        arquivo.close()
        logging.error(f"Erro ao gerar backup para download: {e}", exc_info=True)
        abort(500, description="Erro ao gerar backup do sistema")
    arquivo.seek(0)
    registrar_log(session['user_id'], 'download_backup', 'INFO', request=request)
    return send_file(arquivo, as_attachment=True, mimetype='application/zip',
                     download_name=f"acougue_backup_completo_{datetime.now():%Y%m%d_%H%M%S}.zip")


@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))


# Sistema de Autenticação

# Senha documentada no README e criada pelo popular_banco.py
SENHA_PADRAO = 'admin123'
ENDPOINTS_LIVRES = {'static', 'login', 'logout', 'trocar_senha'}


@app.before_request
def carregar_usuario_da_sessao():
    """Relê o usuário do banco a cada requisição: quem foi desativado perde o
    acesso na hora e mudanças de cargo valem sem precisar sair e entrar."""
    user_id = session.get('user_id')
    if user_id is None or request.endpoint == 'static':
        return None
    with get_db_connection() as conn:
        usuario = conn.execute(
            'SELECT username, role, ativo FROM users WHERE id = ?', (user_id,)).fetchone()
    if usuario is None or not usuario['ativo']:
        session.clear()
        flash('Sua sessão foi encerrada. Entre novamente.', 'error')
        return redirect(url_for('login'))
    session['role'] = usuario['role']
    session['username'] = usuario['username']
    if session.get('trocar_senha') and request.endpoint not in ENDPOINTS_LIVRES:
        flash('Troque a senha padrão antes de continuar.', 'error')
        return redirect(url_for('trocar_senha'))
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        ip = request.remote_addr

        espera = tempo_bloqueio_login(username, ip)
        if espera:
            minutos = max(1, -(-int(espera.total_seconds()) // 60))
            registrar_log(None, 'login_bloqueado', 'WARNING', {'username': username}, request=request)
            return render_template(
                'login.html',
                error=f'Muitas tentativas erradas. Tente novamente em {minutos} minuto(s).'), 429

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ? AND ativo = 1', (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password_hash'], password):
                limpar_falhas_login(username)
                session.clear()
                session.permanent = True
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                registrar_log(
                    user['id'],
                    'login',
                    'INFO',
                    {'result': 'success'},
                    request=request
                )
                if password == SENHA_PADRAO:
                    session['trocar_senha'] = True
                    flash('Você entrou com a senha padrão. Cadastre uma senha nova.', 'error')
                    return redirect(url_for('trocar_senha'))
                return redirect(url_for('index'))
            else:
                registrar_falha_login(username, ip)
                registrar_log(None, 'login_falha', 'WARNING', {'username': username}, request=request)
                return render_template('login.html', error='Credenciais inválidas')
    
    return render_template('login.html')

@app.route('/conta/senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if request.method == 'POST':
        atual = request.form.get('senha_atual', '')
        nova = request.form.get('nova_senha', '')
        confirmacao = request.form.get('confirmacao', '')
        usuario = get_user_by_id(session['user_id'])

        erro = None
        if not check_password_hash(usuario['password_hash'], atual):
            erro = 'Senha atual incorreta.'
        elif len(nova) < 6:
            erro = 'A nova senha deve ter pelo menos 6 caracteres.'
        elif nova == SENHA_PADRAO or nova == atual:
            erro = 'Escolha uma senha diferente da atual e da senha padrão.'
        elif nova != confirmacao:
            erro = 'A confirmação não confere com a nova senha.'
        if erro:
            return render_template('conta/senha.html', error=erro)

        update_user(session['user_id'], password=nova)
        session.pop('trocar_senha', None)
        registrar_log(session['user_id'], 'trocar_senha', 'INFO', request=request)
        flash('Senha alterada com sucesso.', 'success')
        return redirect(url_for('index'))
    return render_template('conta/senha.html')


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

def _erro_na_foto(foto):
    """Mensagem de erro se a foto enviada for inválida; None se estiver ok ou não houver foto."""
    if not foto or foto.filename == '':
        return None
    if not allowed_file(foto.filename):
        return "Apenas arquivos JPG, JPEG e PNG são permitidos!"
    foto.stream.seek(0, os.SEEK_END)
    tamanho = foto.stream.tell()
    foto.stream.seek(0)
    if tamanho > app.config['MAX_FILE_SIZE_MB'] * 1024 * 1024:
        return f"Arquivo muito grande! Tamanho máximo: {app.config['MAX_FILE_SIZE_MB']}MB"
    return None


def _formulario_produto(template, **contexto):
    """Renderiza o cadastro/edição com as listas de fornecedores e categorias."""
    return render_template(template, fornecedores=get_fornecedores(),
                           categorias=get_categorias(), **contexto)


@app.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_produto():
    if request.method == 'POST':
        foto = request.files.get('foto')
        erro = _erro_na_foto(foto)
        if erro:
            return _formulario_produto('produtos/novo.html', error=erro, form_data=request.form)
        try:
            inserir_produto(request.form, foto)
        except ValueError as e:
            return _formulario_produto('produtos/novo.html', error=str(e), form_data=request.form)
        except Exception as e:
            logging.error(f"Erro ao cadastrar produto: {str(e)}", exc_info=True)
            return _formulario_produto('produtos/novo.html',
                                       error="Erro ao cadastrar produto. Verifique os dados.",
                                       form_data=request.form)
        flash(f'Produto "{request.form.get("nome", "").strip()}" cadastrado.', 'success')
        return redirect(url_for('listar_produtos'))

    return _formulario_produto('produtos/novo.html')

@app.route('/produtos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def editar_produto(id):
    produto = get_produto_by_id(id)
    if not produto or not produto['ativo']:
        abort(404)

    if request.method == 'POST':
        foto = request.files.get('foto')
        erro = _erro_na_foto(foto)
        if erro:
            return _formulario_produto('produtos/editar.html', produto=produto, error=erro)
        try:
            atualizar_produto(id, request.form, foto)
        except ValueError as e:
            return _formulario_produto('produtos/editar.html', produto=produto, error=str(e))
        except Exception as e:
            logging.error(f"Erro ao atualizar produto: {str(e)}", exc_info=True)
            return _formulario_produto('produtos/editar.html', produto=produto,
                                       error="Erro ao atualizar produto. Verifique os dados.")
        flash(f'Produto "{produto["nome"]}" atualizado.', 'success')
        return redirect(url_for('listar_produtos'))

    return _formulario_produto('produtos/editar.html', produto=produto)

@app.route('/produtos/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_produto_route(id):
    try:
        if excluir_produto(id) == 'desativado':
            flash('O produto já tem vendas registradas, então foi desativado '
                  '(o histórico de vendas foi mantido).', 'success')
        else:
            flash('Produto excluído.', 'success')
    except ValueError as ve:
        flash(str(ve), 'error')
    except Exception as e:
        logging.error(f"Erro ao excluir produto: {str(e)}", exc_info=True)
        flash('Erro interno ao excluir produto.', 'error')
    return redirect(url_for('listar_produtos'))
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



def validar_cnpj(cnpj):
    """True se o CNPJ tem 14 dígitos e os dois dígitos verificadores conferem."""
    digitos = re.sub(r'\D', '', cnpj or '')
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False

    def digito_verificador(base):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return '0' if resto < 2 else str(11 - resto)

    return (digitos[12] == digito_verificador(digitos[:12])
            and digitos[13] == digito_verificador(digitos[:13]))


def formatar_cnpj(cnpj):
    digitos = re.sub(r'\D', '', cnpj or '')
    if len(digitos) != 14:
        return (cnpj or '').strip()
    return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'


def _dados_fornecedor(form, cnpj_atual=None):
    """Valida e padroniza o formulário de fornecedor. Um CNPJ já cadastrado e
    não alterado é aceito mesmo sem dígitos válidos (cadastros anteriores à validação)."""
    dados = {
        'nome': form.get('nome', '').strip(),
        'cnpj': formatar_cnpj(form.get('cnpj', '')),
        'contato': form.get('contato', '').strip(),
        'endereco': form.get('endereco', '').strip() or None,
    }
    if not dados['nome'] or not dados['contato']:
        raise ValueError('Nome e contato são obrigatórios.')
    if dados['cnpj'] != cnpj_atual and not validar_cnpj(dados['cnpj']):
        raise ValueError('CNPJ inválido: confira os 14 dígitos.')
    return dados


@app.route('/fornecedores/novo', methods=['GET', 'POST'])
@login_required
@role_required('gerente')
def novo_fornecedor():
    if request.method == 'POST':
        try:
            dados = _dados_fornecedor(request.form)
            create_fornecedor(**dados)
            flash(f'Fornecedor "{dados["nome"]}" cadastrado.', 'success')
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
        try:
            dados = _dados_fornecedor(request.form, cnpj_atual=fornecedor['cnpj'])
            update_fornecedor(id, **dados)
            flash(f'Fornecedor "{dados["nome"]}" atualizado.', 'success')
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
    fornecedor = get_fornecedor_by_id(id)
    if not fornecedor:
        flash('Fornecedor não encontrado.', 'error')
        return redirect(url_for('listar_fornecedores'))
    try:
        with get_db_connection() as conn:
            vinculados = conn.execute(
                'SELECT COUNT(*) FROM produtos WHERE fornecedor_id = ?', (id,)).fetchone()[0]
        delete_fornecedor(id)
    except Exception as e:
        logging.error(f"Erro ao excluir fornecedor: {e}", exc_info=True)
        flash('Erro ao excluir fornecedor.', 'error')
        return redirect(url_for('listar_fornecedores'))
    mensagem = f'Fornecedor "{fornecedor["nome"]}" excluído.'
    if vinculados:
        mensagem += f' {vinculados} produto(s) ficaram sem fornecedor.'
    flash(mensagem, 'success')
    return redirect(url_for('listar_fornecedores'))

# Gestão de Vendas

@app.route('/vendas/nova', methods=['GET', 'POST'])
@login_required
def nova_venda():
    if request.method == 'POST':
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Usuário não autenticado'}), 401

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Dados da venda inválidos'}), 400
        if not data.get('metodo_pagamento'):
            return jsonify({'success': False, 'error': 'Informe a forma de pagamento'}), 400
        metodo_pagamento = normalizar_forma_pagamento(data.get('metodo_pagamento'))
        if metodo_pagamento is None:
            return jsonify({'success': False, 'error': 'Forma de pagamento inválida'}), 400
        data_vencimento = data.get('data_vencimento')
        data_venda = data.get('data_venda')

        # Validação da data da venda
        if not data_venda:
            return jsonify({'success': False, 'error': 'Data da venda obrigatória'}), 400

        try:
            data_venda = datetime.strptime(str(data_venda), '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Formato de data inválido (use AAAA-MM-DD)'}), 400

        if metodo_pagamento == 'pagamento_prazo':
            if not data_vencimento:
                return jsonify({'success': False, 'error': 'Data de vencimento obrigatória'}), 400
            try:
                vencimento = datetime.strptime(str(data_vencimento), '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Formato de data de vencimento inválido (use AAAA-MM-DD)'}), 400
            if vencimento < datetime.today().date():
                return jsonify({'success': False, 'error': 'Data de vencimento inválida'}), 400

        cliente_cpf = data.get('cpf')
        cliente_nome = data.get('nome_cliente')
        status_pagamento = 'pendente' if metodo_pagamento == 'pagamento_prazo' else 'pago'

        agora = datetime.now()
        venda_data = {
            # Venda de hoje guarda a hora; venda lançada em outra data guarda só o dia
            'data_venda': (agora.strftime('%Y-%m-%d %H:%M:%S') if data_venda == agora.date()
                           else data_venda.isoformat()),
            'cliente_cpf': cliente_cpf,
            'cliente_nome': cliente_nome,
            'metodo_pagamento': metodo_pagamento,
            'itens': data.get('itens'),  # preço e total são calculados no servidor
            'status_pagamento': status_pagamento,
            'data_vencimento': data_vencimento,
            'observacao': data.get('observacao')
        }
        # Sufixo aleatório: duas vendas no mesmo segundo não colidem na chave
        venda_id = f"V{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"

        try:
            processar_venda(venda_id, venda_data, user_id)
            return jsonify({'success': True, 'venda_id': venda_id})
        except ValueError as ve:
            return jsonify({'success': False, 'error': str(ve)}), 400
        except Exception as e:
            logging.error(f"Erro ao processar venda: {e}")
            return jsonify({'success': False, 'error': 'Erro ao registrar venda'}), 500

    # GET: Adicionar data atual como padrão
    produtos = listar_produtos_simples()
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('vendas/nova.html', produtos=produtos, current_date=current_date,
                           formas_pagamento=FORMAS_PAGAMENTO)


# ---------------------------------------------------------------
# Relatórios

# Movimentação de caixa por dia: consulta compartilhada com o PDF (ver gerador_pdf.py)

@app.route('/relatorios')
@login_required
@role_required('gerente')
def relatorios():
    return render_template('relatorios/dashboard.html')


# Colunas de cada relatório: (campo da consulta, título, formato).
# Formatos: moeda, quantidade (até 3 casas, para kg), inteiro, data, texto.
COLUNAS_RELATORIOS = {
    'vendas_periodo': [('data', 'Data', 'data'), ('total_vendas', 'Vendas', 'inteiro'),
                       ('valor_total', 'Valor total', 'moeda'), ('ticket_medio', 'Ticket médio', 'moeda')],
    'vendas_categorias': [('categoria', 'Categoria', 'texto'),
                          ('quantidade_vendida', 'Quantidade vendida', 'quantidade'),
                          ('valor_total', 'Valor total', 'moeda')],
    'top_produtos': [('nome', 'Produto', 'texto'), ('quantidade_vendida', 'Quantidade vendida', 'quantidade'),
                     ('valor_total', 'Valor total', 'moeda')],
    'estoque_nivel': [('nome', 'Produto', 'texto'), ('quantidade', 'Em estoque', 'quantidade'),
                      ('estoque_minimo', 'Estoque mínimo', 'quantidade'), ('diferenca', 'Diferença', 'quantidade')],
    'estoque_validade': [('nome', 'Produto', 'texto'), ('data_validade', 'Validade', 'data'),
                         ('dias_restantes', 'Dias restantes', 'inteiro')],
    'clientes_fieis': [('cliente_nome', 'Cliente', 'texto'), ('total_compras', 'Compras', 'inteiro'),
                       ('valor_total_gasto', 'Valor gasto', 'moeda')],
    'fornecedores_produtos': [('fornecedor', 'Fornecedor', 'texto'), ('total_produtos', 'Produtos', 'inteiro'),
                              ('total_estoque', 'Itens em estoque', 'quantidade')],
    'movimentacao_caixa': [('data', 'Data', 'data'), ('valor_a_vista', 'À vista', 'moeda'),
                           ('valor_fiado_recebido', 'Fiado recebido', 'moeda'),
                           ('total_entradas', 'Total recebido', 'moeda'),
                           ('valor_vendido_a_prazo', 'Vendido a prazo', 'moeda')],
    'comparativo': [('periodo', 'Período', 'texto'), ('total_vendas', 'Vendas', 'inteiro'),
                    ('valor_total', 'Valor total', 'moeda')],
}


# Helper functions para relatórios
def parse_date(date_str, default):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date().isoformat()
    except (TypeError, ValueError):
        return default


def _arg_inteiro(nome, padrao, minimo, maximo):
    """Parâmetro inteiro da URL; valores inválidos viram o padrão e são limitados à faixa."""
    valor = request.args.get(nome, padrao, type=int)
    return max(minimo, min(maximo, valor))


@app.route('/relatorios/<report_type>')
@login_required
@role_required('gerente')
def relatorios_unificados(report_type):
    hoje = datetime.now().date()
    inicio_periodo = parse_date(request.args.get('start_date'), hoje.replace(day=1).isoformat())
    fim_periodo = parse_date(request.args.get('end_date'), hoje.isoformat())
    limite = _arg_inteiro('limit', 10, 1, 100)
    dias_validade = _arg_inteiro('dias', 30, 0, 3650)
    agrupar_por_ano = request.args.get('periodo') == 'year'

    report_titles = {
        'vendas_totais': 'Vendas Totais',
        'vendas_periodo': 'Vendas por Período',
        'vendas_categorias': 'Vendas por Categoria',
        'top_produtos': 'Top Produtos Vendidos',
        'estoque_nivel': 'Nível de Estoque Crítico',
        'estoque_validade': 'Produtos Próximos do Vencimento',
        'clientes_fieis': 'Clientes Mais Fieis',
        'fornecedores_produtos': 'Produtos por Fornecedor',
        'movimentacao_caixa': 'Movimentação de Caixa',
        'comparativo': 'Comparativo de Vendas'
    }

    # Configurations for all reports (now consolidated to be rendered as HTML)
    reports = {
        'vendas_totais': {
            'query': '''
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
            '''
        },
        'vendas_periodo': {
            'query': '''
                SELECT DATE(v.data) as data, COUNT(*) as total_vendas,
                SUM(v.total) as valor_total, AVG(v.total) as ticket_medio
                FROM vendas v
                WHERE DATE(v.data) BETWEEN ? AND ?
                GROUP BY DATE(v.data) ORDER BY data
            ''',
            'params': (inicio_periodo, fim_periodo)
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
            'params': (limite,)
        },
        'estoque_nivel': {
            'query': '''
                SELECT nome, quantidade, estoque_minimo, (quantidade - estoque_minimo) as diferenca
                FROM produtos WHERE ativo = 1 AND quantidade < estoque_minimo ORDER BY diferenca ASC
            '''
        },
        'estoque_validade': {
            'query': '''
                SELECT nome, data_validade,
                CAST(JULIANDAY(data_validade) - JULIANDAY(?) AS INTEGER) as dias_restantes
                FROM produtos WHERE ativo = 1 AND data_validade IS NOT NULL
                AND dias_restantes BETWEEN 0 AND ? ORDER BY data_validade
            ''',
            'params': (hoje.isoformat(), dias_validade)
        },
        'clientes_fieis': {
            'query': '''
                SELECT cliente_nome, COUNT(*) as total_compras, SUM(total) as valor_total_gasto
                FROM vendas WHERE cliente_nome IS NOT NULL
                GROUP BY cliente_nome ORDER BY total_compras DESC LIMIT ?
            ''',
            'params': (limite,)
        },
        'fornecedores_produtos': {
            'query': '''
                SELECT f.nome as fornecedor, COUNT(p.id) as total_produtos, SUM(p.quantidade) as total_estoque
                FROM fornecedores f LEFT JOIN produtos p ON f.id = p.fornecedor_id
                GROUP BY f.id ORDER BY total_produtos DESC
            '''
        },
        # Entradas pela data em que o dinheiro entrou; fiado vendido é conta a receber,
        # não saída de caixa
        'movimentacao_caixa': {
            'query': SQL_MOVIMENTACAO_CAIXA + ' ORDER BY data DESC'
        },
        'comparativo': {
            'query': '''
                SELECT strftime('{group_format}', data) as periodo,
                COUNT(*) as total_vendas, SUM(total) as valor_total
                FROM vendas GROUP BY periodo ORDER BY periodo DESC LIMIT 12
            ''',
            'params': (),
            'pre_process': lambda: {'group_format': '%Y' if agrupar_por_ano else '%Y-%m'}
        }
    }

    config = reports.get(report_type)
    if not config:
        abort(404, description="Relatório não encontrado")
    colunas = COLUNAS_RELATORIOS.get(report_type)

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

    return render_template('relatorio_unificado.html',
                           dados=dados,
                           colunas=colunas,
                           report_type=report_type,
                           titulo_relatorio=report_titles.get(report_type, 'Relatório'))



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
    usuarios = [dict(u) for u in get_all_users()]
    return render_template('admin/usuarios.html', usuarios=usuarios)

@app.route('/admin/estoque')
@login_required
@role_required('gerente')
def admin_estoque():
    # Obtém todos os produtos e filtra alerta de estoque
    produtos = get_all_produtos()
    estoque = [
        p for p in produtos
        if p['quantidade'] < (p['estoque_minimo'] or 0)
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
            flash(f'Usuário {username} criado com sucesso.', 'success')
            return redirect(url_for('admin_usuarios'))
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


def _contar_gerentes_ativos(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'gerente' AND ativo = 1").fetchone()[0]


@app.route('/admin/usuarios/editar/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def editar_usuario(id):
    new_role = request.form.get('role')
    if new_role not in ['gerente', 'funcionario']:
        abort(400)
    try:
        with get_db_connection() as conn:
            usuario = conn.execute(
                "SELECT username, role FROM users WHERE id = ? AND ativo = 1", (id,)).fetchone()
            if usuario is None:
                flash('Usuário não encontrado.', 'error')
                return redirect(url_for('admin_usuarios'))
            # Impedir que o último gerente seja rebaixado
            if (usuario['role'] == 'gerente' and new_role == 'funcionario'
                    and _contar_gerentes_ativos(conn) == 1):
                flash('Não é possível rebaixar o último gerente.', 'error')
                return redirect(url_for('admin_usuarios'))

        update_user_role(id, new_role)
        registrar_log(session['user_id'], 'update_user_role', 'INFO',
                      {'user_id': id, 'username': usuario['username'], 'role': new_role},
                      request=request)
        flash(f'Cargo de {usuario["username"]} atualizado.', 'success')
    except Exception as e:
        logging.error(f"Erro ao atualizar usuário: {str(e)}", exc_info=True)
        flash('Erro ao atualizar usuário.', 'error')
    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
@role_required('gerente')
def excluir_usuario(id):
    if id == session['user_id']:
        flash('Você não pode excluir a própria conta.', 'error')
        return redirect(url_for('admin_usuarios'))
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT username, role FROM users WHERE id = ? AND ativo = 1", (id,)).fetchone()
            if user is None:
                flash('Usuário não encontrado.', 'error')
                return redirect(url_for('admin_usuarios'))
            # Verificar se é o último gerente
            if user['role'] == 'gerente' and _contar_gerentes_ativos(conn) == 1:
                flash('Não é possível excluir o último gerente.', 'error')
                return redirect(url_for('admin_usuarios'))

        resultado = delete_user(id)
        registrar_log(session['user_id'], 'delete_user', 'INFO',
                      {'user_id': id, 'username': user['username'], 'resultado': resultado},
                      request=request)
        if resultado == 'desativado':
            flash(f'Usuário {user["username"]} desativado: ele tem vendas registradas, '
                  'que foram mantidas no histórico.', 'success')
        else:
            flash(f'Usuário {user["username"]} excluído.', 'success')
    except Exception as e:
        logging.error(f"Erro ao excluir usuário: {str(e)}", exc_info=True)
        flash('Erro ao excluir usuário.', 'error')
    return redirect(url_for('admin_usuarios'))




# Dashboard Principal

def intervalo_de_hoje():
    """(hoje, amanhã) em horário local, para filtrar 'data >= ? AND data < ?'.
    O DATE('now') do SQLite é UTC: depois das 21h, no Brasil, já seria amanhã."""
    hoje = datetime.now().date()
    return hoje.isoformat(), (hoje + timedelta(days=1)).isoformat()


@app.route('/dashboard')
@login_required
def dashboard():
    hoje = intervalo_de_hoje()
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
            WHERE v.data >= ? AND v.data < ?
            ORDER BY v.data DESC
        ''', hoje)
        data['vendas_hoje'] = [dict(zip([column[0] for column in cursor.description], row)) 
                       for row in cursor.fetchall()]

        data['total_dia'] = round(sum(v['total'] or 0 for v in data['vendas_hoje']), 2)

        cursor.execute('''
            SELECT nome, quantidade, estoque_minimo
            FROM produtos
            WHERE ativo = 1 AND quantidade < estoque_minimo
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
                WHERE data >= ? AND data < ?
            ''', hoje)
            data.update(cursor.fetchone())

            cursor.execute('''
                SELECT metodo_pagamento, COUNT(*) as quantidade,
                       SUM(total) as valor_total
                FROM vendas
                WHERE data >= ? AND data < ?
                GROUP BY metodo_pagamento
            ''', hoje)
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
    if marcar_venda_pago(venda_id):
        registrar_log(session['user_id'], 'pagar_fiado', 'INFO', {'venda_id': venda_id},
                      request=request)
        flash(f'Pagamento da venda {venda_id} registrado.', 'success')
    else:
        flash('Venda não encontrada, não é a prazo ou já estava paga.', 'error')
    return redirect(url_for('listar_vendas_prazo'))

@app.route('/vendas/listar_vendas_prazo/adicionar_observacao/<venda_id>', methods=['POST'])
@login_required
@role_required('gerente')
def adicionar_observacao_venda_prazo(venda_id):
    observacao = request.form.get('observacao', '')
    adicionar_observacao_venda(venda_id, observacao)
    flash('Observação salva.', 'success')
    return redirect(url_for('listar_vendas_prazo'))


# Utilitários
@app.route('/logs')
@login_required
@role_required('gerente')
def visualizar_logs():
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = 20
    filtros = {
        campo: request.args.get(campo, '').strip()
        for campo in ('search', 'level', 'user_id', 'action', 'start_date', 'end_date')
    }

    logs, total = listar_logs(page=page, per_page=per_page, **filtros)
    total_pages = max((total + per_page - 1) // per_page, 1)
    # Os cartões mostram a distribuição por nível, então ignoram o filtro de nível
    contagem = contar_logs_por_nivel(
        **{campo: valor for campo, valor in filtros.items() if campo != 'level'})

    # Obter nomes de usuários para o filtro
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users ORDER BY username")
        usuarios = {row['id']: row['username'] for row in cursor.fetchall()}

    for log in logs:
        log['usuario'] = _nome_usuario_log(log['user_id'], usuarios)
        log['detalhes'] = _ler_detalhes_log(log['details'])

    return render_template('logs.html',
                           logs=logs,
                           total=total,
                           page=page,
                           total_pages=total_pages,
                           contagem=contagem,
                           usuarios=usuarios,
                           acoes=listar_acoes_logs(),
                           filtros={campo: valor for campo, valor in filtros.items() if valor})


def _nome_usuario_log(user_id, usuarios):
    if user_id is None or user_id == '':
        return '—'
    try:
        return usuarios.get(int(user_id), f'#{user_id}')
    except (TypeError, ValueError):
        return str(user_id)  # eventos do sistema gravam um texto, ex.: 'Sistema'


def _ler_detalhes_log(details):
    if not details:
        return None
    try:
        return json.loads(details)
    except ValueError:
        return details

@app.template_filter('format_currency')
def format_currency(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

app.jinja_env.filters['format_currency'] = format_currency


@app.template_filter('format_quantidade')
def format_quantidade(value):
    """Número com até 3 casas decimais e vírgula (2.357 -> '2,357'; 10.0 -> '10')."""
    try:
        return f"{float(value):.3f}".rstrip('0').rstrip('.').replace('.', ',')
    except (TypeError, ValueError):
        return '-'


@app.template_filter('formatar_celula')
def formatar_celula(valor, formato):
    if valor is None or valor == '':
        return '-'
    if formato == 'moeda':
        return format_currency(valor)
    if formato == 'quantidade':
        return format_quantidade(valor)
    if formato == 'inteiro':
        try:
            return f"{int(round(float(valor))):,}".replace(',', '.')
        except (TypeError, ValueError):
            return valor
    if formato == 'data':
        return format_datetime(valor, '%d/%m/%Y')
    return valor


@app.template_filter('miniatura')
def miniatura(foto):
    """Caminho (relativo a static/) da miniatura da foto, ou da própria foto
    enquanto a miniatura não existir."""
    if not foto:
        return ''
    if os.path.exists(caminho_miniatura(app.config['UPLOAD_FOLDER'], foto)):
        return f'uploads/produtos/{PASTA_MINIATURAS}/{os.path.basename(foto)}.webp'
    return f'uploads/produtos/{foto}'


@app.template_filter('forma_pagamento')
def forma_pagamento(valor):
    return FORMAS_PAGAMENTO.get(valor, valor or '—')

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
                WHERE ativo = 1 AND data_validade BETWEEN ? AND ?
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

@app.errorhandler(403)
def acesso_negado(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500


scheduler = BackgroundScheduler(daemon=True)


def iniciar_tarefas_agendadas():
    """Verificação de validades na inicialização e a cada 24h. O backup é conferido
    a cada hora, mas só é feito quando o último tem mais de 24h."""
    scheduler.add_job(verificar_validades, 'interval', hours=24)
    scheduler.add_job(backup_se_necessario, 'interval', hours=1)
    # Miniaturas das fotos que ainda não têm (em segundo plano, não atrasa a abertura)
    scheduler.add_job(gerar_miniaturas_faltantes, args=[app.config['UPLOAD_FOLDER']])
    scheduler.start()
    backup_se_necessario()
    verificar_validades()


def configuracao_execucao():
    """Parâmetros do servidor lidos do ambiente. O modo debug expõe o debugger
    do Werkzeug (execução de código pelo navegador), então só liga com FLASK_DEBUG=1."""
    return {
        'debug': os.environ.get('FLASK_DEBUG', '').strip().lower() in ('1', 'true', 'sim', 'yes'),
        'host': os.environ.get('FLASK_RUN_HOST', '127.0.0.1'),
        'port': int(os.environ.get('FLASK_RUN_PORT', 5000)),
    }


if __name__ == '__main__':
    execucao = configuracao_execucao()
    # Com o reloader do modo debug este bloco roda no processo pai e no filho;
    # as tarefas só sobem no processo que atende as requisições.
    if not execucao['debug'] or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        iniciar_tarefas_agendadas()
    try:
        app.run(**execucao)
    finally:
        if scheduler.running:
            scheduler.shutdown()