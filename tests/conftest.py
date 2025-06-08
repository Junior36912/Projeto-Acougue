import pytest
from app import app

@pytest.fixture
def app():
    app.config.update({
        'TESTING': True,
        'DATABASE': 'file::memory:?cache=shared',
        'WTF_CSRF_ENABLED': False
    })
    yield app

@pytest.fixture
def client(app):
    return app.test_client()