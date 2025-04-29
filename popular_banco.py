from banco_dados import get_db_connection, init_db  # Adicione init_db aqui

def popular_dados_teste():
    # Reinicializa todas as tabelas
    init_db()  # ← Linha crítica adicionada
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Adicionar fornecedor padrão (o resto mantém igual)
        cursor.execute('''
            INSERT INTO fornecedores (nome, cnpj, contato, endereco)
            VALUES (?, ?, ?, ?)
        ''', (
            "Açougue Central",
            "12.345.678/0001-99",
            "(11) 98765-4321",
            "Av. das Carnes, 456 - Centro"
        ))
        fornecedor_id = cursor.lastrowid


        # Produtos para teste
        produtos = [
            ('Picanha Bovino', 'Carnes Nobres', 99.90, 50, 'quilo', 10, fornecedor_id),
            ('Coxão Mole', 'Carnes', 47.50, 30, 'quilo', 5, fornecedor_id),
            ('Linguiça Toscana', 'Embutidos', 28.90, 100, 'unidade', 20, fornecedor_id),
            ('Peito de Frango', 'Aves', 19.90, 80, 'quilo', 15, fornecedor_id),
            ('Hambúrguer Artesanal', 'Processados', 14.90, 200, 'unidade', 50, fornecedor_id),
            ('Costela Bovina', 'Carnes', 69.90, 40, 'quilo', 10, fornecedor_id)
        ]

        # Inserir produtos
        for produto in produtos:
            cursor.execute('''
                INSERT INTO produtos (
                    nome,
                    categoria,
                    preco,
                    quantidade,
                    tipo_venda,
                    estoque_minimo,
                    fornecedor_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', produto)

        conn.commit()
        print("✅ 6 produtos e 1 fornecedor inseridos com sucesso!")

if __name__ == '__main__':
    popular_dados_teste()