import os
import pytest
from unittest.mock import patch
from app import validar_cnpj, backup_db, app
from banco_dados import processar_venda

# -------------------------
# Testes para validar_cnpj
# -------------------------
def test_cnpj_valido():
    assert validar_cnpj("12.345.678/0001-95") is True

def test_cnpj_invalido_com_digitos_iguais():
    assert validar_cnpj("11.111.111/1111-11") is False

def test_cnpj_com_tamanho_invalido():
    assert validar_cnpj("12345678") is False

# ----------------------
# Testes para backup_db
# ----------------------
def test_backup_criado():
    backup_db()
    backup_dir = os.path.join(os.path.dirname(__file__), '..', 'backups')
    backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
    assert len(backups) > 0, "Nenhum arquivo de backup .db foi encontrado."

# -----------------------------
# Testes para processar_venda
# -----------------------------
@patch('banco_dados.get_db_connection')
def test_processar_venda_sucesso(mock_conn):
    venda_id = "V20250512123000"
    venda_data = {
        'cliente_cpf': '12345678900',
        'cliente_nome': 'João',
        'metodo_pagamento': 'pix',
        'itens': [{'produto_id': 1, 'quantidade': 2, 'preco_unitario': 10.0}],
        'status_pagamento': 'pago',
        'observacao': ''
    }
    user_id = 1

    # Simulação do retorno do banco
    mock_conn.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = []

    try:
        processar_venda(venda_id, venda_data, user_id)
    except Exception:
        pytest.fail("processar_venda levantou exceção inesperada.")
