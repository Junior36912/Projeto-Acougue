from functools import wraps
from flask import session, redirect, url_for, abort

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            # Logado, mas sem o cargo: página de acesso negado (não desloga)
            if session.get('role') != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
