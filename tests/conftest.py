import os
import sys
import tempfile

import pytest

# app.py chama init_db() e lê a SECRET_KEY na importação: o ambiente precisa
# apontar para arquivos temporários antes do import, senão os testes mexeriam
# no acougue.db real e em instance/secret_key.
_PASTA_IMPORT = tempfile.mkdtemp(prefix='acougue-testes-')
os.environ['DB_PATH'] = os.path.join(_PASTA_IMPORT, 'import.db')
os.environ['SECRET_KEY'] = 'chave-usada-somente-nos-testes'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app  # noqa: E402
from banco_dados import init_db  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Banco novo e vazio para cada teste."""
    caminho = tmp_path / 'teste.db'
    monkeypatch.setenv('DB_PATH', str(caminho))
    init_db()
    return caminho


@pytest.fixture
def app(db_path, tmp_path, monkeypatch):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    monkeypatch.setitem(flask_app.config, 'TESTING', True)
    monkeypatch.setitem(flask_app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setitem(flask_app.config, 'UPLOAD_FOLDER', str(uploads))
    monkeypatch.setitem(flask_app.config, 'BACKUP_FOLDER', str(tmp_path / 'backups'))
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
