# 🥩 Sistema de Gestão para Açougue

Sistema completo de gestão para açougue, desenvolvido em **Flask (Python)**, com funcionalidades de controle de **estoque, vendas, fornecedores, usuários, relatórios e muito mais**.

---

## 🚀 Funcionalidades

- 🔑 **Autenticação e Autorização**: login com dois níveis de acesso (gerente e funcionário)  
- 📦 **Gestão de Produtos**: CRUD de produtos com controle de estoque, categorias, fornecedores e imagens  
- 🤝 **Gestão de Fornecedores**: cadastro e gerenciamento de fornecedores  
- 💰 **Vendas**: registro de vendas à vista e a prazo (fiado)  
- 📊 **Relatórios**: vendas, estoque, financeiro, clientes, etc. (em PDF e no sistema)  
- 💾 **Backup Automático**: banco de dados e imagens salvos automaticamente  
- 📝 **Logs**: registro detalhado de atividades do sistema  
- 📉 **Dashboard**: painel com métricas e alertas importantes  

---

## 🛠️ Tecnologias Utilizadas

- **Backend**: Flask (Python)  
- **Banco de Dados**: SQLite  
- **Frontend**: HTML, CSS, JavaScript (templates Jinja2)  
- **PDF**: ReportLab  
- **Agendamento**: APScheduler (backup, verificação de validades)  

---

## 📂 Estrutura do Projeto

```text
Projeto-Acougue/
├── app.py                 # Aplicação principal Flask
├── app_logging.py         # Sistema de logging personalizado
├── banco_dados.py         # Funções de acesso ao banco de dados
├── decorators.py          # Decoradores para autenticação e autorização
├── gerador_pdf.py         # Geração de relatórios em PDF
├── tests/                 # Testes automatizados
│   ├── conftest.py
│   ├── popular_banco.py
│   ├── testes.py
│   └── test_integration.py
├── static/                # Arquivos estáticos (CSS, JS, imagens)
├── templates/             # Templates HTML
└── backups/               # Backups gerados automaticamente
