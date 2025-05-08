from werkzeug.security import generate_password_hash
from banco_dados import get_db_connection, init_db
from datetime import datetime, timedelta

def popular_dados_teste():
    init_db()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Adicione antes de criar os dados:
        cursor.execute("DELETE FROM venda_itens")
        cursor.execute("DELETE FROM vendas")
        cursor.execute("DELETE FROM produtos")
        cursor.execute("DELETE FROM fornecedores")
        cursor.execute("DELETE FROM users")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='users'")  # Reset autoincrement
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='fornecedores'")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='produtos'")
        conn.commit()

        # Resetar tabelas na ordem correta de dependência
        cursor.execute("DELETE FROM venda_itens")
        cursor.execute("DELETE FROM vendas")
        cursor.execute("DELETE FROM produtos")
        cursor.execute("DELETE FROM fornecedores")
        cursor.execute("DELETE FROM users")
        conn.commit()  # Commit crítico aqui

        # 1. Criar usuário admin
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (
            "admin",
            "admin@acougue.com",
            generate_password_hash("admin123"),
            "gerente"
        ))
        conn.commit()  # Commit para gerar o ID
        usuario_id = cursor.lastrowid
        print(f"🆔 Usuário criado com ID: {usuario_id}")

        # 2. Criar fornecedor
        cursor.execute('''
            INSERT INTO fornecedores (nome, cnpj, contato, endereco)
            VALUES (?, ?, ?, ?)
        ''', (
            "Açougue Central",
            "12.345.678/0001-99",
            "(11) 98765-4321",
            "Av. das Carnes, 456 - Centro"
        ))
        conn.commit()  # Commit para gerar o ID
        fornecedor_id = cursor.lastrowid
        print(f"🏭 Fornecedor criado com ID: {fornecedor_id}")

        # 3. Inserir produtos
        produtos = [
            ('Picanha Bovino', 'Carnes Nobres', 99.90, 50, 'quilo', 10, fornecedor_id),
            ('Coxão Mole', 'Carnes', 47.50, 30, 'quilo', 5, fornecedor_id),
            ('Linguiça Toscana', 'Embutidos', 28.90, 100, 'unidade', 20, fornecedor_id)
        ]
        
        for produto in produtos:
            cursor.execute('''
                INSERT INTO produtos (
                    nome, categoria, preco, quantidade, tipo_venda, 
                    estoque_minimo, fornecedor_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', produto)
        conn.commit()
        print(f"📦 {len(produtos)} produtos inseridos")
        
        # Após inserir produtos, verifique os IDs:
        cursor.execute("SELECT id FROM produtos")
        produto_ids = [row['id'] for row in cursor.fetchall()]
        print(f"🔍 IDs de produtos disponíveis: {produto_ids}")  # Deve ser [1, 2, 3]

        # 4. Criar vendas
        
        vendas = [
            ('V20231015120000', '123.456.789-00', 297.80, 'PIX', usuario_id, 'pago', None),
            ('V20231015120001', '987.654.321-00', 150.00, 'pagamento_prazo', usuario_id, 'pendente', '2023-11-15')
        ]
        
        for venda in vendas:
            cursor.execute('''
                INSERT INTO vendas 
                (id, cliente_cpf, total, metodo_pagamento, usuario_id, status_pagamento, data_vencimento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', venda)
        conn.commit()
        print(f"💰 {len(vendas)} vendas registradas")

        # 5. Adicionar itens às vendas
        # Substitua a seção de itens de venda por:
        itens_venda = [
            # Venda 1: Picanha (ID 1) e Linguiça (ID 3)
            ('V20231015120000', 1, 2.0, 99.90),  
            ('V20231015120000', 3, 5, 28.90),
            
            # Venda 2: Coxão Mole (ID 2)
            ('V20231015120001', 2, 3.0, 47.50)
        ]
        
        for item in itens_venda:
            cursor.execute('''
                INSERT INTO venda_itens 
                (venda_id, produto_id, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?)
            ''', item)
        conn.commit()
        print(f"🛒 {len(itens_venda)} itens de venda adicionados")

    print("✅ Todos os dados de teste foram inseridos com sucesso!")

if __name__ == '__main__':
    popular_dados_teste()