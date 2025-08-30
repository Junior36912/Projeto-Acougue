Sistema de Gestão para Açougue
Sistema completo de gestão para açougue desenvolvido em Flask (Python) com funcionalidades de controle de estoque, vendas, fornecedores, usuários, relatórios e muito mais.

🚀 Funcionalidades
Autenticação e Autorização: Sistema de login com dois níveis de acesso (gerente e funcionário)

Gestão de Produtos: CRUD completo de produtos com controle de estoque, categorias, fornecedores e imagens

Gestão de Fornecedores: Cadastro e gerenciamento de fornecedores

Vendas: Registro de vendas à vista e a prazo (fiado)

Relatórios: Diversos relatórios (vendas, estoque, financeiro, clientes, etc.)

Backup Automático: Sistema de backup automático do banco de dados e imagens

Logs: Registro de atividades do sistema

Dashboard: Painel com métricas e alertas importantes

🛠️ Tecnologias Utilizadas
Backend: Flask (Python)

Banco de Dados: SQLite

Frontend: HTML, CSS, JavaScript (com templates Jinja2)

PDF: ReportLab para geração de relatórios em PDF

Agendamento: APScheduler para tarefas agendadas (backup, verificação de validades)

📁 Estrutura do Projeto
text
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
📦 Instalação e Configuração
Pré-requisitos
Python 3.8 ou superior

pip (gerenciador de pacotes do Python)

Passos
Clone o repositório

bash
git clone <url-do-repositorio>
cd Projeto-Acougue
Crie um ambiente virtual (recomendado)

bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
Instale as dependências

bash
pip install -r requirements.txt
Caso não tenha um arquivo requirements.txt, instale as dependências manualmente:

bash
pip install flask apscheduler reportlab werkzeug flask-wtf
Inicialize o banco de dados

bash
python -c "from banco_dados import init_db; init_db()"
Popule o banco com dados de teste (opcional)

bash
python tests/popular_banco.py
Execute a aplicação

bash
python app.py
A aplicação estará disponível em http://localhost:5000.

🔧 Uso
Acesso Inicial
URL: http://localhost:5000

Login padrão (após popular o banco):

Usuário: admin

Senha: admin123

Funcionalidades Principais
Dashboard: Visualize métricas rápidas e alertas de estoque

Produtos: Cadastre, edite e exclua produtos. Controle estoque e visualize produtos próximos do vencimento

Fornecedores: Gerencie os fornecedores dos produtos

Vendas: Registre vendas (à vista ou a prazo) e gerencie contas a receber

Relatórios: Gere relatórios em PDF ou visualize na tela

Admin: Gerencie usuários e permissões

Backup
Backups automáticos são gerados a cada 24 horas e podem ser baixados manualmente em /backup (apenas para gerentes).

🧪 Testes
O projeto inclui testes unitários e de integração. Para executar:

bash
pytest tests/ -v
⚙️ Personalização
Configurações
Edite a classe Config em app.py para alterar:

Chave secreta (SECRET_KEY)

Pasta de upload de imagens (UPLOAD_FOLDER)

Tamanho máximo de arquivo (MAX_FILE_SIZE_MB)

Extensões permitidas (ALLOWED_EXTENSIONS)

Adicionando Novos Relatórios
Edite a função relatorios_unificados em app.py para adicionar novos relatórios.

🔒 Segurança
Senhas são armazenadas usando hash (werkzeug.security)

Proteção contra CSRF (Flask-WTF)

Controle de acesso por roles (gerente/funcionário)

Logs de atividades detalhados

📄 Licença
Este projeto é de uso interno. Consulte os termos de licença para mais informações.

📞 Suporte
Em caso de problemas, entre em contato com a equipe de desenvolvimento.

New chat
