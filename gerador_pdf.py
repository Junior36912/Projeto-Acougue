# gerador_pdf.py
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime
import sqlite3
from io import BytesIO
from flask import make_response
from contextlib import contextmanager
import os

def get_custom_styles():
    styles = getSampleStyleSheet()
    
    # Verifica se o estilo já existe antes de adicionar
    if 'Title' not in styles:
        styles.add(ParagraphStyle(name='Title', fontSize=18, alignment=1, spaceAfter=12))
    if 'Subtitle' not in styles:
        styles.add(ParagraphStyle(name='Subtitle', fontSize=14, alignment=1, spaceAfter=6))
    if 'Header' not in styles:
        styles.add(ParagraphStyle(name='Header', fontSize=12, alignment=1, spaceAfter=6))
    if 'Body' not in styles:
        styles.add(ParagraphStyle(name='Body', fontSize=10, alignment=0, spaceAfter=3))
    
    return styles

@contextmanager
def get_db_connection():
    conn = sqlite3.connect('acougue.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def format_currency(value):
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_pdf_completo():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = get_custom_styles()
    
    
    # Cabeçalho
    logo_path = os.path.join('static', 'images', 'logo.png') if os.path.exists(os.path.join('static', 'images', 'logo.png')) else None
    
    if logo_path:
        logo = Image(logo_path, width=1.5*inch, height=1*inch)
        elements.append(logo)
    
    elements.append(Paragraph("Relatório Completo do Açougue", styles['Title']))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Subtitle']))
    elements.append(Spacer(1, 0.5*inch))
    
    # 1. Relatórios de Vendas
    elements.append(Paragraph("1. Relatórios de Vendas", styles['Header']))
    
    # Vendas por Período
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DATE(data) as data, COUNT(*) as total_vendas, SUM(total) as valor_total, AVG(total) as ticket_medio
            FROM vendas
            WHERE DATE(data) BETWEEN DATE('now', '-30 days') AND DATE('now')
            GROUP BY DATE(data)
            ORDER BY data
        ''')
        vendas_periodo = cursor.fetchall()
    
    data = [['Data', 'Total Vendas', 'Valor Total', 'Ticket Médio']]
    for row in vendas_periodo:
        data.append([
            row['data'],
            str(row['total_vendas']),
            format_currency(row['valor_total']),
            format_currency(row['ticket_medio'])
        ])
    
    elements.append(Paragraph("Vendas por Período (Últimos 30 dias)", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # Vendas por Categoria
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.categoria, SUM(vi.quantidade) as quantidade_vendida, 
                   SUM(vi.quantidade * vi.preco_unitario) as valor_total
            FROM venda_itens vi
            JOIN produtos p ON vi.produto_id = p.id
            GROUP BY p.categoria
            ORDER BY valor_total DESC
        ''')
        vendas_categoria = cursor.fetchall()
    
    data = [['Categoria', 'Quantidade Vendida', 'Valor Total']]
    for row in vendas_categoria:
        data.append([
            row['categoria'],
            str(row['quantidade_vendida']),
            format_currency(row['valor_total'])
        ])
    
    elements.append(Paragraph("Vendas por Categoria", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 2. Relatórios Financeiros
    elements.append(Paragraph("2. Relatórios Financeiros", styles['Header']))
    
    # Contas a Receber
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cliente_nome, total, data_vencimento,
                   CASE WHEN data_vencimento < DATE('now') THEN 'Vencido' ELSE 'A Vencer' END as status
            FROM vendas
            WHERE status_pagamento = 'pendente'
            ORDER BY data_vencimento
        ''')
        contas_receber = cursor.fetchall()
    
    data = [['Cliente', 'Valor', 'Vencimento', 'Status']]
    for row in contas_receber:
        data.append([
            row['cliente_nome'],
            format_currency(row['total']),
            row['data_vencimento'],
            row['status']
        ])
    
    elements.append(Paragraph("Contas a Receber", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('TEXTCOLOR', (3, 1), (3, -1), lambda r, c, v: colors.red if v == 'Vencido' else colors.green)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 3. Relatórios de Estoque
    elements.append(Paragraph("3. Relatórios de Estoque", styles['Header']))
    
    # Nível de Estoque
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT nome, quantidade, estoque_minimo, (quantidade - estoque_minimo) as diferenca
            FROM produtos
            WHERE quantidade < estoque_minimo
            ORDER BY diferenca ASC
        ''')
        estoque_nivel = cursor.fetchall()
    
    data = [['Produto', 'Quantidade', 'Estoque Mínimo', 'Diferença']]
    for row in estoque_nivel:
        data.append([
            row['nome'],
            str(row['quantidade']),
            str(row['estoque_minimo']),
            str(row['diferenca'])
        ])
    
    elements.append(Paragraph("Produtos Abaixo do Estoque Mínimo", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('TEXTCOLOR', (3, 1), (3, -1), colors.red)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 4. Relatórios de Clientes
    elements.append(Paragraph("4. Relatórios de Clientes", styles['Header']))
    
    # Clientes Fiéis
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cliente_nome, COUNT(*) as total_compras, SUM(total) as valor_total_gasto
            FROM vendas
            WHERE cliente_nome IS NOT NULL
            GROUP BY cliente_nome
            ORDER BY total_compras DESC
            LIMIT 10
        ''')
        clientes_fieis = cursor.fetchall()
    
    data = [['Cliente', 'Total Compras', 'Valor Total Gasto']]
    for row in clientes_fieis:
        data.append([
            row['cliente_nome'],
            str(row['total_compras']),
            format_currency(row['valor_total_gasto'])
        ])
    
    elements.append(Paragraph("Top 10 Clientes Fiéis", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 5. Relatórios de Fornecedores
    elements.append(Paragraph("5. Relatórios de Fornecedores", styles['Header']))
    
    # Produtos por Fornecedor
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT f.nome as fornecedor, COUNT(p.id) as total_produtos, SUM(p.quantidade) as total_estoque
            FROM fornecedores f
            LEFT JOIN produtos p ON f.id = p.fornecedor_id
            GROUP BY f.id
            ORDER BY total_produtos DESC
        ''')
        fornecedores_produtos = cursor.fetchall()
    
    data = [['Fornecedor', 'Total Produtos', 'Total em Estoque']]
    for row in fornecedores_produtos:
        data.append([
            row['fornecedor'],
            str(row['total_produtos']),
            str(row['total_estoque'])
        ])
    
    elements.append(Paragraph("Produtos por Fornecedor", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 6. Relatórios Operacionais
    elements.append(Paragraph("6. Relatórios Operacionais", styles['Header']))
    
    # Movimentação de Caixa
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DATE(data) as data,
                   SUM(CASE WHEN metodo_pagamento = 'fiado' THEN 0 ELSE total END) as entradas,
                   SUM(CASE WHEN metodo_pagamento = 'fiado' THEN total ELSE 0 END) as saidas
            FROM vendas
            WHERE DATE(data) BETWEEN DATE('now', '-7 days') AND DATE('now')
            GROUP BY DATE(data)
            ORDER BY data DESC
        ''')
        movimentacao = cursor.fetchall()
    
    data = [['Data', 'Entradas', 'Saídas', 'Saldo']]
    for row in movimentacao:
        saldo = row['entradas'] - row['saidas']
        data.append([
            row['data'],
            format_currency(row['entradas']),
            format_currency(row['saidas']),
            format_currency(saldo)
        ])
    
    elements.append(Paragraph("Movimentação de Caixa (Últimos 7 dias)", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('TEXTCOLOR', (3, 1), (3, -1), lambda r, c, v: colors.green if float(v.replace('R$', '').replace(',', '')) > 0 else colors.red)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # 7. Relatórios Estratégicos
    elements.append(Paragraph("7. Relatórios Estratégicos", styles['Header']))
    
    # Comparativo Mensal
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT strftime('%Y-%m', data) as periodo,
                   COUNT(*) as total_vendas,
                   SUM(total) as valor_total
            FROM vendas
            GROUP BY periodo
            ORDER BY periodo DESC
            LIMIT 12
        ''')
        comparativo = cursor.fetchall()
    
    data = [['Período', 'Total Vendas', 'Valor Total']]
    for row in comparativo:
        data.append([
            row['periodo'],
            str(row['total_vendas']),
            format_currency(row['valor_total'])
        ])
    
    elements.append(Paragraph("Comparativo Mensal", styles['Body']))
    elements.append(Spacer(1, 0.1*inch))
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    
    # Rodapé
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("Relatório gerado automaticamente pelo Sistema de Gestão do Açougue", styles['Body']))
    
    # Construir o PDF
    doc.build(elements)
    
    buffer.seek(0)
    return buffer

def gerar_relatorio_pdf():
    pdf = gerar_pdf_completo()
    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=relatorio_completo.pdf'
    return response