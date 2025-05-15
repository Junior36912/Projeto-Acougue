from werkzeug.security import generate_password_hash
from banco_dados import get_db_connection, init_db
from datetime import datetime, timedelta

def popular_dados_teste():
    init_db()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Limpar tabelas na ordem correta (respeitando relações de chave estrangeira)
        cursor.execute("DELETE FROM venda_itens")
        cursor.execute("DELETE FROM vendas")
        cursor.execute("DELETE FROM produtos")
        cursor.execute("DELETE FROM fornecedores")
        cursor.execute("DELETE FROM users")

        # Resetar sequências de autoincremento (específico do SQLite)
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='users'")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='fornecedores'")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='produtos'")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='vendas'")
        cursor.execute("UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='venda_itens'")  # Adicionado

        conn.commit()

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
        conn.commit()
        usuario_id = cursor.lastrowid
        print(f"🆔 Usuário criado com ID: {usuario_id}")

        # 2. Inserir fornecedor
        cursor.execute('''
            INSERT INTO fornecedores (nome, cnpj, contato, endereco)
            VALUES (?, ?, ?, ?)
        ''', (
            "Açougue JT",
            "12.345.678/0001-99",
            "(11) 98765-4321",
            "Av. das Carnes, 456 - Centro"
        ))
        conn.commit()
        fornecedor_id = cursor.lastrowid
        print(f"🏭 Fornecedor criado com ID: {fornecedor_id}")

        # 3. Inserir produtos
        produtos = [
            # Carnes BOI
            ('Coração', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'coracao.png'),
            ('Fígado', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'figado.png'),
            ('Bisteca', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'bisteca-bolvina.png'),
            ('Paleta', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'paleta.png'),
            ('Costela', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'costela-bolvina.png'),
            ('Polpa ou Coxa Mole', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'coxao-mole.png'),
            ('Patim ou Caturrino', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'patim.png'),
            ('Alcatra', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'alcatra.png'),
            ('Mão de Vaca', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'mao-de-vaca.png'),
            ('Filé', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'file-mignon.png'),
            ('Ossada', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, None),  # Imagem faltante: ossada.png
            ('Panelada (Prato)', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'panelada.jpeg'),
            ('Picanha', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'picanha.webp'),
            ('Demais Carnes Magicas', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, None),  # Imagem faltante: demais-carnes-magicas.png
            ('Carne Moída Pronta', 'BOI', 0.0, 0, 'quilo', 0, fornecedor_id, 'carne-moida.png'),

            # Carnes PORCO
            ('Com Toucinho', 'PORCO', 0.0, 0, 'quilo', 0, fornecedor_id, 'com-toucinho.png'),
            ('Sem Toucinho', 'PORCO', 0.0, 0, 'quilo', 0, fornecedor_id, 'sem-toucinho.png'),

            # Carneiro
            ('Carneiro', 'CARNEIRO', 0.0, 0, 'quilo', 0, fornecedor_id, 'carneiro.png'),

            # Frangos
            ('Abatido', 'FRANGOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'frango-fresco.png'),
            ('Peito', 'FRANGOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'peito-frango.webp'),
            ('Coxa', 'FRANGOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'coxa-frango.png'),
            ('Sobrecoxa', 'FRANGOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'sobrecoxa.png'),

            # Congelados
            ('Linguiça Toscana Dália', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'linguica-toscana-dalia.png'),
            ('Aurora', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'linguica-toscana-aurora.webp'),
            ('Linguiça Calabresa Dália', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'linguica-calabresa-dalia.png'),
            ('Seara ou Perdigão', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'linguica-perdigao.png'),
            ('Bisteca Suína', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'bisteca-suina.png'),
            ('Pernil Suíno', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'pernil-suino.png'),
            ('Lapa de Filé', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'capa-file.png'),
            ('Bacon', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'bacon.png'),
            ('Presunto', 'CONGELADOS', 0.0, 0, 'quilo', 0, fornecedor_id, 'presunto.png'),

            # Bebidas (Novos Produtos)
            ('Budweiser 350ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'budweiser-350ml.png'),
            ('Budweiser 550ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'budweiser-550ml.webp'),
            ('Corona 330ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'corona-330ml.png'),
            ('Guaraná 350ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'guaran_350.png'),
            ('Guaraná 1L', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'guarana-1l.png'),
            ('Guaraná 2L', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'guarana-2l.webp'),
            ('H2O', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'h2o.png'),
            ('Heineken Original', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'heineken-original-bottle.png'),
            ('Skol 350ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'skol-350ml.png'),
            ('Stella Artois 600ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'stella-600ml.png'),
            ('Sukita 2L', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'sukita-2l.png'),
            ('Pepsi 1L', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'pepsi-1l.png'),
            ('Pepsi 2L', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'pepsi-2l.png'),
            ('Pepsi 350ml', 'BEBIDAS', 0.0, 0, 'unidade', 0, fornecedor_id, 'pepsi-350ml.png'),
        ]

        for produto in produtos:
            nome, categoria, preco, quantidade, tipo_venda, estoque_minimo, fornecedor_id, foto = produto
            if foto:
                foto = f'uploads/produtos/{foto}'
            else:
                foto = None  # Garante NULL explícito para imagens faltantes
            
            cursor.execute('''
                INSERT INTO produtos (
                    nome, categoria, preco, quantidade, tipo_venda,
                    estoque_minimo, fornecedor_id, foto
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                nome, categoria, preco, quantidade, tipo_venda,
                estoque_minimo, fornecedor_id, foto
            ))

        conn.commit()  # Commit crucial para salvar todos os produtos

        # 4. Criar vendas de exemplo (corrigido)
        import uuid  # Adicione no topo do arquivo

        # Gerar ID único para a venda
        venda_id = str(uuid.uuid4())
        data_venda = datetime.now() - timedelta(days=1)

        # Inserir venda principal
        cursor.execute('''
            INSERT INTO vendas (id, data, total, usuario_id, metodo_pagamento)
            VALUES (?, ?, ?, ?, ?)
        ''', (venda_id, data_venda, 199.90, usuario_id, 'dinheiro'))
        conn.commit()

        # Inserir itens da venda (exemplo)
        produtos_venda = [
            (venda_id, 1, 2, 99.95),  # Produto ID 1, 2 unidades
            (venda_id, 3, 1, 50.00)    # Produto ID 3, 1 unidade
        ]

        for item in produtos_venda:
            cursor.execute('''
                INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?)
            ''', item)
        conn.commit()

    print("✅ Todos os dados de teste foram inseridos com sucesso!")

if __name__ == '__main__':
    popular_dados_teste()