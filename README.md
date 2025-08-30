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

```

⚙️ Instalação e Configuração
✅ Pré-requisitos

Python 3.8+

pip (gerenciador de pacotes do Python)

📌 Passos

Clone o repositório

```
git clone https://github.com/seu-usuario/Projeto-Acougue.git
cd Projeto-Acougue
```

Crie um ambiente virtual (recomendado)

```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

Instale as dependências

```
pip install -r requirements.txt
```

Execute a aplicação

```
python app.py
```

Acesse em: http://localhost:5000

## 💻 Uso
### 🔐 Acesso Inicial

URL: http://localhost:5000

Usuário: admin

Senha: admin123 (após popular o banco)

## 📌 Funcionalidades Principais

- Dashboard: métricas rápidas e alertas de estoque

- Produtos: cadastro, edição e exclusão + controle de estoque

- Fornecedores: gerenciamento completo

- Vendas: vendas à vista ou fiado + contas a receber

- Relatórios: PDF e visualização no sistema

- Admin: gerenciamento de usuários e permissões

## 💾 Backup

- Backups automáticos a cada 24h
 
- Disponíveis em /backup (apenas para gerentes)

## 🧪 Testes

Rodar todos os testes automatizados:
```
pytest tests/ -v
```
⚙️ Personalização
Configurações em app.py

```
SECRET_KEY → chave secreta da aplicação

UPLOAD_FOLDER → pasta de upload de imagens

MAX_FILE_SIZE_MB → tamanho máximo de arquivos

ALLOWED_EXTENSIONS → extensões permitidas
```

Adicionar novos relatórios

Editar a função relatorios_unificados em app.py

### 🔒 Segurança

Senhas com hash seguro (Werkzeug)

Proteção CSRF (Flask-WTF)

Controle de acesso por roles (gerente/funcionário)

Logs detalhados de atividades

## 📜 Licença

Este projeto é de uso interno. Consulte os termos de licença para mais informações.

## 📧 Suporte

Em caso de problemas, entre em contato com a equipe de desenvolvimento.
