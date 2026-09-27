import sqlite3
import os
import math
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging

from flask import current_app
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from imagens import gerar_miniatura, remover_miniatura

DB_PATH = os.environ.get('DB_PATH', 'acougue.db')

# Versão do esquema gravada em PRAGMA user_version. Ao mudar o esquema,
# incremente e acrescente o passo correspondente em _migrar().
SCHEMA_VERSION = 3

# Prefixo que versões antigas gravavam no campo produtos.foto
PREFIXO_FOTO_ANTIGO = 'uploads/produtos/'

# Valor gravado no banco -> texto exibido. 'pagamento_prazo' é o fiado.
FORMAS_PAGAMENTO = {
    'dinheiro': 'Dinheiro',
    'debito': 'Cartão de Débito',
    'credito': 'Cartão de Crédito',
    'pix': 'PIX',
    'pagamento_prazo': 'Pagamento a Prazo',
}

# Textos gravados por versões antigas (as opções do select não tinham value)
_FORMAS_PAGAMENTO_ANTIGAS = {
    'dinheiro': 'dinheiro',
    'cartão débito': 'debito', 'cartao debito': 'debito', 'débito': 'debito', 'debito': 'debito',
    'cartão crédito': 'credito', 'cartao credito': 'credito', 'crédito': 'credito', 'credito': 'credito',
    'pix': 'pix',
    'pagamento_prazo': 'pagamento_prazo', 'fiado': 'pagamento_prazo',
}

# Categorias do cadastro original (popular_banco.py). A migração 2 devolve a
# categoria certa aos produtos que o formulário de edição antigo trocou para
# "Bovino"/"Suíno"/"Aves" (o select só tinha essas opções).
_CATEGORIAS_ORIGINAIS = {
    'Coração': 'BOI', 'Fígado': 'BOI', 'Bisteca': 'BOI', 'Bisteca bovina': 'BOI',
    'Paleta': 'BOI', 'Costela': 'BOI', 'Polpa ou Coxa Mole': 'BOI',
    'Patim ou Caturrino': 'BOI', 'Alcatra': 'BOI', 'Mão de Vaca': 'BOI', 'Filé': 'BOI',
    'Filé de boi': 'BOI', 'Ossada': 'BOI', 'Panelada (Prato)': 'BOI', 'Picanha': 'BOI',
    'Demais Carnes Magicas': 'BOI', 'Carne Moída Pronta': 'BOI',
    'Com Toucinho': 'PORCO', 'Sem Toucinho': 'PORCO',
    'Carneiro': 'CARNEIRO',
    'Abatido': 'FRANGOS', 'Peito': 'FRANGOS', 'Coxa': 'FRANGOS', 'Sobrecoxa': 'FRANGOS',
    'Linguiça Toscana Dália': 'CONGELADOS', 'Aurora': 'CONGELADOS',
    'Linguiça Calabresa Dália': 'CONGELADOS', 'Seara ou Perdigão': 'CONGELADOS',
    'Bisteca Suína': 'CONGELADOS', 'Pernil Suíno': 'CONGELADOS', 'Lapa de Filé': 'CONGELADOS',
    'Bacon': 'CONGELADOS', 'Presunto': 'CONGELADOS',
    'Budweiser 350ml': 'BEBIDAS', 'Budweiser 550ml': 'BEBIDAS', 'Corona 330ml': 'BEBIDAS',
    'Guaraná 350ml': 'BEBIDAS', 'Guaraná 1L': 'BEBIDAS', 'Guaraná 2L': 'BEBIDAS',
    'H2O': 'BEBIDAS', 'Heineken Original': 'BEBIDAS', 'Heineken Original 330 ml': 'BEBIDAS',
    'Heineken Original 250ml': 'BEBIDAS', 'Skol 350ml': 'BEBIDAS',
    'Stella Artois 600ml': 'BEBIDAS', 'Sukita 2L': 'BEBIDAS', 'Pepsi 1L': 'BEBIDAS',
    'Pepsi 2L': 'BEBIDAS', 'Pepsi 350ml': 'BEBIDAS',
}
_CATEGORIAS_DO_FORMULARIO_ANTIGO = ('Bovino', 'Suíno', 'Aves')

_CENTAVO = Decimal('0.01')
_GRAMA = Decimal('0.001')


def _decimal(valor):
    """Converte número ou texto ("45,90") em Decimal; ValueError se inválido."""
    if isinstance(valor, bool):
        raise ValueError('valor inválido')
    texto = str(valor).strip().replace(',', '.')
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError('valor inválido')
    if not numero.is_finite():
        raise ValueError('valor inválido')
    return numero


def arredondar_dinheiro(valor):
    """Valor em reais arredondado para centavos (meio para cima, como no caixa)."""
    return float(_decimal(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP))


def arredondar_quantidade(valor):
    """Quantidade com no máximo 3 casas (gramas, nos produtos vendidos por quilo)."""
    return float(_decimal(valor).quantize(_GRAMA, rounding=ROUND_HALF_UP))


def normalizar_forma_pagamento(valor):
    """Valor aceito em FORMAS_PAGAMENTO, ou None se não for uma forma válida."""
    chave = str(valor or '').strip().lower()
    return _FORMAS_PAGAMENTO_ANTIGAS.get(chave)


def agora_texto():
    """Data e hora locais no formato gravado no banco."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def ler_data_hora(valor):
    """Converte o texto gravado no banco em (datetime, tem_hora).
    Aceita 'AAAA-MM-DD', 'AAAA-MM-DD HH:MM:SS' e a variante com microssegundos
    que versões antigas gravavam. Retorna (None, False) se não for uma data."""
    if not valor:
        return None, False
    if isinstance(valor, datetime):
        return valor, True
    texto = str(valor).strip()
    try:
        return datetime.fromisoformat(texto), len(texto) > 10
    except ValueError:
        return None, False


def _caminho_banco():
    return os.environ.get('DB_PATH', 'acougue.db')


@contextmanager
def get_db_connection():
    db_path = _caminho_banco()
    # Usar URI para permitir compartilhamento em memória
    conn = sqlite3.connect(f'file:{db_path}', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# Esquema atual. vendas e venda_itens usam {nome} porque a migração 1
# recria essas tabelas com outro nome antes de renomeá-las.
_SQL_USERS = '''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'funcionario',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ativo INTEGER NOT NULL DEFAULT 1
    )
'''

_SQL_FORNECEDORES = '''
    CREATE TABLE IF NOT EXISTS fornecedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cnpj TEXT UNIQUE NOT NULL,
        contato TEXT NOT NULL,
        endereco TEXT
    )
'''

# quantidade e estoque_minimo são REAL: produtos por quilo têm estoque fracionado
_SQL_PRODUTOS = '''
    CREATE TABLE IF NOT EXISTS {nome} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT,
        categoria TEXT NOT NULL,
        preco NUMERIC NOT NULL,
        quantidade REAL NOT NULL,
        estoque_minimo REAL DEFAULT 0,
        codigo_barras TEXT UNIQUE,
        foto TEXT,
        fornecedor_id INTEGER REFERENCES fornecedores(id)
          ON DELETE SET NULL ON UPDATE CASCADE,
        data_validade DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo_venda TEXT NOT NULL DEFAULT 'unidade',
        ativo INTEGER NOT NULL DEFAULT 1
    )
'''

_SQL_TRIGGER_PRODUTOS = '''
    CREATE TRIGGER IF NOT EXISTS trg_update_produtos_updated_at
    AFTER UPDATE ON produtos
    FOR EACH ROW
    BEGIN
        UPDATE produtos SET updated_at = datetime('now', 'localtime') WHERE id = NEW.id;
    END;
'''

# Sem ON DELETE em usuario_id: excluir um usuário com vendas é bloqueado
# pelo banco, e o sistema desativa o usuário em vez de apagar o histórico.
_SQL_VENDAS = '''
    CREATE TABLE IF NOT EXISTS {nome} (
        id TEXT PRIMARY KEY,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        cliente_cpf TEXT,
        cliente_nome TEXT,
        total NUMERIC NOT NULL,
        metodo_pagamento TEXT NOT NULL,
        usuario_id INTEGER NOT NULL REFERENCES users(id) ON UPDATE CASCADE,
        status_pagamento TEXT NOT NULL DEFAULT 'pago',
        data_vencimento DATE,
        observacao TEXT,
        data_pagamento TIMESTAMP
    )
'''

# Excluir a venda leva os itens junto; excluir um produto vendido é bloqueado.
_SQL_VENDA_ITENS = '''
    CREATE TABLE IF NOT EXISTS {nome} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id TEXT NOT NULL REFERENCES vendas(id)
          ON DELETE CASCADE ON UPDATE CASCADE,
        produto_id INTEGER NOT NULL REFERENCES produtos(id) ON UPDATE CASCADE,
        quantidade REAL NOT NULL,
        preco_unitario NUMERIC NOT NULL
    )
'''

_SQL_LOGS = '''
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
'''


# Tentativas de login erradas, para bloquear adivinhação de senha (SEC-04)
_SQL_LOGIN_FALHAS = '''
    CREATE TABLE IF NOT EXISTS login_falhas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        ip TEXT,
        momento TIMESTAMP NOT NULL
    )
'''

# Criados depois das migrações: recriar uma tabela apaga os índices dela
_INDICES = (
    'CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data)',
    'CREATE INDEX IF NOT EXISTS idx_vendas_metodo_status ON vendas(metodo_pagamento, status_pagamento)',
    'CREATE INDEX IF NOT EXISTS idx_vendas_usuario ON vendas(usuario_id)',
    'CREATE INDEX IF NOT EXISTS idx_venda_itens_venda ON venda_itens(venda_id)',
    'CREATE INDEX IF NOT EXISTS idx_venda_itens_produto ON venda_itens(produto_id)',
    'CREATE INDEX IF NOT EXISTS idx_produtos_categoria ON produtos(categoria)',
    'CREATE INDEX IF NOT EXISTS idx_produtos_nome ON produtos(nome)',
    'CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)',
    'CREATE INDEX IF NOT EXISTS idx_login_falhas_usuario ON login_falhas(username, momento)',
    'CREATE INDEX IF NOT EXISTS idx_login_falhas_ip ON login_falhas(ip, momento)',
)


def _tabela_existe(conn, tabela):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)
    ).fetchone() is not None


def _colunas(conn, tabela):
    return [row['name'] for row in conn.execute(f'PRAGMA table_info({tabela})')]


def init_db():
    """Cria as tabelas que faltam e migra bancos antigos para o esquema atual."""
    with get_db_connection() as conn:
        # Transações controladas manualmente (necessário para as migrações)
        conn.isolation_level = None
        banco_novo = not _tabela_existe(conn, 'users')

        for sql in (_SQL_USERS, _SQL_FORNECEDORES, _SQL_PRODUTOS.format(nome='produtos'),
                    _SQL_TRIGGER_PRODUTOS,
                    _SQL_VENDAS.format(nome='vendas'),
                    _SQL_VENDA_ITENS.format(nome='venda_itens'), _SQL_LOGS, _SQL_LOGIN_FALHAS):
            conn.execute(sql)

        if banco_novo:
            conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        else:
            _migrar(conn)

        for sql in _INDICES:
            conn.execute(sql)


def _migrar(conn):
    versao = conn.execute('PRAGMA user_version').fetchone()[0]
    if versao >= SCHEMA_VERSION:
        return
    _backup_pre_migracao(conn, versao)
    if versao < 1:
        _migracao_1(conn)
    if versao < 2:
        _migracao_2(conn)
    if versao < 3:
        _migracao_3(conn)
    conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')


def _backup_pre_migracao(conn, versao):
    """Copia o banco para backups/ antes de alterar o esquema."""
    db_path = _caminho_banco()
    if 'memory' in db_path:
        return
    pasta = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'backups')
    os.makedirs(pasta, exist_ok=True)
    nome = os.path.splitext(os.path.basename(db_path))[0]
    destino = os.path.join(
        pasta, f"{nome}_pre_migracao_v{versao}_{datetime.now():%Y%m%d_%H%M%S}.db")
    copia = sqlite3.connect(destino)
    try:
        conn.backup(copia)
    finally:
        copia.close()
    logging.info(f"Backup do banco antes da migração salvo em {destino}")


def _fk_on_delete(conn, tabela, tabela_referenciada):
    for fk in conn.execute(f'PRAGMA foreign_key_list({tabela})'):
        if fk['table'] == tabela_referenciada:
            return fk['on_delete']
    return None


def _recriar_tabela(conn, tabela, sql_create):
    """Recria a tabela com o esquema atual preservando os dados
    (procedimento de 12 passos da documentação do SQLite)."""
    temporaria = f'{tabela}_migracao'
    antigas = set(_colunas(conn, tabela))
    conn.execute(sql_create.format(nome=temporaria))
    comuns = ', '.join(c for c in _colunas(conn, temporaria) if c in antigas)
    conn.execute(f'INSERT INTO {temporaria} ({comuns}) SELECT {comuns} FROM {tabela}')
    conn.execute(f'DROP TABLE {tabela}')
    conn.execute(f'ALTER TABLE {temporaria} RENAME TO {tabela}')


def _migracao_1(conn):
    """Exclusão lógica (coluna ativo), fotos gravadas só pelo nome do arquivo
    e chaves estrangeiras que não apagam o histórico de vendas."""
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute('BEGIN')
        for tabela in ('users', 'produtos'):
            if 'ativo' not in _colunas(conn, tabela):
                conn.execute(
                    f'ALTER TABLE {tabela} ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1')

        conn.execute(
            'UPDATE produtos SET foto = substr(foto, ?) WHERE foto LIKE ?',
            (len(PREFIXO_FOTO_ANTIGO) + 1, PREFIXO_FOTO_ANTIGO + '%'))

        if _fk_on_delete(conn, 'vendas', 'users') != 'NO ACTION':
            _recriar_tabela(conn, 'vendas', _SQL_VENDAS)
        if (_fk_on_delete(conn, 'venda_itens', 'produtos') != 'NO ACTION'
                or _fk_on_delete(conn, 'venda_itens', 'vendas') != 'CASCADE'):
            _recriar_tabela(conn, 'venda_itens', _SQL_VENDA_ITENS)

        _avisar_violacoes_fk(conn, 1)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.execute('PRAGMA foreign_keys = ON')


def _avisar_violacoes_fk(conn, migracao):
    violacoes = conn.execute('PRAGMA foreign_key_check').fetchall()
    if violacoes:
        logging.warning(
            f"Migração {migracao}: {len(violacoes)} registros com chave estrangeira inválida "
            f"(dados antigos, mantidos como estão): {[tuple(v) for v in violacoes][:10]}")


def _tipo_coluna(conn, tabela, coluna):
    for row in conn.execute(f'PRAGMA table_info({tabela})'):
        if row['name'] == coluna:
            return (row['type'] or '').upper()
    return None


def _migracao_2(conn):
    """Quantidades decimais, data de pagamento, formas de pagamento padronizadas,
    valores em centavos e categorias trocadas pelo formulário antigo restauradas."""
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute('BEGIN')
        # Sem o trigger, as correções abaixo não alteram updated_at dos produtos
        conn.execute('DROP TRIGGER IF EXISTS trg_update_produtos_updated_at')

        if _tipo_coluna(conn, 'produtos', 'quantidade') != 'REAL':
            _recriar_tabela(conn, 'produtos', _SQL_PRODUTOS)
        if _tipo_coluna(conn, 'venda_itens', 'quantidade') != 'REAL':
            _recriar_tabela(conn, 'venda_itens', _SQL_VENDA_ITENS)
        if 'data_pagamento' not in _colunas(conn, 'vendas'):
            conn.execute('ALTER TABLE vendas ADD COLUMN data_pagamento TIMESTAMP')

        desconhecidas = []
        for (valor,) in conn.execute('SELECT DISTINCT metodo_pagamento FROM vendas').fetchall():
            nova = normalizar_forma_pagamento(valor)
            if nova is None:
                desconhecidas.append(valor)
            elif nova != valor:
                conn.execute('UPDATE vendas SET metodo_pagamento = ? WHERE metodo_pagamento = ?',
                             (nova, valor))
        if desconhecidas:
            logging.warning(f"Migração 2: formas de pagamento não reconhecidas mantidas: {desconhecidas}")

        # Venda à vista é paga no ato; fiado recebe a data quando é quitado
        conn.execute("""
            UPDATE vendas SET data_pagamento = data
            WHERE status_pagamento = 'pago' AND metodo_pagamento != 'pagamento_prazo'
              AND data_pagamento IS NULL
        """)

        conn.execute('UPDATE vendas SET total = ROUND(total, 2) WHERE total != ROUND(total, 2)')
        conn.execute('UPDATE venda_itens SET preco_unitario = ROUND(preco_unitario, 2) '
                     'WHERE preco_unitario != ROUND(preco_unitario, 2)')
        conn.execute('UPDATE produtos SET preco = ROUND(preco, 2) WHERE preco != ROUND(preco, 2)')
        conn.execute('UPDATE produtos SET quantidade = ROUND(quantidade, 3) '
                     'WHERE quantidade != ROUND(quantidade, 3)')

        # O formulário de edição antigo escrevia o texto "None" nos campos vazios
        conn.execute("UPDATE produtos SET descricao = NULL WHERE descricao = 'None'")
        conn.execute("UPDATE produtos SET codigo_barras = NULL WHERE codigo_barras = 'None'")

        antes = conn.total_changes
        marcadores = ', '.join('?' * len(_CATEGORIAS_DO_FORMULARIO_ANTIGO))
        for nome, categoria in _CATEGORIAS_ORIGINAIS.items():
            conn.execute(
                f'UPDATE produtos SET categoria = ? WHERE nome = ? AND categoria IN ({marcadores})',
                (categoria, nome, *_CATEGORIAS_DO_FORMULARIO_ANTIGO))
        conn.execute("UPDATE produtos SET categoria = 'BEBIDAS' WHERE categoria = 'BEBIDA'")
        logging.info(f"Migração 2: categoria restaurada em {conn.total_changes - antes} produtos")

        conn.execute(_SQL_TRIGGER_PRODUTOS)
        _avisar_violacoes_fk(conn, 2)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.execute('PRAGMA foreign_keys = ON')





def _migracao_3(conn):
    """Horário local em vez de UTC: os logs antigos (gravados pelo CURRENT_TIMESTAMP
    do SQLite, em UTC) são convertidos, e o trigger de updated_at passa a usar a
    hora local. Os logs novos já são gravados com a hora local pelo Python."""
    try:
        conn.execute('BEGIN')
        conn.execute("UPDATE logs SET timestamp = datetime(timestamp, 'localtime') "
                     "WHERE timestamp IS NOT NULL")
        conn.execute('DROP TRIGGER IF EXISTS trg_update_produtos_updated_at')
        conn.execute(_SQL_TRIGGER_PRODUTOS)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise

def _clausula_set(campos, permitidos, tabela):
    """Monta "col = ?, ..." só com colunas conhecidas: nomes de coluna não podem
    ir como parâmetro no SQL, então qualquer chave fora da lista é recusada."""
    desconhecidos = set(campos) - permitidos
    if desconhecidos:
        raise ValueError(f"Campo(s) inválido(s) para {tabela}: {', '.join(sorted(desconhecidos))}")
    if not campos:
        raise ValueError(f"Nenhum campo para atualizar em {tabela}")
    return ', '.join(f"{campo} = ?" for campo in campos)


# -----------------------
# Tentativas de login (SEC-04)
# -----------------------
LIMITE_FALHAS_USUARIO = 5    # erros seguidos no mesmo usuário
LIMITE_FALHAS_IP = 20        # erros vindos do mesmo endereço, em qualquer usuário
JANELA_FALHAS = timedelta(minutes=15)


def registrar_falha_login(username, ip):
    agora = datetime.now()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO login_falhas (username, ip, momento) VALUES (?, ?, ?)",
                     (username.strip().lower(), ip, agora.strftime('%Y-%m-%d %H:%M:%S')))
        # histórico curto: nada além de um dia é necessário para o bloqueio
        conn.execute("DELETE FROM login_falhas WHERE momento < ?",
                     ((agora - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()


def tempo_bloqueio_login(username, ip, agora=None):
    """Quanto falta para liberar o login (timedelta), ou None se não está bloqueado.
    Bloqueia com LIMITE_FALHAS_USUARIO erros no usuário ou LIMITE_FALHAS_IP erros
    no IP dentro de JANELA_FALHAS; libera quando os erros saem da janela."""
    agora = agora or datetime.now()
    desde = (agora - JANELA_FALHAS).strftime('%Y-%m-%d %H:%M:%S')
    liberacoes = []
    with get_db_connection() as conn:
        for coluna, valor, limite in (('username', username.strip().lower(), LIMITE_FALHAS_USUARIO),
                                      ('ip', ip, LIMITE_FALHAS_IP)):
            if valor is None:
                continue
            linha = conn.execute(
                f"SELECT momento FROM login_falhas WHERE {coluna} = ? AND momento >= ? "
                "ORDER BY momento DESC LIMIT 1 OFFSET ?", (valor, desde, limite - 1)).fetchone()
            if linha:
                liberacoes.append(datetime.fromisoformat(linha['momento']) + JANELA_FALHAS)
    if not liberacoes:
        return None
    return max(liberacoes) - agora


def limpar_falhas_login(username):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM login_falhas WHERE username = ?", (username.strip().lower(),))
        conn.commit()


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
    """Retorna os usuários ativos com campos essenciais"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT id, username, email, role FROM users WHERE ativo = 1 ORDER BY username'
        )
        return [dict(row) for row in cursor.fetchall()]

_CAMPOS_USUARIO = {'username', 'email', 'password_hash', 'role', 'ativo'}

def update_user(user_id, **kwargs):
    if 'password' in kwargs:
        kwargs['password_hash'] = generate_password_hash(kwargs.pop('password'))
    set_clause = _clausula_set(kwargs, _CAMPOS_USUARIO, 'users')
    with get_db_connection() as conn:
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", [*kwargs.values(), user_id])
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
    """Exclui o usuário. Quem já registrou vendas é só desativado, para não
    perder o histórico. Retorna 'excluido' ou 'desativado'."""
    with get_db_connection() as conn:
        tem_vendas = conn.execute(
            "SELECT 1 FROM vendas WHERE usuario_id = ? LIMIT 1", (user_id,)).fetchone()
        if tem_vendas:
            conn.execute("UPDATE users SET ativo = 0 WHERE id = ?", (user_id,))
            conn.commit()
            return 'desativado'
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return 'excluido'

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
_CAMPOS_FORNECEDOR = {'nome', 'cnpj', 'contato', 'endereco'}

def update_fornecedor(fornecedor_id, **kwargs):
    set_clause = _clausula_set(kwargs, _CAMPOS_FORNECEDOR, 'fornecedores')
    with get_db_connection() as conn:
        try:
            conn.execute(f"UPDATE fornecedores SET {set_clause} WHERE id = ?",
                         [*kwargs.values(), fornecedor_id])
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

_CAMPOS_PRODUTO = {'nome', 'descricao', 'categoria', 'preco', 'quantidade', 'estoque_minimo',
                   'codigo_barras', 'foto', 'fornecedor_id', 'data_validade', 'tipo_venda', 'ativo'}

def update_produto(produto_id, **kwargs):
    desconhecidos = set(kwargs) - _CAMPOS_PRODUTO - {'foto_file'}
    if desconhecidos:
        raise ValueError(f"Campo(s) inválido(s) para produtos: {', '.join(sorted(desconhecidos))}")
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
    kwargs.pop('foto_file', None)
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

def get_all_produtos():
    """Produtos ativos com o nome do fornecedor."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT p.*, f.nome as fornecedor
            FROM produtos p
            LEFT JOIN fornecedores f ON p.fornecedor_id = f.id
            WHERE p.ativo = 1
            ORDER BY p.nome
        """)
        return [dict(row) for row in cursor.fetchall()]

def listar_produtos(search: str = '', categoria: str = '', page: int = 1, per_page: int = 10):
    # Query principal
    base_query = '''
        SELECT p.*, f.nome AS fornecedor
        FROM produtos AS p
        LEFT JOIN fornecedores AS f ON p.fornecedor_id = f.id
        WHERE p.ativo = 1
    '''
    count_query = 'SELECT COUNT(*) as total FROM produtos p WHERE p.ativo = 1'
    
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
    """Retorna todas as vendas ordenadas pela data decrescente"""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT * FROM vendas ORDER BY data DESC')
        return [dict(row) for row in cursor.fetchall()]

_CAMPOS_VENDA = {'cliente_cpf', 'cliente_nome', 'total', 'metodo_pagamento', 'status_pagamento',
                 'data_vencimento', 'observacao', 'data', 'data_pagamento'}

def update_venda(venda_id, **kwargs):
    set_clause = _clausula_set(kwargs, _CAMPOS_VENDA, 'vendas')
    with get_db_connection() as conn:
        conn.execute(f"UPDATE vendas SET {set_clause} WHERE id = ?", [*kwargs.values(), venda_id])
        conn.commit()

def delete_venda(venda_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))
        conn.commit()

def _validar_item_venda(item):
    """Retorna (produto_id, quantidade) de um item enviado pelo navegador."""
    try:
        if isinstance(item['id'], bool) or isinstance(item['quantidade'], bool):
            raise TypeError
        produto_id = int(item['id'])
        quantidade = float(item['quantidade'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Item da venda inválido')
    if not math.isfinite(quantidade) or quantidade <= 0:
        raise ValueError('A quantidade de cada item deve ser maior que zero')
    return produto_id, arredondar_quantidade(quantidade)


def processar_venda(venda_id, venda_data, usuario_id):
    """Registra a venda, os itens e a baixa de estoque numa única transação.

    Preço e total vêm sempre do cadastro do produto; qualquer preço enviado
    pelo navegador é ignorado. Levanta ValueError (sem gravar nada) se algum
    item for inválido ou faltar estoque.
    """
    itens = venda_data.get('itens')
    if not isinstance(itens, list) or not itens:
        raise ValueError('Adicione pelo menos um item à venda')
    metodo_pagamento = normalizar_forma_pagamento(venda_data.get('metodo_pagamento'))
    if metodo_pagamento is None:
        raise ValueError('Forma de pagamento inválida')

    data_venda = venda_data.get('data_venda') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status_pagamento = venda_data.get('status_pagamento', 'pago')
    # À vista é pago no ato; o fiado ganha data_pagamento quando é quitado
    data_pagamento = str(data_venda) if status_pagamento == 'pago' else None

    with get_db_connection() as conn:
        try:
            # IMMEDIATE: reserva a escrita já na leitura do estoque
            conn.execute('BEGIN IMMEDIATE')
            itens_validados = []
            for item in itens:
                produto_id, quantidade = _validar_item_venda(item)
                produto = conn.execute(
                    "SELECT nome, preco, tipo_venda FROM produtos WHERE id = ? AND ativo = 1",
                    (produto_id,)
                ).fetchone()
                if produto is None:
                    raise ValueError(f'Produto {produto_id} não encontrado')
                if produto['tipo_venda'] != 'quilo' and not quantidade.is_integer():
                    raise ValueError(
                        f'"{produto["nome"]}" é vendido por unidade: informe uma quantidade inteira')
                preco = arredondar_dinheiro(produto['preco'] or 0)
                if preco <= 0:
                    raise ValueError(
                        f'"{produto["nome"]}" está sem preço cadastrado. '
                        'Peça ao gerente para cadastrar o preço.')

                baixa = conn.execute(
                    "UPDATE produtos SET quantidade = ROUND(quantidade - ?, 3) "
                    "WHERE id = ? AND quantidade >= ?",
                    (quantidade, produto_id, quantidade)
                )
                if baixa.rowcount == 0:
                    disponivel = conn.execute(
                        "SELECT quantidade FROM produtos WHERE id = ?", (produto_id,)
                    ).fetchone()['quantidade']
                    raise ValueError(
                        f'Estoque insuficiente para "{produto["nome"]}" (disponível: {disponivel:g})')
                itens_validados.append((produto_id, quantidade, preco))

            # Cada item é arredondado em centavos (meio para cima) e o total é a soma deles
            total = arredondar_dinheiro(sum(
                _decimal(arredondar_dinheiro(_decimal(quantidade) * _decimal(preco)))
                for _, quantidade, preco in itens_validados))
            conn.execute(
                """
                INSERT INTO vendas
                (id, cliente_cpf, cliente_nome, total, metodo_pagamento,
                usuario_id, status_pagamento, data_vencimento, observacao, data, data_pagamento)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venda_id,
                    venda_data.get('cliente_cpf'),
                    venda_data.get('cliente_nome'),
                    total,
                    metodo_pagamento,
                    usuario_id,
                    status_pagamento,
                    venda_data.get('data_vencimento'),
                    venda_data.get('observacao'),
                    str(data_venda),
                    data_pagamento
                )
            )
            conn.executemany(
                "INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario) "
                "VALUES (?, ?, ?, ?)",
                [(venda_id, produto_id, quantidade, preco)
                 for produto_id, quantidade, preco in itens_validados]
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return True

def listar_produtos_simples():
    """Produtos ativos para a tela de venda."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, nome, preco, quantidade, tipo_venda, foto
            FROM produtos
            WHERE ativo = 1
            ORDER BY nome
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

_CAMPOS_VENDA_ITEM = {'produto_id', 'quantidade', 'preco_unitario'}

def update_venda_item(item_id, **kwargs):
    set_clause = _clausula_set(kwargs, _CAMPOS_VENDA_ITEM, 'venda_itens')
    with get_db_connection() as conn:
        conn.execute(f"UPDATE venda_itens SET {set_clause} WHERE id = ?", [*kwargs.values(), item_id])
        conn.commit()


def delete_venda_item(item_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM venda_itens WHERE id = ?", (item_id,))
        conn.commit()


# ---------------------------------------------------------------
# CRUD de Produtos
# ---------------------------------------------------------------


def _valor_formulario(form, campo, padrao):
    # O navegador envia os campos não preenchidos como texto vazio
    valor = form.get(campo)
    if valor is None or str(valor).strip() == '':
        return padrao
    return valor


def _ler_numeros_produto(form, tipo_venda, existente=None):
    """Valida preço, quantidade e estoque mínimo do formulário de produto.
    Aceita vírgula decimal; produtos por quilo aceitam até 3 casas (gramas)
    e produtos por unidade só aceitam números inteiros."""
    existente = existente or {}
    try:
        preco = arredondar_dinheiro(_valor_formulario(form, 'preco', existente.get('preco')))
    except ValueError:
        preco = 0
    if preco <= 0:
        raise ValueError('Preço inválido. Deve ser um número positivo.')

    por_quilo = tipo_venda == 'quilo'
    unidade = 'kg' if por_quilo else 'unidades'
    lidos = {}
    for campo, rotulo, padrao in (('quantidade', 'Quantidade', existente.get('quantidade', 0)),
                                  ('estoque_minimo', 'Estoque mínimo', 0)):
        try:
            valor = arredondar_quantidade(_valor_formulario(form, campo, padrao))
        except ValueError:
            raise ValueError(f'{rotulo} inválido(a). Informe um número em {unidade}.')
        if valor < 0:
            raise ValueError(f'{rotulo} não pode ser negativo(a).')
        if not por_quilo and not valor.is_integer():
            raise ValueError(f'{rotulo}: produtos vendidos por unidade aceitam só números inteiros.')
        lidos[campo] = valor if por_quilo else int(valor)
    return preco, lidos['quantidade'], lidos['estoque_minimo']


def inserir_produto(form: dict, foto):
    # Validações básicas
    nome = form.get('nome', '').strip()
    if not nome:
        raise ValueError('Campo obrigatório faltando: nome')
    preco, quantidade, estoque_minimo = _ler_numeros_produto(form, form.get('tipo_venda'))

    # Preparar dados
    produto_data = {
        'nome': nome,
        'descricao': form.get('descricao', '').strip(),
        'categoria': (form.get('categoria') or '').strip() or None,
        'preco': preco,
        'quantidade': quantidade,
        'estoque_minimo': estoque_minimo,
        'codigo_barras': form.get('codigo_barras') or None,
        'fornecedor_id': form.get('fornecedor_id') or None,
        'data_validade': form.get('data_validade') or None,
        'tipo_venda': form.get('tipo_venda'),
        'foto': _salvar_foto(foto)
    }

    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:  # Properly use the context manager
            cursor = conn.cursor()
            
            # Query de inserção (SQLite usa ? como placeholder, não %s)
            query = """
            INSERT INTO produtos (
                nome, descricao, categoria, preco, quantidade, estoque_minimo,
                codigo_barras, fornecedor_id, data_validade, tipo_venda, foto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            valores = (
                produto_data['nome'],
                produto_data['descricao'],
                produto_data['categoria'],
                produto_data['preco'],
                produto_data['quantidade'],
                produto_data['estoque_minimo'],
                produto_data['codigo_barras'],
                produto_data['fornecedor_id'],
                produto_data['data_validade'],
                produto_data['tipo_venda'],
                produto_data['foto']
            )
            
            cursor.execute(query, valores)
            conn.commit()
            
            produto_id = cursor.lastrowid
            return produto_id
            
    except Exception as e:
        logging.error(f"Erro ao inserir produto no banco de dados: {str(e)}")
        _remover_foto_se_orfa(produto_data['foto'])
        raise ValueError("Erro ao salvar produto no banco de dados")


def _salvar_foto(foto):
    """Grava o upload na pasta de fotos e retorna só o nome do arquivo
    (a URL é montada nos templates com o prefixo uploads/produtos/)."""
    if not foto or not foto.filename:
        return None
    filename = secure_filename(f"{datetime.now().timestamp()}_{foto.filename}")
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    foto.save(os.path.join(upload_folder, filename))
    gerar_miniatura(upload_folder, filename)
    return filename


def _remover_foto_se_orfa(foto):
    """Apaga o arquivo da foto se nenhum produto (nem desativado) o usa mais."""
    if not foto:
        return
    with get_db_connection() as conn:
        em_uso = conn.execute(
            "SELECT 1 FROM produtos WHERE foto = ? LIMIT 1", (foto,)).fetchone()
    if em_uso:
        return
    caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], os.path.basename(foto))
    remover_miniatura(current_app.config['UPLOAD_FOLDER'], foto)
    try:
        os.remove(caminho)
    except FileNotFoundError:
        pass
    except OSError as rm_err:
        logging.error(f"Falha ao remover arquivo {caminho}: {rm_err}")


def atualizar_produto(produto_id: int, form: dict, foto):
    # Buscar existente
    existing = get_produto_by_id(produto_id)
    if not existing:
        raise ValueError('Produto não encontrado')
    update_data = {}
    # Validar e montar dados
    update_data['nome'] = form.get('nome', '').strip() or existing['nome']
    update_data['descricao'] = (form.get('descricao') or '').strip() or None
    update_data['categoria'] = form.get('categoria', '').strip() or existing['categoria']
    tipo_venda = form.get('tipo_venda') or existing['tipo_venda']
    (update_data['preco'], update_data['quantidade'],
     update_data['estoque_minimo']) = _ler_numeros_produto(form, tipo_venda, dict(existing))
    # Opcionais: campo enviado vazio limpa o valor; campo ausente mantém o atual
    for campo in ('codigo_barras', 'fornecedor_id', 'data_validade'):
        if campo in form:
            update_data[campo] = (form.get(campo) or '').strip() or None
        else:
            update_data[campo] = existing[campo]
    update_data['tipo_venda'] = form.get('tipo_venda') or existing['tipo_venda']

    # Processar nova imagem
    new_filename = _salvar_foto(foto)
    update_data['foto'] = new_filename or existing['foto']

    # Montar UPDATE
    cols = list(update_data.keys())
    set_clause = ', '.join([f"{col} = ?" for col in cols])
    params = [update_data[col] for col in cols] + [produto_id]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE produtos SET {set_clause} WHERE id = ?', params)
            conn.commit()
    except Exception:
        # rollback imagem nova
        _remover_foto_se_orfa(new_filename)
        raise

    # remover imagem antiga
    if new_filename:
        _remover_foto_se_orfa(existing['foto'])


def excluir_produto(produto_id: int):
    """Exclui o produto. Produtos que já aparecem em vendas são só desativados,
    para preservar o histórico. Retorna 'excluido' ou 'desativado'."""
    with get_db_connection() as conn:
        row = conn.execute('SELECT foto FROM produtos WHERE id = ?', (produto_id,)).fetchone()
        if row is None:
            raise ValueError('Produto não encontrado')
        tem_vendas = conn.execute(
            'SELECT 1 FROM venda_itens WHERE produto_id = ? LIMIT 1', (produto_id,)).fetchone()
        if tem_vendas:
            conn.execute('UPDATE produtos SET ativo = 0 WHERE id = ?', (produto_id,))
            conn.commit()
            return 'desativado'
        conn.execute('DELETE FROM produtos WHERE id = ?', (produto_id,))
        conn.commit()
    _remover_foto_se_orfa(row['foto'])
    return 'excluido'

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
        cursor.execute(
            'SELECT DISTINCT categoria FROM produtos WHERE ativo = 1 ORDER BY categoria')
        return [row['categoria'] for row in cursor.fetchall()]

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
        # Datas com ou sem hora (e com microssegundos, gravadas por versões antigas)
        data, tem_hora = ler_data_hora(r['data'])
        vencimento, _ = ler_data_hora(r['data_vencimento'])
        dv = vencimento.date() if vencimento else None
        vencida = (r['status_pagamento']=='pendente' and dv and dv < hoje)
        vendas_map[vid].update({
            'id': vid, 'cliente_nome': r['cliente_nome'], 'data': data, 'tem_hora': tem_hora,
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
    """Quita uma venda a prazo pendente, registrando a data do pagamento.
    Retorna False se a venda não existe, não é a prazo ou já estava paga."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE vendas
            SET status_pagamento = 'pago', data_pagamento = ?
            WHERE id = ? AND metodo_pagamento = 'pagamento_prazo'
              AND status_pagamento = 'pendente'
            """,
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), venda_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def adicionar_observacao_venda(venda_id, observacao):
    """Adiciona ou atualiza observação de uma venda."""
    return update_venda(venda_id, observacao=observacao)

def _filtros_logs(search=None, level=None, user_id=None, action=None,
                  start_date=None, end_date=None):
    """Monta a cláusula WHERE usada tanto na listagem quanto nas contagens."""
    condicoes, params = [], []
    if search:
        condicoes.append("(action LIKE ? OR details LIKE ?)")
        params.extend([f'%{search}%', f'%{search}%'])
    if level:
        condicoes.append("level = ?")
        params.append(level)
    if user_id:
        condicoes.append("user_id = ?")
        params.append(user_id)
    if action:
        condicoes.append("action = ?")
        params.append(action)
    if start_date:
        condicoes.append("DATE(timestamp) >= ?")
        params.append(start_date)
    if end_date:
        condicoes.append("DATE(timestamp) <= ?")
        params.append(end_date)
    where = f" WHERE {' AND '.join(condicoes)}" if condicoes else ""
    return where, params


def listar_logs(page=1, per_page=20, search=None, level=None, user_id=None, action=None, start_date=None, end_date=None):
    where, params = _filtros_logs(search, level, user_id, action, start_date, end_date)
    with get_db_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM logs{where}", params).fetchone()[0]
        cursor = conn.execute(
            f"SELECT * FROM logs{where} ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?",
            params + [per_page, (page - 1) * per_page]
        )
        logs = [dict(row) for row in cursor.fetchall()]
    return logs, total


def contar_logs_por_nivel(search=None, user_id=None, action=None, start_date=None, end_date=None):
    """Quantidade de logs por nível ({'INFO': n, ...}) com os filtros informados."""
    where, params = _filtros_logs(search, None, user_id, action, start_date, end_date)
    with get_db_connection() as conn:
        cursor = conn.execute(
            f"SELECT level, COUNT(*) AS total FROM logs{where} GROUP BY level", params)
        return {row['level']: row['total'] for row in cursor.fetchall()}


def listar_acoes_logs():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT DISTINCT action FROM logs ORDER BY action")
        return [row['action'] for row in cursor.fetchall()]