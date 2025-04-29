import logging
from datetime import datetime
from flask import request

def registrar_log(user_id, action, level='INFO', details=None, request=None):
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'action': action,
        'level': level,
        'details': details or {},
        'ip_address': request.remote_addr if request else None,
        'user_agent': request.headers.get('User-Agent') if request else None
    }
    
    logger = logging.getLogger('app_logger')
    msg = f"[{log_data['timestamp']}] User {user_id} - {action}"
    
    if level == 'INFO':
        logger.info(msg, extra=log_data)
    elif level == 'WARNING':
        logger.warning(msg, extra=log_data)
    elif level == 'ERROR':
        logger.error(msg, extra=log_data)