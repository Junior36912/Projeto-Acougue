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

Python 3.11+ (testado no 3.12)

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

O modo debug fica desligado por padrão. Para desenvolver com recarga automática e debugger, use `FLASK_DEBUG=1 python app.py` (nunca em produção: o debugger permite executar código pelo navegador).

## 💻 Uso
### 🔐 Acesso Inicial

URL: http://localhost:5000

Usuário: admin

Senha: admin123 (após rodar `python popular_banco.py`)

No primeiro acesso com a senha padrão, o sistema exige que você cadastre uma senha nova. Cada usuário pode trocar a própria senha pelo link **Senha** no menu.

## 📌 Funcionalidades Principais

- Dashboard: métricas rápidas e alertas de estoque

- Produtos: cadastro, edição e exclusão + controle de estoque

- Fornecedores: gerenciamento completo

- Vendas: vendas à vista ou fiado + contas a receber

- Relatórios: PDF e visualização no sistema

- Admin: gerenciamento de usuários e permissões

## 💾 Backup

- Com o sistema rodando (`python app.py`), o backup é feito quando o último tem mais de 24h, e não a cada reinício.
- Ficam em `backups/`: `acougue_banco_*.zip` (banco comprimido) e `acougue_fotos_*.zip` (fotos, criado só quando alguma foto muda).
- Retenção automática: o último backup de cada um dos 7 dias mais recentes, o de cada uma das 4 semanas mais recentes e os 2 últimos de fotos. Os arquivos `acougue_system_backup_*.zip` de versões antigas não são apagados automaticamente.
- O gerente baixa um backup completo (banco + fotos) em `/backup` ("Backup Completo" no dashboard). Ele é gerado na hora e não fica guardado.
- Antes de migrar o esquema do banco, o sistema salva uma cópia em `backups/acougue_pre_migracao_v<versão>_<data>.db`.

## 🧪 Testes

Instalar as dependências de teste e rodar a suíte:
```
pip install -r requirements-dev.txt
pytest tests/ -v
```
Os testes usam bancos e pastas temporários: não alteram o `acougue.db` nem a pasta `backups/`.
⚙️ Personalização
Configurações em app.py

```
SECRET_KEY → chave secreta da aplicação (variável de ambiente; se não existir,
             uma chave aleatória é gerada e guardada em instance/secret_key)
DB_PATH → caminho do banco SQLite (padrão: acougue.db)
FLASK_DEBUG → 1 liga o modo debug (padrão: desligado)
FLASK_RUN_HOST / FLASK_RUN_PORT → endereço e porta (padrão: 127.0.0.1:5000)

UPLOAD_FOLDER → pasta de upload de imagens

MAX_FILE_SIZE_MB → tamanho máximo de arquivos

ALLOWED_EXTENSIONS → extensões permitidas
```

Adicionar novos relatórios

Editar a função relatorios_unificados em app.py

### 🔒 Segurança

- Senhas com hash seguro (Werkzeug), troca obrigatória da senha padrão
- Banco de dados fora do git (`*.db` no `.gitignore`)

- Proteção CSRF (Flask-WTF)

- Controle de acesso por roles (gerente/funcionário)

- Logs detalhados de atividades

## 📜 Licença

Este projeto é de uso interno. Consulte os termos de licença para mais informações.

## 📧 Suporte

Em caso de problemas, entre em contato com a equipe de desenvolvimento.
