import logging
from datetime import datetime
import json
from banco_dados import get_db_connection

# Atualize a função registrar_log
def registrar_log(user_id, action, level='INFO', details=None, request=None):
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent') if request else None
    
    # Salvar no banco de dados
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO logs (timestamp, user_id, action, level, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            # Hora local (o CURRENT_TIMESTAMP do SQLite é UTC).
            # ensure_ascii=False: grava "Coração" legível, para a busca nos logs encontrar
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id, action, level,
             json.dumps(details, ensure_ascii=False) if details else None,
             ip_address, user_agent)
        )
        conn.commit()
    
    # Manter o logging tradicional também
    logger = logging.getLogger('app_logger')
    msg = f"[{datetime.now().isoformat()}] User {user_id} - {action}"
    
    if level == 'INFO':
        logger.info(msg, extra={'details': details})
    elif level == 'WARNING':
        logger.warning(msg, extra={'details': details})
    elif level == 'ERROR':
        logger.error(msg, extra={'details': details})