# Revisão do Projeto Açougue — Problemas, Correções e Melhorias

Registro permanente dos problemas encontrados no código. Serve de lista de trabalho entre sessões:
quem for corrigir algo marca o item aqui.

- **Revisão inicial:** 26/09/2026, sobre o commit `cb51f21` (branch `main`)
- **Situação atual (26/09/2026):** **63 de 107 itens corrigidos**, entre eles **todos os 12 críticos 🔴** e 30 dos 32 altos 🟠,
  com **195 testes** (os do pyflakes rodam com o `requirements-dev.txt`). Detalhes no **Histórico**, no fim do arquivo.
- **Escopo:** todo o código Python, templates, CSS, testes, banco `acougue.db`, dependências e repositório.
- **Método:** leitura do código, análise estática (pyflakes), execução da suíte de testes e chamadas reais
  às rotas com o cliente de teste do Flask **numa cópia isolada do projeto** (o banco original não foi tocado).
  Quando um item diz **"Verificado"**, o comportamento foi reproduzido na prática.

## Como usar este arquivo

- Cada item tem um **ID fixo** (ex.: `BUG-01`). Não renumere; ao adicionar itens, use o próximo número da seção.
- Ao corrigir: troque `- [ ]` por `- [x]` e anote o commit, ex.: `- [x] **BUG-01** ... ✅ corrigido em abc1234`.
- Se um item deixar de fazer sentido, marque `- [~]` e explique em uma linha.
- Registre cada nova revisão no **Histórico** no fim do arquivo.

**Severidade:** 🔴 Crítico (quebra função essencial, perda de dados ou falha de segurança grave) ·
🟠 Alto · 🟡 Médio · 🔵 Baixo / melhoria

---

## Resumo

| Seção | 🔴 | 🟠 | 🟡 | 🔵 | Total | Corrigidos |
|---|---|---|---|---|---|---|
| 1. Funcionalidades quebradas (BUG) | 6 | 12 | 8 | 4 | 30 | 28 |
| 2. Regras de negócio e integridade dos dados (NEG) | 3 | 4 | 5 | 0 | 12 | 10 |
| 3. Segurança (SEC) | 2 | 3 | 4 | 3 | 12 | 8 |
| 4. Banco de dados (DB) | 0 | 2 | 4 | 2 | 8 | 1 |
| 5. Relatórios e PDF (REL) | 0 | 3 | 2 | 2 | 7 | 4 |
| 6. Interface e templates (UI) | 0 | 1 | 7 | 2 | 10 | 3 |
| 7. Desempenho (PERF) | 0 | 1 | 4 | 1 | 6 | 1 |
| 8. Testes (TEST) | 1 | 3 | 1 | 1 | 6 | 4 |
| 9. Infraestrutura, dependências e repositório (INF) | 0 | 2 | 2 | 2 | 6 | 1 |
| 10. Qualidade de código (CODE) | 0 | 1 | 5 | 4 | 10 | 3 |
| **Total** | **12** | **32** | **42** | **21** | **107** | **63** |

Corrigidos por severidade: 🔴 12 de 12 · 🟠 30 de 32 · 🟡 16 de 42 · 🔵 5 de 21. Itens marcados com 🟨 estão parcialmente resolvidos.

### Próximos mais urgentes (pendentes)

1. **INF-02 / SEC-05 (restante)** — o histórico do git ainda guarda os bancos com hashes de senha e 112 MB de backups. Limpar exige reescrever o histórico e forçar o push no GitHub, **o que depende da sua decisão**.
2. **DB-01** — o caminho do banco é relativo à pasta de onde se roda o sistema; rodar de outra pasta cria um banco vazio sem avisar.
3. **NEG-08** — a venda a prazo aceita cliente sem nome e datas retroativas sem controle.
4. **SEC-07** — o upload confere só a extensão do arquivo, não se é mesmo uma imagem.
5. **DB-05** — o banco não tem restrições `CHECK` (preço, quantidade, cargo, forma de pagamento).
6. **REL-04 / UI-06** — "Vendas Totais", fornecedores e fiado não têm paginação.
7. **INF-03** — não há configuração para produção (servidor WSGI e serviço).
8. **INF-04** — o log só sai no console, sem arquivo nem rotação.
9. **PERF-03 / DB-06** — o alerta de validade grava um log por produto por dia, e a tabela `logs` cresce sem limite.
10. **DB-03** — o SQLite roda sem WAL e sem tempo de espera, o que pode dar "database is locked" com o scheduler rodando junto.

### Ordem sugerida de correção

1. ~~**Críticos**~~ ✅ feito em 26/09/2026.
2. ~~**Lote 2** (fiado, formas de pagamento, caixa, git, categorias, permissões, relatórios, decimais, mensagens, CSS, backup)~~ ✅ feito em 26/09/2026.
3. ~~**Lote 3** (datas e fuso, fornecedores, edição de produto, colunas dos relatórios, login, SQL dinâmico, dependências, miniaturas, índices, duplicatas)~~ ✅ feito em 26/09/2026.
4. **Dados e segurança:** DB-01, NEG-08, SEC-07, DB-05, DB-03, SEC-09, SEC-10.
5. **Operação:** INF-03, INF-04, PERF-03, DB-06, REL-04, UI-06.
6. **Repositório:** INF-02 (com decisão do usuário), INF-05, INF-06, DB-07, TEST-06.
7. **Estrutura e acabamento:** CODE-02, CODE-05 a CODE-10, UI-02, UI-03, REL-05, REL-06 e o restante.

---

## 1. Funcionalidades quebradas (BUG)

- [x] **BUG-01** 🔴 — [banco_dados.py:1-7](banco_dados.py#L1-L7) — **Imports removidos quebram usuários, senhas e fotos.**
  O commit `c3e2dd9` ("Limpeza...") removeu `generate_password_hash`, `secure_filename` e `current_app`.
  Foi a única mudança de conteúdo desse commit no arquivo; o resto foi conversão de fim de linha.
  Efeitos: `create_user` (tela "Novo Usuário" sempre mostra "Erro ao criar usuário"), `update_user(password=...)`,
  `atualizar_produto` com foto nova, `create_produto`, `update_produto` e a remoção de foto em `excluir_produto`, todos com `NameError`.
  *Verificado:* pyflakes aponta 14 nomes indefinidos; a suíte fica com 15 falhas.
  *Correção:* recolocar `from werkzeug.security import generate_password_hash`, `from werkzeug.utils import secure_filename`
  e `from flask import current_app`.
  ✅ **Corrigido em 26/09/2026.** Imports recolocados. *Testes:* `tests/test_criticos.py::test_bug01_*`.

- [x] **BUG-02** 🔴 — [banco_dados.py:1023-1082](banco_dados.py#L1023-L1082) — **A foto do produto novo é descartada.**
  `inserir_produto` recebe `foto`, mas grava sempre `'foto': None` e nunca salva o arquivo.
  *Verificado:* um POST em `/produtos/novo` com imagem gravou `foto = NULL`.
  *Correção:* salvar como em `atualizar_produto` (nome com timestamp + `secure_filename`) e apagar o arquivo se o INSERT falhar.
  ✅ **Corrigido em 26/09/2026.** `inserir_produto` grava o arquivo com `_salvar_foto` e o apaga se o INSERT falhar. *Testes:* `test_bug02_*`.

- [x] **BUG-03** 🔴 — [popular_banco.py:118](popular_banco.py#L118), [banco_dados.py:1140](banco_dados.py#L1140),
  [templates/produtos/listar.html:58](templates/produtos/listar.html#L58), [templates/vendas/nova.html:44](templates/vendas/nova.html#L44),
  [templates/produtos/editar.html:98](templates/produtos/editar.html#L98) — **O caminho da foto é gravado de dois jeitos.**
  O seed grava `uploads/produtos/x.png`, enquanto a edição grava só `1749388247.599506_OIP.jpeg`. A listagem e a tela de venda usam
  `url_for('static', filename=p.foto)`, que só funciona no 1º formato; a edição prefixa `uploads/produtos/`, que só funciona no 2º.
  *Verificado:* no banco atual, "Heineken" e o produto com `OIP.jpeg` aparecem com imagem quebrada na listagem e na venda.
  O arquivo antigo também nunca é apagado, porque o caminho montado fica duplicado.
  *Correção:* gravar só o nome do arquivo, montar a URL sempre com `'uploads/produtos/' + foto` e migrar as linhas existentes.
  ✅ **Corrigido em 26/09/2026.** O banco guarda só o nome do arquivo, e os templates montam `uploads/produtos/<foto>`. A migração 1 removeu o prefixo antigo das linhas existentes, e o `popular_banco.py` foi ajustado. Uma foto só é apagada quando nenhum outro produto a usa. *Testes:* `test_bug03_*`. *Verificado no servidor real:* as 46 imagens da tela de venda abrem.

- [x] **BUG-04** 🔴 — [app.py:930-940](app.py#L930-L940) — **`/admin/estoque` dá erro 500.** O template `admin/estoque.html` não existe.
  *Verificado:* status 500. *Correção:* criar o template ou remover a rota.
  ✅ **Corrigido em 26/09/2026.** Criado `templates/admin/estoque.html`, com link na home do gerente. *Teste:* `test_bug04_*`.

- [x] **BUG-05** 🔴 — [banco_dados.py:1341](banco_dados.py#L1341) — **Qualquer filtro em `/logs` dá erro 500.**
  A query de contagem não tem os `AND ...` dos filtros, mas recebe os parâmetros deles ("Incorrect number of bindings").
  *Verificado:* `/logs?level=INFO` → 500. *Correção:* montar a cláusula `WHERE` uma única vez e reutilizá-la nas duas queries.
  ✅ **Corrigido em 26/09/2026.** `_filtros_logs` monta o `WHERE` uma única vez, usado na listagem e na contagem. *Testes:* `test_bug05_*`.

- [x] **BUG-06** 🔴 — [templates/logs.html:77-171](templates/logs.html#L77-L171) (e o arquivo inteiro) — **A página de logs é uma maquete.**
  Os números são fixos ("1,248", "942"...), os usuários são fictícios ("João Silva", "Maria Oliveira"), os filtros não têm `name` nem `<form>`,
  e as variáveis `logs`, `usuarios` e `total_pages` enviadas pela rota são ignoradas. O gerente nunca vê os logs reais.
  A página também não tem link em nenhum lugar do sistema.
  *Correção:* reescrever o template iterando `logs`, com filtros reais e paginação; adicionar o link no menu do gerente.
  ✅ **Corrigido em 26/09/2026.** A página foi reescrita com os dados reais: filtros, cartões por nível, detalhes do JSON e paginação. Ganhou link na home do gerente. Também corrigido: `registrar_log` gravava os acentos escapados (`Cora\u00e7\u00e3o`), e a busca não encontrava "Coração". Os logs gravados antes da correção continuam escapados. *Testes:* `test_bug06_*`.

- [x] **BUG-07** 🟠 — [app.py:712](app.py#L712) — **A rota `/vendas/pagamento_prazo/pagar/<id>` quebra.** Ela redireciona para
  `url_for('listar_fiado')`, que não existe (BuildError). *Verificado:* 500. É uma duplicata de `pagar_venda_prazo`. *Correção:* remover.
  ✅ **Corrigido em 26/09/2026 (lote 2).** A rota duplicada foi removida. *Teste:* `tests/test_lote2.py::test_bug07_*`.

- [x] **BUG-08** 🟠 — [banco_dados.py:1283-1285](banco_dados.py#L1283-L1285), [app.py:1156-1163](app.py#L1156-L1163) — **"Pagar" sempre informa erro.**
  `marcar_venda_pago` retorna o `None` de `update_venda`, então a rota sempre redireciona com `error='Venda não encontrada ou já paga'`,
  mesmo quando o pagamento funcionou. A função também marca qualquer venda como paga, sem conferir se é a prazo ou se está pendente,
  e não grava log.
  *Correção:* `UPDATE ... WHERE id=? AND metodo_pagamento='pagamento_prazo' AND status_pagamento='pendente'`, retornando `rowcount > 0`.
  ✅ **Corrigido em 26/09/2026 (lote 2).** `marcar_venda_pago` só quita vendas a prazo pendentes, grava `data_pagamento` e retorna se deu certo. A tela mostra "Pagamento registrado" ou o motivo do erro, e o pagamento fica no log. *Testes:* `test_bug08_*`. *Verificado* quitando um fiado real.

- [x] **BUG-09** 🟠 — [app.py:1325-1331](app.py#L1325-L1331) — **As páginas 404/500 personalizadas nunca aparecem com `python app.py`.**
  Os `@app.errorhandler` ficam **depois** do bloco `if __name__ == '__main__': app.run()`, que bloqueia; eles só seriam registrados
  quando o servidor parasse. *Correção:* mover os handlers para antes do bloco `__main__`.
  ✅ **Corrigido em 26/09/2026.** Os handlers foram movidos para antes do bloco `__main__`. *Verificado* rodando `python app.py`.

- [x] **BUG-10** 🟠 — [app.py:1325](app.py#L1325) — **O scheduler, o backup e a verificação de validade rodam 2× a cada inicialização.**
  Com `debug=True`, o reloader do Werkzeug executa o bloco `__main__` no processo pai e no filho, criando 2 schedulers.
  *Evidência:* backups gêmeos `20250529_012859`/`_012900` e `20250608_110302`/`_110304` (mesmo tamanho); na tabela `logs`,
  108 dos 109 registros são `alerta_validade`, com 12 entradas no mesmo segundo para 6 produtos.
  *Correção:* iniciar só quando `os.environ.get('WERKZEUG_RUN_MAIN') == 'true'` (ou com `use_reloader=False`),
  ou mover os jobs para um processo separado.
  ✅ **Corrigido em 26/09/2026.** As tarefas só sobem sem reloader, ou no processo filho (`WERKZEUG_RUN_MAIN`). *Verificado* com `FLASK_DEBUG=1`: o scheduler sobe 1×.

- [x] **BUG-11** 🟠 — [templates/vendas/nova.html:154](templates/vendas/nova.html#L154), [:201](templates/vendas/nova.html#L201) — **A busca de produtos
  e o nome no carrinho estão quebrados.** Depois que a coluna "Imagem" foi adicionada, `row.children[0]` passou a ser a célula da imagem:
  a busca filtra pelo texto vazio ou "-", e o carrinho mostra o item sem nome.
  *Correção:* usar um atributo `data-nome` na `<tr>`.
  ✅ **Corrigido em 26/09/2026.** A busca e o carrinho usam `data-nome`.

- [x] **BUG-12** 🟠 — [templates/vendas/nova.html:144](templates/vendas/nova.html#L144), [:252](templates/vendas/nova.html#L252) —
  **A data da venda escolhida é ignorada.** `const dataVenda` é lida uma vez, quando a página carrega; se o operador mudar a data,
  o valor inicial é enviado mesmo assim. *Correção:* ler `document.getElementById('data_venda').value` no submit.
  ✅ **Corrigido em 26/09/2026.** A data da venda é lida no momento do envio.

- [x] **BUG-13** 🟠 — [app.py:694](app.py#L694) — **Duas vendas no mesmo segundo geram erro 500.** O ID é `V%Y%m%d%H%M%S`, e a segunda venda
  colide na chave primária. *Verificado:* dois POSTs seguidos, e o segundo retornou 500 "Erro ao registrar venda".
  *Correção:* usar `uuid4` ou uma chave `INTEGER AUTOINCREMENT` mais um código legível separado.
  ✅ **Corrigido em 26/09/2026.** O ID ganhou um sufixo aleatório (ex.: `V20260926172049-3FA2B1`). *Teste:* `test_bug13_*`.

- [x] **BUG-14** 🟠 — [templates/produtos/editar.html:25-29](templates/produtos/editar.html#L25-L29) — **Editar um produto troca a categoria dele.**
  O select tem só Bovino/Suíno/Aves, mas o banco tem BOI, PORCO, CARNEIRO, FRANGOS, CONGELADOS, BEBIDAS, Bovino...
  Ao salvar um produto de outra categoria, ela vira "Bovino" sem aviso. *Verificado:* a edição do produto 5 (BOI) não tem a opção BOI.
  O cadastro usa texto livre, e por isso as categorias ficaram inconsistentes.
  *Correção:* tabela `categorias` (ou lista fixa) usada no cadastro e na edição, e padronizar os dados existentes.
  ✅ **Corrigido em 26/09/2026 (lote 2).** A categoria virou um campo de texto com sugestões das categorias existentes (`<datalist>`), preenchido com a categoria atual. A migração 2 devolveu às categorias originais os 32 produtos que o formulário antigo tinha trocado para "Bovino" (e BEBIDA virou BEBIDAS); só "sdfghjk" ficou como estava. *Testes:* `test_bug14_*`.

- [x] **BUG-15** 🟡 — [app.py:498-501](app.py#L498-L501) — **Um erro de foto na edição abre a tela de cadastro.** Os erros de extensão ou tamanho
  renderizam `produtos/novo.html` em vez de `editar.html`. O usuário perde a edição e, se enviar o formulário, **cria um produto duplicado**.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Um erro de foto na edição volta para a tela de edição.

- [x] **BUG-16** 🟡 — [templates/produtos/novo.html](templates/produtos/novo.html) — **O cadastro de produto perde os dados quando dá erro.**
  A rota envia `form_data`, mas o template não o usa; só o `tipo_venda` é mantido.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O cadastro mantém os dados digitados quando dá erro, e as mensagens de validação aparecem (antes ficavam escondidas fora do modo debug). *Teste:* `test_neg05_erro_de_validacao_mantem_o_formulario`.

- [x] **BUG-17** 🟡 — [templates/fornecedores/editar.html:15](templates/fornecedores/editar.html#L15), [:29](templates/fornecedores/editar.html#L29) —
  **A edição de fornecedor corrompe dados.** O `<textarea>` tem espaços e quebras de linha em volta do valor, então cada salvamento
  acrescenta espaços ao endereço. O `padEnd(14,'0')` e o `padEnd(11,'0')` completam CNPJ e telefone incompletos com zeros.
  O formulário também não tem `<label>`.
  ✅ **Corrigido em 26/09/2026 (lote 3).** O formulário virou um só (`fornecedores/_form.html`), com rótulos, `<textarea>` sem espaços em volta e sem o `padEnd`. A máscara de telefone não mexe em contatos que sejam e-mail. No servidor, `_dados_fornecedor` remove espaços, padroniza o formato do CNPJ e valida os dígitos verificadores (`validar_cnpj`). Um CNPJ antigo mantido sem alteração é aceito, para não travar a edição dos cadastros existentes. *Testes:* `tests/test_lote3.py::test_bug17_*`. *Verificado:* salvar o fornecedor real duas vezes não alterou nada.

- [x] **BUG-18** 🟡 — [app.py:614-633](app.py#L614-L633) — **Excluir fornecedor nunca falha, e o aviso nunca aparece.** A FK é `ON DELETE SET NULL`:
  os produtos perdem o fornecedor sem aviso, e a mensagem "Não é possível excluir..." nunca é usada (nem seria exibida, ver BUG-19).
  ✅ **Corrigido em 26/09/2026 (lote 2).** A exclusão agora avisa quantos produtos ficaram sem fornecedor. *Teste:* `test_bug19_excluir_fornecedor_avisa_produtos_sem_fornecedor`.

- [x] **BUG-19** 🟡 — várias rotas — **As mensagens de sucesso e erro não aparecem.** As rotas mandam `?error=`/`?success=` na URL,
  mas `fornecedores/listar`, `vendas/listar_vendas_prazo` e `index` não leem esses parâmetros, e `flash()` nunca é chamado
  (o `flash_messages.html` fica sempre vazio). *Correção:* usar `flash()` em todo o sistema.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Todas as rotas usam `flash()`, exibido uma única vez pelo `base.html`. O parâmetro `?error=` na URL deixou de ser lido, e o `flash_messages.html`, que duplicava as mensagens, foi removido. *Testes:* `test_bug19_*`.

- [x] **BUG-20** 🟡 — [app.py:67-79](app.py#L67-L79), [banco_dados.py:1263-1265](banco_dados.py#L1263-L1265) — **Datas com microssegundos quebram a exibição.**
  O banco tem datas como `2025-05-14 16:12:02.682109`: `format_datetime` devolve a string crua, e `fetch_vendas_prazo` gera
  `ValueError` (erro 500) se uma venda a prazo tiver esse formato. *Correção:* usar `datetime.fromisoformat`.
  ✅ **Corrigido em 26/09/2026 (lote 3).** `ler_data_hora` (usando `datetime.fromisoformat`) lê qualquer formato gravado; `format_datetime` e a tela de fiado usam essa função e só mostram a hora quando ela existe. *Testes:* `test_bug20_*`.

- [x] **BUG-21** 🟡 — [templates/base.html:24-28](templates/base.html#L24-L28), [templates/index.html:44](templates/index.html#L44),
  [decorators.py:20](decorators.py#L20) — **Um funcionário "cai" para a tela de login.** O menu mostra Produtos e Fornecedores para todos,
  e a home mostra "Vendas a Prazo" para o funcionário, mas essas páginas exigem gerente. `role_required` redireciona para `/login`
  mesmo com o usuário logado. *Verificado:* funcionário → `/vendas/listar_vendas_prazo` → 302 `/login`.
  *Correção:* esconder os links conforme o cargo e responder 403 com uma página própria.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O menu e a home escondem as páginas de gerente do funcionário, e o acesso negado mostra uma página 403 sem deslogar (ver SEC-03). *Testes:* `test_sec03_*`.

- [ ] **BUG-22** 🔵 — [templates/base.html:61](templates/base.html#L61) — O rodapé mostra "© Açougue" sem o ano: `current_year` nunca é definido.
  *Correção:* usar um `@app.context_processor`.

- [ ] **BUG-23** 🔵 — [app.py:1068](app.py#L1068) — A página `/dashboard` não tem link em lugar nenhum; só dá para abrir digitando a URL.

- [x] **BUG-24** 🔵 — [templates/base.html:19-29](templates/base.html#L19-L29) — A tela de login mostra o menu (Home/Produtos/Fornecedores/Sair)
  para quem ainda não entrou.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O menu só aparece para quem está logado. *Teste:* `test_bug24_*`.

- [x] **BUG-25** 🟠 — [banco_dados.py:1037](banco_dados.py#L1037), [:1129](banco_dados.py#L1129) — **Não dá para salvar produto com "Estoque mínimo" vazio.**
  O navegador envia o campo vazio (`''`), e `int('')` estoura.
  *Verificado:* o cadastro mostra "Erro ao cadastrar produto"; a edição mostra ao usuário a mensagem crua do Python
  `invalid literal for int() with base 10: ''`. *Correção:* `int(form.get('estoque_minimo') or 0)` e validar antes.
  ✅ **Corrigido em 26/09/2026.** Usa `int(form.get('estoque_minimo') or 0)` no cadastro e na edição. *Teste:* `test_bug02_cadastro_sem_foto_e_sem_estoque_minimo`.

- [x] **BUG-26** 🟠 — [banco_dados.py:1130-1132](banco_dados.py#L1130-L1132) — **Não dá para limpar campos opcionais na edição.**
  `form.get(x) or existing[x]` faz um campo vazio voltar ao valor antigo, então nunca se remove o código de barras, o fornecedor
  ou a validade de um produto.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Na edição, um campo opcional enviado vazio limpa o valor; um campo que não veio no formulário mantém o atual. *Testes:* `test_bug26_*`. *Verificado* com o Bacon real (código de barras, fornecedor e validade limpos).

- [x] **BUG-27** 🟠 — [banco_dados.py:1162-1179](banco_dados.py#L1162-L1179) — **Excluir um produto que já foi vendido mostra "Erro interno".**
  No banco atual, `venda_itens` não tem CASCADE (ver NEG-04), e a versão ativa de `excluir_produto` não trata `IntegrityError`.
  A versão antiga, [linha 721](banco_dados.py#L721), tratava, mas foi sobrescrita (CODE-01).
  *Verificado:* `IntegrityError: FOREIGN KEY constraint failed`.
  *Correção:* adotar soft delete (`ativo = 0`) para produtos com vendas (ver NEG-03).
  ✅ **Corrigido em 26/09/2026.** Um produto com vendas agora é desativado em vez de excluído (ver NEG-03).

- [x] **BUG-28** 🔵 — [app.py:235](app.py#L235) — **Dois backups no mesmo segundo gravam o mesmo arquivo.** O nome do backup tem precisão
  de segundos, então um segundo backup no mesmo segundo (ex.: duplo clique em "Backup Completo") sobrescreve o primeiro.
  Encontrado na verificação de 26/09/2026. *Correção:* incluir microssegundos ou um sufixo aleatório no nome.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O nome do backup inclui microssegundos. *Teste:* `test_bug28_*`.

- [x] **BUG-29** 🟠 — [templates/produtos/editar.html](templates/produtos/editar.html) — **A edição de produto gravava o texto "None".**
  Com o código de barras ou a descrição vazios, o formulário antigo exibia e reenviava o texto `None`. Isso gravou "None" na descrição de 32 produtos
  e no código de barras do "Abatido"; como o código de barras é único, um segundo produto editado sem código daria erro.
  Encontrado ao reescrever o formulário em 26/09/2026.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Os campos vazios são renderizados vazios, e a migração 2 trocou os "None" gravados por NULL. *Testes:* `test_bug14_editar_produto_mantem_a_categoria`, `test_bug29_*`.

- [x] **BUG-30** 🟡 — [app.py](app.py) — **O relatório de validade escondia o produto que vence hoje.** A conta `JULIANDAY(data_validade) - JULIANDAY('now')` incluía
  a hora atual (em UTC), então um produto com validade de hoje dava -0,x dia e ficava fora do filtro "entre 0 e N dias". Encontrado ao corrigir o NEG-11, em 26/09/2026.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Os dias são contados entre a validade e a data local de hoje, em números inteiros. *Teste:* `test_neg11_produto_que_vence_hoje_aparece_no_relatorio`.

## 2. Regras de negócio e integridade dos dados (NEG)

- [x] **NEG-01** 🔴 — [banco_dados.py:859](banco_dados.py#L859), [:920](banco_dados.py#L920), [templates/vendas/nova.html:201](templates/vendas/nova.html#L201) —
  **O preço vem do navegador.** O total e o `preco_unitario` usam o `item['preco']` enviado pelo cliente; nos produtos por unidade,
  o JS lê o preço do texto da página. Qualquer usuário logado, inclusive funcionário, pode vender a R$ 0,01 pelo DevTools.
  *Verificado:* venda aceita com `preco: 0.01`.
  *Correção:* buscar o preço no banco. Para os produtos por quilo, definir uma regra (hoje o operador digita o R$/kg em cada venda).
  ✅ **Corrigido em 26/09/2026.** `processar_venda` usa o preço do cadastro em todos os itens e ignora o preço enviado pelo navegador; nos produtos por quilo, o preço cadastrado é o R$/kg. A tela mostra o preço do cadastro, e um produto sem preço fica com o botão desabilitado. **Mudança de comportamento:** o operador não digita mais o R$/kg na hora da venda. *Testes:* `test_neg01_*`.

- [x] **NEG-02** 🔴 — [banco_dados.py:837-926](banco_dados.py#L837-L926) — **Nenhuma validação dos itens no servidor.**
  *Verificado:* quantidade negativa é aceita e **aumenta** o estoque (10 → 60); quantidade acima do estoque é aceita
  (o estoque foi a **-99983**); um carrinho vazio cria uma venda de R$ 0; um produto inexistente dá 500.
  *Correção:* dentro da transação, validar `quantidade > 0`, a existência do produto e usar
  `UPDATE produtos SET quantidade = quantidade - ? WHERE id = ? AND quantidade >= ?`, conferindo o `rowcount`.
  Rejeitar carrinho vazio.
  ✅ **Corrigido em 26/09/2026.** O servidor valida cada item: quantidade maior que zero e finita, inteira nos produtos por unidade, produto existente e ativo, carrinho não vazio e JSON válido. A baixa usa `UPDATE ... WHERE quantidade >= ?` dentro de uma transação `BEGIN IMMEDIATE`, e qualquer falha desfaz a venda inteira. *Testes:* `test_neg02_*`.

- [x] **NEG-03** 🔴 — [banco_dados.py:195-221](banco_dados.py#L195-L221) — **Exclusões apagam o histórico financeiro.**
  `vendas.usuario_id ON DELETE CASCADE`: excluir um funcionário apaga todas as vendas dele (o `admin` tem 29 vendas no banco atual).
  Num banco novo, `venda_itens.produto_id ON DELETE CASCADE` também apaga os itens vendidos quando se exclui um produto,
  e os totais e relatórios passados ficam inconsistentes.
  *Correção:* `ON DELETE RESTRICT` mais soft delete (`ativo = 0`) para usuários e produtos.
  ✅ **Corrigido em 26/09/2026.** `users` e `produtos` ganharam a coluna `ativo`: quem tem vendas é desativado em vez de apagado. O login, as listagens, a tela de venda e os relatórios de estoque ignoram os inativos. As FKs foram recriadas sem CASCADE (a migração 1 recria `vendas` e `venda_itens`, com backup automático antes). *Testes:* `test_neg03_*`. *Verificado* numa cópia do banco real: as 25 vendas do usuário excluído foram preservadas.

- [x] **NEG-04** 🟠 — [banco_dados.py:272-451](banco_dados.py#L272-L451) — **O esquema do banco depende de quando ele foi criado.**
  O `acougue.db` atual difere do `init_db`: não tem CASCADE em `venda_itens`, usa `DECIMAL(10,2)` em vez de `NUMERIC`,
  e a FK de fornecedor não tem `ON UPDATE`. Como `CREATE TABLE IF NOT EXISTS` nunca altera tabelas existentes e não há migrações,
  o comportamento de exclusão depende da idade do banco.
  *Correção:* migrações versionadas (`PRAGMA user_version` com scripts, ou Alembic, que já está no requirements).
  🟨 **Parcial (26/09/2026):** agora existe um mecanismo de migração (`PRAGMA user_version` + `_migrar`, com backup automático antes), e `vendas` e `venda_itens` têm o mesmo esquema em bancos novos e antigos. Ainda restam diferenças de tipo (`DECIMAL` vs `NUMERIC`) na tabela `produtos`.
  ✅ **Corrigido em 26/09/2026 (lote 2).** A migração 2 recriou `produtos` e `venda_itens` com o esquema atual; bancos novos e antigos agora têm o mesmo esquema.

- [x] **NEG-05** 🟠 — [banco_dados.py:170](banco_dados.py#L170), [:218](banco_dados.py#L218), [:1028](banco_dados.py#L1028), [:1129](banco_dados.py#L1129) —
  **Estoque em kg numa coluna INTEGER.** Os formulários convertem com `int()`, então não se cadastra 2,5 kg, mas as vendas subtraem
  frações (o banco tem 91.6, 18.235). *Correção:* guardar gramas em INTEGER (ou REAL, com cuidado) e aceitar decimais
  conforme o `tipo_venda`.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Quantidade e estoque mínimo são `REAL` (migração 2). O formulário aceita decimais e vírgula nos produtos por quilo e exige inteiros nos por unidade, com o passo do campo ajustado conforme o tipo. *Testes:* `test_neg05_*`. *Verificado:* Bacon salvo com 5,5 kg.

- [x] **NEG-06** 🟠 — [banco_dados.py:891](banco_dados.py#L891) — **Dinheiro em float sem arredondamento.** *Evidência:* há vendas com total
  `96.998` e `13.008` no banco. *Correção:* guardar em centavos (INTEGER) ou usar `Decimal` com `quantize(Decimal('0.01'), ROUND_HALF_UP)`.
  🟨 **Parcial (26/09/2026):** a venda arredonda cada item e o total para centavos, mas os valores ainda são guardados como float.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Os valores são calculados com `Decimal` e arredondados em centavos, meio para cima (`arredondar_dinheiro`), por item e no total. A migração 2 arredondou os dados antigos (96,998 virou 97,00) e a soma geral ficou igual. *Testes:* `test_neg06_*`.

- [x] **NEG-07** 🟠 — [templates/vendas/nova.html:102-106](templates/vendas/nova.html#L102-L106) — **As formas de pagamento não têm valor fixo.**
  Os `<option>` sem `value` gravam o texto exibido. *Evidência:* o banco tem `dinheiro`, `Dinheiro`, `PIX` e `pagamento_prazo`,
  e os relatórios agrupam "Dinheiro" e "dinheiro" separadamente.
  *Correção:* valores fixos (`dinheiro`, `debito`, `credito`, `pix`, `prazo`), validação no servidor, `CHECK` no banco
  e migração dos dados existentes.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Os valores agora são fixos (`dinheiro`, `debito`, `credito`, `pix`, `pagamento_prazo`) e ficam em `FORMAS_PAGAMENTO`. O servidor valida a forma e aceita os textos antigos, a migração 2 padronizou os dados e as telas mostram o nome legível (filtro `forma_pagamento`). *Testes:* `test_neg07_*`. O `CHECK` no banco continua pendente (DB-05).

- [ ] **NEG-08** 🟡 — [app.py:639-704](app.py#L639-L704) — **A venda a prazo tem validação fraca.** O nome do cliente não é obrigatório
  no servidor, e aparece "None" na lista de clientes. O vencimento é comparado com hoje, não com a data da venda. A data da venda
  pode ser qualquer uma (*verificado:* uma venda retroativa de 2020 foi aceita). O CPF não é validado. Sem `metodo_pagamento`, dá 500 (`KeyError`).

- [ ] **NEG-09** 🟡 — [banco_dados.py:1283](banco_dados.py#L1283) — **O recebimento do fiado não guarda histórico.** Não registra a data do pagamento,
  a forma, quem recebeu nem pagamentos parciais. *Melhoria:* tabela `pagamentos` ligada à venda.
  🟨 **Parcial (26/09/2026):** a quitação grava a data do pagamento, e o log registra quem quitou. Faltam a forma de pagamento e os pagamentos parciais.

- [x] **NEG-10** 🟡 — [app.py:663](app.py#L663) — **A venda grava só a data, sem hora.** O dashboard mostra "Hora 00:00" em tudo
  e perde a ordem das vendas no dia. *Correção:* combinar a data escolhida com a hora atual.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Venda com data de hoje grava data e hora (`AAAA-MM-DD HH:MM:SS`); venda lançada em outro dia grava só a data, e as telas não mostram "00:00". *Testes:* `test_neg10_*`.

- [x] **NEG-11** 🟡 — [app.py:1083](app.py#L1083), [:1089](app.py#L1089), [:1110](app.py#L1110), [:1118](app.py#L1118) — **Mistura de UTC com horário local.**
  No SQLite, `DATE('now')` e `CURRENT_TIMESTAMP` são UTC; o Python grava a data local (UTC-3). Entre 21h e 23h59, "Vendas de Hoje"
  sai zerado, e os logs ficam 3h adiantados. *Verificado:* `datetime('now')` retornou 19:45 quando a hora local era 16:45.
  *Correção:* passar a data calculada pelo Python como parâmetro, ou usar `'localtime'`, de forma padronizada.
  ✅ **Corrigido em 26/09/2026 (lote 3).** O dashboard filtra por intervalo de datas locais calculado no Python (`intervalo_de_hoje`), o que também usa o índice novo. O relatório de validade conta os dias a partir da data local; antes, o produto que vencia hoje sumia do relatório. O PDF usa `DATE('now', 'localtime')`, os logs são gravados com a hora local e a migração 3 converteu os logs antigos de UTC para a hora local (13:10 virou 10:10). Os campos `created_at` continuam com o padrão UTC do SQLite, mas não aparecem em nenhuma tela. *Testes:* `test_neg11_*`, que simulam o horário das 21h às 24h trocando o fuso do processo.

- [x] **NEG-12** 🟡 — [decorators.py](decorators.py), [app.py:1023-1053](app.py#L1023-L1053) — **O cargo fica congelado na sessão.**
  Um gerente rebaixado ou excluído continua com acesso até sair, porque o `role` fica no cookie. Um gerente também pode excluir
  a própria conta. *Correção:* recarregar o usuário do banco a cada request (`before_request`) e bloquear a autoexclusão.
  ✅ **Corrigido em 26/09/2026 (lote 2).** `before_request` relê o usuário a cada requisição: quem é desativado sai na hora, e mudança de cargo vale na requisição seguinte. Também não é mais possível excluir a própria conta. *Testes:* `test_neg12_*`. *Verificado* com duas sessões no servidor real.

## 3. Segurança (SEC)

- [x] **SEC-01** 🔴 — [app.py:107](app.py#L107) — **Chave secreta padrão fixa (`'dev-key-123'`).** O cookie de sessão do Flask é só assinado; com a chave
  conhecida, qualquer pessoa forja `{'user_id': 1, 'role': 'gerente'}`. *Correção:* exigir `SECRET_KEY` por variável de ambiente
  ou `.env` e recusar iniciar sem ela.
  ✅ **Corrigido em 26/09/2026.** A chave vem de `SECRET_KEY` ou é gerada uma única vez em `instance/secret_key` (permissão 600, fora do git). **Efeito:** as sessões abertas antes da atualização expiram, então é preciso entrar de novo. *Testes:* `test_sec01_*`.

- [x] **SEC-02** 🔴 — [app.py:1325](app.py#L1325) — **`app.run(debug=True)` fixo no código.** O debugger do Werkzeug permite executar código
  se ficar acessível na rede, e expõe stack traces. *Correção:* ler o modo debug do ambiente e usar waitress ou gunicorn em produção.
  ✅ **Corrigido em 26/09/2026.** O debug só liga com `FLASK_DEBUG=1`; host e porta vêm de `FLASK_RUN_HOST` e `FLASK_RUN_PORT`. *Testes:* `test_sec02_*`. *Verificado:* o erro 500 aparece sem o debugger.

- [x] **SEC-03** 🟠 — [decorators.py:12-21](decorators.py#L12-L21) — **A autorização confia só na sessão** (ver NEG-12), e o acesso negado
  vira redirecionamento para o login em vez de 403.
  ✅ **Corrigido em 26/09/2026 (lote 2).** `role_required` responde 403 com a página "Acesso restrito", e o cargo vem sempre do banco (NEG-12). *Testes:* `test_sec03_*`.

- [x] **SEC-04** 🟠 — [app.py:328-372](app.py#L328-L372) — **Login sem proteções.** Não há limite de tentativas, as falhas de login não são registradas,
  a sessão não é limpa ao entrar, não há `SESSION_COOKIE_SAMESITE` nem `SESSION_COOKIE_SECURE` (se usar HTTPS),
  e não há tempo de expiração da sessão. *Correção:* Flask-Limiter (ou um contador simples), registrar as falhas, configurar os cookies.
  ✅ **Corrigido em 26/09/2026 (lote 3).** O login bloqueia o usuário por 15 minutos após 5 erros, e o IP após 20 erros em qualquer usuário (tabela `login_falhas`, com resposta 429). As falhas e os bloqueios vão para o log, e um login certo zera os erros. O cookie de sessão agora é `SameSite=Lax` e `HttpOnly` e expira em 12h. *Testes:* `test_sec04_*`. *Verificado* no servidor real: a 6ª tentativa recebe 429.

- [x] **SEC-05** 🟠 — [.gitignore](.gitignore) — **Banco com dados reais versionado.** `acougue.db` e `tests/acougue.db` estão no git,
  com hashes de senha e nomes de clientes. A senha padrão `admin/admin123` está no README e no seed.
  *Correção:* `git rm --cached acougue.db tests/acougue.db`, colocar `*.db` no `.gitignore` e forçar a troca da senha padrão.
  ✅ **Corrigido em 26/09/2026 (lote 2).** `acougue.db` e `tests/acougue.db` saíram do índice do git (`git rm --cached`, falta commitar) e `*.db` entrou no `.gitignore`. Quem entra com a senha padrão `admin123` é obrigado a trocá-la, e há uma página "Senha" para qualquer usuário. **Atenção:** os bancos continuam no **histórico** do git (13 commits) e no GitHub. Limpar o histórico exige reescrevê-lo (`git filter-repo`) e forçar o push, o que não foi feito. *Testes:* `test_sec05_*`.

- [x] **SEC-06** 🟡 — [banco_dados.py:575-581](banco_dados.py#L575-L581), [:631-641](banco_dados.py#L631-L641), [:693-714](banco_dados.py#L693-L714),
  [:812-816](banco_dados.py#L812-L816), [:968-972](banco_dados.py#L968-L972) — **Nomes de coluna montados a partir dos `**kwargs`.**
  Hoje as chaves vêm do código; se um dia vierem de `request.form`, vira SQL injection. *Correção:* lista branca de colunas.
  ✅ **Corrigido em 26/09/2026 (lote 3).** `_clausula_set` (e uma checagem equivalente no `update_produto`) aceita só as colunas conhecidas de cada tabela e recusa o resto com `ValueError`. *Testes:* `test_sec06_*`.

- [ ] **SEC-07** 🟡 — [app.py:131-133](app.py#L131-L133) — **O upload valida só a extensão, não o conteúdo.** *Correção:* abrir com Pillow
  (`Image.open().verify()`) e regravar a imagem (o que também reduz o tamanho, ver UI-04).

- [x] **SEC-08** 🟡 — [templates/vendas/nova.html:165-170](templates/vendas/nova.html#L165-L170) — **XSS no carrinho.** O HTML é montado com
  `innerHTML` a partir do nome do produto (via `textContent`, que decodifica as entidades). Um produto chamado
  `<img src=x onerror=...>` executa script na tela de venda. *Correção:* montar com `createElement` e `textContent`.
  ✅ **Corrigido em 26/09/2026.** O carrinho é montado com `textContent`.

- [ ] **SEC-09** 🟡 — [app.py:274-286](app.py#L274-L286) — **`GET /backup` gera um backup completo (~19 MB) a cada acesso.**
  É um GET com efeito colateral, disparável por CSRF (uma `<img src=/backup>`) contra um gerente logado, e pode encher o disco (ver PERF-01).
  *Correção:* usar POST com token, limitar a frequência e servir o último backup se ele for recente.
  🟨 **Parcial (26/09/2026):** o download não grava mais arquivo em disco; continua sendo um GET pesado, sem limite de frequência.

- [ ] **SEC-10** 🔵 — [app.py:403](app.py#L403) — Logout por GET (dá para deslogar alguém via CSRF). Preferir POST.

- [x] **SEC-11** 🔵 — [templates/produtos/listar.html:7](templates/produtos/listar.html#L7), [templates/admin/usuarios.html:12](templates/admin/usuarios.html#L12) —
  Mensagens vindas da URL são exibidas como alerta do sistema: um link como `?error=Sistema+bloqueado,+ligue+para...` serve para phishing.
  Não é XSS (o texto é escapado). Resolvido junto com BUG-19 (`flash`).
  ✅ **Corrigido em 26/09/2026 (lote 2).** As mensagens vêm só de `flash()` (ver BUG-19). *Teste:* `test_bug19_texto_na_url_nao_vira_mensagem_do_sistema`.

- [ ] **SEC-12** 🔵 — [templates/base.html:8](templates/base.html#L8) — Os CDNs (Font Awesome, ECharts, Bootstrap) são carregados sem `integrity` (SRI).
  Servir os arquivos localmente também faz o sistema funcionar sem internet, o que é útil num comércio.

## 4. Banco de dados (DB)

- [ ] **DB-01** 🟠 — [banco_dados.py:15-129](banco_dados.py#L15-L129), [gerador_pdf.py:30-38](gerador_pdf.py#L30-L38), [app.py:110](app.py#L110) — **Três fontes
  de verdade para o banco, e todas relativas à pasta atual.** `DB_PATH` no ambiente, `'acougue.db'` fixo no gerador de PDF e
  `app.config['DATABASE']`, usado só no backup. Rodar o sistema a partir de outra pasta cria **um banco novo e vazio** sem avisar,
  e o PDF ignora o `DB_PATH`. *Correção:* uma única configuração, com caminho absoluto baseado na raiz do app;
  o PDF deve reutilizar `banco_dados.get_db_connection`.
  🟨 **Parcial (26/09/2026):** o PDF e o backup usam a mesma conexão do sistema (`DB_PATH`), mas o caminho padrão continua relativo à pasta atual.

- [x] **DB-02** 🟠 — [banco_dados.py:140-234](banco_dados.py#L140-L234) — **Sem índices.** Criar em `vendas(data)`, `vendas(metodo_pagamento, status_pagamento)`,
  `venda_itens(venda_id)`, `venda_itens(produto_id)`, `logs(timestamp)`, `produtos(categoria)` e `produtos(nome)`.
  As queries com `DATE(v.data) = ...` também impedem o uso de índice; trocar por um intervalo (`data >= ? AND data < ?`).
  ✅ **Corrigido em 26/09/2026 (lote 3).** Dez índices (vendas por data, forma e usuário; itens por venda e produto; produtos por nome e categoria; logs por data; falhas de login), criados depois das migrações para não se perderem quando uma tabela é recriada. *Testes:* `test_db02_*`, incluindo o plano de consulta do dashboard.

- [ ] **DB-03** 🟡 — [banco_dados.py:125-135](banco_dados.py#L125-L135) — **Configuração do SQLite frágil para concorrência.** Cada função abre uma conexão nova,
  sem WAL e sem `timeout`/`busy_timeout`. Com o scheduler e as requisições ao mesmo tempo, pode ocorrer "database is locked".
  *Correção:* `PRAGMA journal_mode=WAL`, `timeout=10` e uma conexão por request em `flask.g`.

- [ ] **DB-04** 🟡 — [banco_dados.py:184-191](banco_dados.py#L184-L191) — **O trigger de `updated_at` dobra as escritas.** Ele faz um segundo UPDATE a cada UPDATE,
  inclusive a cada item vendido. *Correção:* incluir `updated_at = CURRENT_TIMESTAMP` no próprio UPDATE.

- [ ] **DB-05** 🟡 — [banco_dados.py:140-234](banco_dados.py#L140-L234) — **Sem restrições `CHECK`.** Faltam `preco > 0`, `quantidade >= 0`,
  `role IN (...)`, `status_pagamento IN (...)`, `metodo_pagamento IN (...)` e `tipo_venda IN ('unidade','quilo')`.

- [ ] **DB-06** 🟡 — [app.py:1306](app.py#L1306) — **A tabela `logs` recebe texto numa coluna INTEGER e cresce sem limite.**
  `logs.user_id` é INTEGER, mas recebe `'Sistema'`; o alerta diário de validade insere um registro por produto por dia (duplicado, ver BUG-10).
  *Correção:* `user_id` NULL para eventos do sistema e uma política de retenção.

- [ ] **DB-07** 🔵 — `schema.sql` e `instance/estoque.db` estão vazios (0 bytes), e a pasta `cypress/` também. Remover ou preencher.

- [ ] **DB-08** 🔵 — (confirmado no log do servidor: `DeprecationWarning` em `verificar_validades`) — [popular_banco.py:142](popular_banco.py#L142), [banco_dados.py:879](banco_dados.py#L879) — Objetos `datetime`/`date` passados direto ao sqlite3
  usam o adaptador padrão, obsoleto desde o Python 3.12. Converter para string ISO explicitamente.

## 5. Relatórios e PDF (REL)

- [x] **REL-01** 🟠 — [templates/relatorio_unificado.html:169](templates/relatorio_unificado.html#L169) — **Contagens aparecem como dinheiro.**
  Qualquer coluna numérica com "total" no nome vira moeda: `total_vendas`, `total_compras`, `total_produtos` e `total_estoque`
  aparecem como "R$ 5,00". *Correção:* definir o formato de cada coluna na configuração do relatório.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Cada relatório declara suas colunas, com título e formato (`COLUNAS_RELATORIOS`: moeda, quantidade, inteiro, data, texto), exibidas pelo filtro `formatar_celula`. As colunas numéricas ficam alinhadas à direita; para isso foi preciso vencer a regra `.table td { text-align: left }` no CSS. *Testes:* `test_rel01_*`.

- [x] **REL-02** 🟠 — [app.py:791-880](app.py#L791-L880) — **Um parâmetro inválido derruba qualquer relatório.** Os 10 relatórios são montados
  a cada request, e `int(request.args.get(...))` roda para todos: `?limit=abc` dá 500 em **qualquer** relatório. *Verificado.*
  *Correção:* `request.args.get('limit', 10, type=int)` com limites mínimo e máximo, e montar só o relatório pedido.
  ✅ **Corrigido em 26/09/2026 (lote 2).** Os parâmetros são lidos com `type=int` e limitados a uma faixa (`_arg_inteiro`); datas inválidas usam o padrão (`parse_date`). *Testes:* `test_rel02_*`, cobrindo os 10 relatórios.

- [x] **REL-03** 🟠 — [app.py:868-870](app.py#L868-L870), [gerador_pdf.py:324-327](gerador_pdf.py#L324-L327) — **"Movimentação de Caixa" está errada.**
  O relatório compara com `'fiado'`, que nunca é gravado (o valor real é `pagamento_prazo`), então as vendas a prazo entram como entrada de caixa.
  Além disso, trata fiado como "saída", o que também está conceitualmente errado: fiado é conta a receber.
  *Correção:* entradas = vendas pagas (por data de pagamento); a receber = pendentes.
  ✅ **Corrigido em 26/09/2026 (lote 2).** A movimentação lista, por dia: vendas à vista, fiado recebido (na data do pagamento), total de entradas e o que foi vendido a prazo (a receber). A consulta é uma só (`SQL_MOVIMENTACAO_CAIXA`), usada pela tela e pelo PDF, e a lambda do PDF saiu. *Testes:* `test_rel03_*`.

- [ ] **REL-04** 🟡 — [app.py:792-808](app.py#L792-L808) — **"Vendas Totais" carrega todo o histórico.** Não tem paginação nem filtro de período,
  e usa `GROUP_CONCAT`; vai ficar lento com o tempo.

- [ ] **REL-05** 🟡 — [gerador_pdf.py](gerador_pdf.py) — **Problemas no PDF.**
  - O logo aponta para `static/images/logo.png`, que não existe (o real é `static/img/logo-acougue.png`), e o caminho é relativo à pasta atual.
  - `TEXTCOLOR` com `lambda` ([:191](gerador_pdf.py#L191), [:352](gerador_pdf.py#L352)) não é suportado pelo ReportLab: a cor condicional não é aplicada,
    e a lambda da linha 344 ainda converteria errado o formato brasileiro de moeda.
  - `format_currency(None)` gera `TypeError` se algum `SUM` vier NULL.
  - O mesmo bloco de `TableStyle` aparece copiado 7×.
  - Usa o tamanho de página `letter` em vez de A4.
  🟨 **Parcial (26/09/2026):** a lambda da movimentação de caixa foi removida e o PDF usa a conexão do sistema; os outros pontos continuam.

- [ ] **REL-06** 🔵 — **Código morto nos relatórios.** [templates/relatorios/relatorios.html](templates/relatorios/relatorios.html) usa o filtro
  inexistente `format_date` e variáveis que nunca são enviadas; [templates/relatorios/relatorio_unificado.html](templates/relatorios/relatorio_unificado.html)
  é uma cópia antiga que não é usada. Também não são usados: `parse_date` ([app.py:753-757](app.py#L753-L757), com `except` genérico)
  e os ramos `post_process` e `contas_receber`.

- [x] **REL-07** 🔵 — [templates/relatorio_unificado.html:244-247](templates/relatorio_unificado.html#L244-L247) — Os dados do gráfico são interpolados
  como string dentro do JS: `valor_total` None vira `None`, que quebra o script. Usar o filtro `|tojson`.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Os dados do gráfico passam por `|tojson`. *Teste:* `test_rel07_*`.

## 6. Interface e templates (UI)

- [x] **UI-01** 🟠 — [templates/base.html](templates/base.html) — **Classes do Bootstrap sem o Bootstrap carregado.** Os templates usam classes do Bootstrap
  (`alert-danger`, `btn-secondary`, `btn-success`, `btn-warning`, `row`, `col-md-*`, `d-flex`, `badge bg-*`, `form-select`) e ícones `bi-*`,
  mas o `base.html` não carrega nem o Bootstrap nem o Bootstrap Icons (só o antigo `logs.html` carregava). Esses alertas e grids ficam sem estilo,
  e os ícones `bi-*` não aparecem. *(A nota de 26/09 que dizia que `.btn-primary` e `.btn-danger` existiam via CSS aninhado estava errada: ver a correção abaixo.)*
  *Correção:* incluir o Bootstrap no `base.html` ou definir as classes que faltam no `styles.css`.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O `styles.css` ganhou uma seção de utilitários que substitui as classes do Bootstrap usadas nos templates, e os ícones `bi-*` foram trocados por Font Awesome. **Achado durante a verificação visual:** `.btn-primary`, `.btn-danger` e `.badge-estoque` estavam escritas como `.btn { &-primary {…} }`, sintaxe do Sass que o navegador descarta, então esses botões **nunca tiveram estilo**; foram definidas de forma explícita. *Testes:* `test_ui01_*` confere que toda classe usada nos templates tem estilo. *Verificado* com capturas de tela no Chrome headless.
- [ ] **UI-02** 🟡 — [static/styles.css](static/styles.css) — **CSS duplicado e desorganizado.** Há regras duplicadas (`.login-container` 6×,
  `.footer-link` 4×, `.dashboard-container` 3×, `.main-footer` 2×, `.card` 2×), classes que nenhum template usa (`.header`, `.metricas-dia`,
  `.metrica-card`), CSS aninhado nativo (não funciona em navegadores antigos) e o `:root` no meio do arquivo.
  As regras escritas como `&-primary`, `&-danger` e `&-estoque` usam sintaxe do Sass e são descartadas pelo navegador. Viraram código morto, porque as classes agora estão definidas explicitamente (UI-01), mas deveriam ser removidas.
  O `<style>` do [admin/novo_usuario.html](templates/admin/novo_usuario.html#L45-L60) muda o `.container` de todo o layout.

- [ ] **UI-03** 🟡 — [templates/logs.html:7-8](templates/logs.html#L7-L8) — Carrega o Font Awesome 6 além do 5 do `base.html`: duas versões na mesma página.

- [x] **UI-04** 🟡 — [static/uploads/produtos/](static/uploads/produtos/) — **Imagens enormes para miniaturas.** São 19 MB de imagens exibidas com 50–100 px
  (ex.: `heineken-original-bottle.png` com 2,3 MB, `linguica-toscana-dalia.png` com 1,9 MB). A tela de **Nova Venda baixa ~19 MB**.
  *Correção:* gerar miniaturas com Pillow (~300 px, WebP) no upload, usar `loading="lazy"` e comprimir as imagens existentes.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Cada foto ganha uma miniatura WebP de até 320 px (`imagens.py`): no upload, e para as fotos existentes em segundo plano na inicialização. As telas usam a miniatura por meio do filtro `miniatura`, com a original como alternativa. As miniaturas ficam fora do git e dos backups. *Verificado:* as imagens da tela de venda caíram de 18,8 MB para 508 KB. *Testes:* `test_ui04_*`.

- [ ] **UI-05** 🟡 — **Arquivos de imagem desnecessários.** `logo-acougue.png` tem 527 KB para ser exibido com 60–100 px.
  `Picsart_25-05-09_14-15-53-416.png` (raiz, fora do git) é **idêntico** ao logo, e `logo-acougue_.png` não é usado.
  Na pasta de uploads há imagens órfãs, que nenhum produto usa: 3× `*_OIP.jpeg`, `logo-completa.png`, `logo-nova-titulo.png`,
  `logo-simbolos.png`, `costela-suina.png` e `coxao-duro.png`.
  🟨 **Parcial (26/09/2026):** o cabeçalho e o login usam `logo-acougue-200.png` (57 KB, antes 515 KB). A cópia `Picsart_*.png` e as imagens órfãs continuam, e apagar arquivos fica a critério do usuário.

- [ ] **UI-06** 🟡 — **Listas sem paginação.** A tela de venda, os fornecedores (a paginação de `get_fornecedores` foi perdida, ver CODE-01),
  as vendas a prazo e os usuários não têm paginação. A lista de vendas a prazo cresce para sempre com as vendas pagas;
  o filtro padrão deveria ser "pendentes".

- [ ] **UI-07** 🟡 — **Formulários inconsistentes com o servidor.**
  - Preço com `min="0"` ([novo.html:37](templates/produtos/novo.html#L37)), mas o servidor exige > 0.
  - A quantidade não aceita decimais nos produtos vendidos por quilo.
  - `accept="image/*"` ([novo.html:97](templates/produtos/novo.html#L97)), mas o servidor só aceita jpg/jpeg/png, e o próprio seed usa `.webp`.
  - O filtro por letra existe no servidor (`letra`), mas não tem interface.
  🟨 **Parcial (26/09/2026):** preço mínimo, decimais e o `accept` do upload foram corrigidos; o filtro por letra continua sem interface.

- [ ] **UI-08** 🟡 — [templates/admin/usuarios.html:31-34](templates/admin/usuarios.html#L31-L34) — **Mudança de cargo sem confirmação.** Trocar o cargo
  no select já envia o formulário. A venda finalizada usa `alert()` e recarrega a página, sem comprovante ou impressão.
  🟨 **Parcial (26/09/2026):** a troca de cargo pede confirmação; a venda continua sem comprovante.

- [ ] **UI-09** 🔵 — **Acessibilidade.** Botões só com ícone não têm `aria-label` (lixeira em `admin/usuarios.html`), o status é indicado só por cor,
  e as tabelas não têm `<caption>`.
  🟨 **Parcial (26/09/2026):** os botões de ícone da gestão de usuários ganharam `aria-label`.

- [x] **UI-10** 🔵 — [templates/vendas/nova.html:13](templates/vendas/nova.html#L13) — O `<meta name="csrf-token">` está dentro do `<body>`
  (deveria estar no `{% block head %}`), e o `csrf_token` oculto dentro de `#form-venda` não é usado.
  ✅ **Corrigido em 26/09/2026.** O `<meta csrf-token>` foi para o `head`, e o input oculto que não era usado foi removido.

## 7. Desempenho (PERF)

- [x] **PERF-01** 🟠 — [app.py:229-260](app.py#L229-L260) — **O backup é pesado e acumula para sempre.**
  Ele compacta o banco e **todas** as imagens (~19 MB) a cada inicialização (2×, ver BUG-10), a cada 24h e a cada clique em "Backup Completo".
  A limpeza só remove o excesso de backups **do dia atual**, então os dias anteriores acumulam indefinidamente
  (`backups/` já tem 112 MB em 6 arquivos, 2 deles duplicados). O `ZipFile(path, 'w')` usa `ZIP_STORED`, ou seja, **sem compressão**.
  *Correção:* retenção por dias (ex.: os últimos 7 diários e 4 semanais), `ZIP_DEFLATED`, e imagens só quando mudarem.
  ✅ **Corrigido em 26/09/2026 (lote 2).** O backup do banco é comprimido (~12 KB, contra ~19 MB antes), e o zip de fotos só é criado quando alguma foto muda. Na inicialização, só faz backup se o último tiver mais de 24h. A retenção guarda tudo das últimas 24h, o último de cada um dos 7 dias e de cada uma das 4 semanas mais recentes, e os 2 últimos de fotos. O download (`/backup`) gera o zip completo na hora, sem guardar. Os `acougue_system_backup_*` antigos (112 MB) não são apagados automaticamente. *Testes:* `test_perf01_*`.

- [ ] **PERF-02** 🟡 — [app.py:1068-1133](app.py#L1068-L1133) — **O dashboard faz 7 queries, várias com varredura completa** (`DATE(data) = DATE('now')`).
  O total do dia e a quantidade de vendas são calculados 2–3× em queries diferentes. Consolidar numa query só.
  🟨 **Parcial (26/09/2026):** o total do dia é somado das vendas já carregadas (uma consulta a menos), e as consultas por data usam intervalo com índice. Ainda são 6 consultas.

- [ ] **PERF-03** 🟡 — [app.py:1286-1319](app.py#L1286-L1319) — **A verificação de validade enche a tabela `logs`.** Ela grava um WARNING por produto por dia.
  Melhor exibir os alertas no dashboard do que registrá-los como log.

- [ ] **PERF-04** 🟡 — **Muitas conexões por request.** Ex.: o caminho de erro de `novo_produto` chama `get_fornecedores` de novo, a página de logs
  abre 2 conexões e `registrar_log` abre outra. Usar uma conexão por request em `flask.g`.

- [ ] **PERF-05** 🟡 — [banco_dados.py:928-937](banco_dados.py#L928-L937) — `listar_produtos_simples` não tem `ORDER BY` (a ordem na tela de venda é arbitrária)
  e carrega todos os produtos, inclusive os sem estoque.
  🟨 **Parcial (26/09/2026):** a lista agora tem `ORDER BY nome` e só traz produtos ativos.

- [ ] **PERF-06** 🔵 — [banco_dados.py:1253](banco_dados.py#L1253) — `defaultdict` é importado dentro da função e `fetch_vendas_prazo` não tem paginação.

## 8. Testes (TEST)

- [x] **TEST-01** 🔴 — **A suíte está quebrada: 15 falhas e 7 aprovações** (*verificado* com `pytest tests/` numa cópia isolada).
  A causa principal é BUG-01.
  ✅ **Corrigido em 26/09/2026.** **80 testes passando** (`pytest tests/`). Os testes novos falham no código original (49 de 58, mesmo com o BUG-01 já corrigido), o que prova que detectam os bugs.

- [x] **TEST-02** 🟠 — [tests/testes.py](tests/testes.py) — **Este arquivo nunca roda.** O nome não segue o padrão `test_*.py`, e se rodasse falharia:
  importa `validar_cnpj`, que não existe no `app.py`. O `test_backup_criado` procura `.db`, mas os backups são `.zip`, e ainda faz um backup
  real do banco de produção. O mock de `processar_venda` usa as chaves erradas (`produto_id`/`preco_unitario` em vez de `id`/`preco`).
  ✅ **Corrigido em 26/09/2026 (lote 3).** O `tests/testes.py` foi removido; o teste de `validar_cnpj` que ele pretendia fazer agora existe e passa (`test_bug17_validar_cnpj`). *Teste:* `test_test02_*` garante que todo arquivo em `tests/` é coletado pelo pytest.

- [x] **TEST-03** 🟠 — [tests/test_integration.py:19-24](tests/test_integration.py#L19-L24) — **Um "banco em memória" que vira arquivo.**
  O teste usa `DB_PATH='testdb'` achando que é um banco em memória, mas `banco_dados` abre `file:testdb` sem `mode=memory`
  e **cria o arquivo `testdb` na raiz do projeto**: é o `testdb` que aparece como não rastreado no `git status`.
  Os dados persistem entre execuções (usernames duplicados na 2ª rodada). O `get_db_connection` local do teste abre **outro** banco,
  em memória, então o `test_update_produto_estoque` não testa o que pretende. `UPLOADER_FOLDER` tem um erro de digitação e não é usado,
  e o teste cria um usuário com o cargo `'admin'`, que o sistema não aceita.
  ✅ **Corrigido em 26/09/2026.** O `TestBase` usa uma pasta temporária e não cria mais o `testdb`. O `testdb` antigo, na raiz, pode ser apagado.

- [x] **TEST-04** 🟠 — [tests/conftest.py:6-26](tests/conftest.py#L6-L26) — **Fixture quebrada.** A fixture `app` sobrescreve o `app` importado,
  e dentro dela `app.config` passa a apontar para a própria função da fixture (AttributeError): qualquer teste que use `client` falha.
  A chave `DATABASE` é ignorada pelo `banco_dados`, e importar `app` roda `init_db()` no `acougue.db` real.
  ✅ **Corrigido em 26/09/2026.** O `conftest.py` foi reescrito: aponta o banco e a `SECRET_KEY` para valores temporários antes de importar o app, e define as fixtures `db_path`, `app` e `client`.

- [ ] **TEST-05** 🟡 — **Faltam testes de rotas HTTP**: permissões (gerente vs funcionário), CSRF, validações de venda (NEG-01/02), relatórios e PDF.
  *Sugestão:* uma fixture com banco temporário (`tmp_path`) e `create_app(test_config)`.
  🟨 **Parcial (26/09/2026):** os lotes 1 a 3 cobrem permissões, vendas, relatórios, PDF, backup, login e migrações (195 testes). O CSRF só é verificado nos testes ponta a ponta, porque a suíte o desliga.

- [ ] **TEST-06** 🔵 — `tests/acougue.db` está versionado, e os `.pyc` de `tests/__pycache__` aparecem como apagados no `git status`
  (falta commitar a remoção). O README cita `tests/popular_banco.py`, mas o arquivo está na raiz.
  🟨 **Parcial (26/09/2026):** a remoção de `tests/acougue.db` do git está preparada (lote 2); falta o commit, junto com a remoção dos `.pyc`.

## 9. Infraestrutura, dependências e repositório (INF)

- [x] **INF-01** 🟠 — [requirements.txt](requirements.txt) — **O arquivo está em UTF-16 com CRLF e cheio de pacotes desnecessários.**
  O pip lê o formato, mas o GitHub, o `diff` e o `grep` mostram lixo. São ~70 pacotes, a maioria sem uso, e alguns só para Windows
  ou desktop: pygame, moviepy, pytube, pywebview, pythonnet, clr_loader, pywin32-ctypes, pyinstaller, PyOpenGL, numpy, imageio,
  fpdf2, PyPDF2, bottle, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Flask-Login, flask-cors...
  O que é usado de fato: Flask, Flask-WTF, APScheduler, reportlab e pillow (mais o pytest para desenvolvimento).
  *Correção:* regravar em UTF-8 só com o necessário, e criar um `requirements-dev.txt` para pytest e ferramentas.
  ✅ **Corrigido em 26/09/2026 (lote 3).** O `requirements.txt` foi regravado em UTF-8, com 8 pacotes fixados nas versões testadas, e o `requirements-dev.txt` traz pytest e pyflakes. *Verificado:* num ambiente virtual novo, instalado só por esses arquivos, a suíte inteira passa (21 pacotes, contra os 66 do `.venv` antigo). *Testes:* `test_inf01_*`, que também conferem que todo import externo do código está no arquivo.

- [ ] **INF-02** 🟠 — **O repositório pesa 252 MB** (`.git`), porque o histórico ainda contém o `node_modules` e 112 MB de backups `.zip`.
  *Opcional:* limpar o histórico com `git filter-repo`. É destrutivo e reescreve os commits; combinar antes com quem tiver clones.

- [ ] **INF-03** 🟡 — **Não há configuração de produção.** O gunicorn está no requirements, mas não há ponto de entrada WSGI nem serviço configurado.
  Com vários workers do gunicorn, o APScheduler rodaria os jobs N vezes. *Correção:* waitress (Windows) ou gunicorn com 1 worker
  para o scheduler, ou os jobs num processo à parte ou no cron.

- [ ] **INF-04** 🟡 — [app.py:64](app.py#L64), [app_logging.py](app_logging.py) — **O log só sai no console.** Não há arquivo de log nem rotação,
  o `extra={'details': ...}` não é usado pelo formatter, e vários `logging.error` não têm `exc_info`.
  Também não são registrados no log: falhas de login, vendas, CRUD de produtos e fornecedores, e pagamentos de fiado.

- [ ] **INF-05** 🔵 — [README.md](README.md) — **O README está desatualizado.** A estrutura mostrada não bate com a real, a URL de clone é um placeholder,
  ele pede "Python 3.8+" mas o ambiente usa 3.12, e não explica como rodar o `popular_banco.py` nem como configurar a `SECRET_KEY`.
  Falta um `.env.example`.

- [ ] **INF-06** 🔵 — **Fins de linha e permissões misturados.** Há arquivos com CRLF e outros com LF, e `.py`, `.db` e `.png` estão com permissão de execução.
  Adicionar um `.gitattributes` (`* text=auto eol=lf`) e ajustar as permissões.

## 10. Qualidade de código (CODE)

- [x] **CODE-01** 🟠 — [banco_dados.py](banco_dados.py) — **Funções definidas mais de uma vez; a última sobrescreve as anteriores.**
  `create_user` 2× ([533](banco_dados.py#L533), [981](banco_dados.py#L981)), `get_all_users` 3× ([565](banco_dados.py#L565), [981](banco_dados.py#L981), [1203](banco_dados.py#L1203)),
  `excluir_produto` 2× ([721](banco_dados.py#L721), [1162](banco_dados.py#L1162)), `get_fornecedores` 2× ([456](banco_dados.py#L456), com paginação;
  [1180](banco_dados.py#L1180), sem), `get_all_vendas` 2× e `get_venda_items` 2×. A versão ativa de `excluir_produto` perdeu o tratamento de erro (BUG-27).
  🟨 **Parcial (26/09/2026):** a cópia morta de `excluir_produto` foi removida; as outras duplicatas continuam.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Ficou uma única definição de cada função, com o comportamento que estava em vigor (sempre a última). *Testes:* `test_code01_*`.

- [ ] **CODE-02** 🟡 — **Duas APIs de produto com comportamentos diferentes.** `create_produto`/`update_produto`/`delete_produto` (usadas só nos testes)
  e `inserir_produto`/`atualizar_produto`/`excluir_produto` (usadas pelo app) nomeiam e salvam as fotos de formas diferentes. Unificar.

- [x] **CODE-03** 🟡 — [app.py:2-56](app.py#L2-L56) — **Imports sem uso.** `json`, `shutil`, `defaultdict`, `wraps`, `send_file`, `generate_password_hash`
  e `secure_filename`, mais 6 funções do `banco_dados`. O [app_logging.py:3](app_logging.py#L3) importa `request` e depois o sobrescreve com um parâmetro.
  ✅ **Corrigido em 26/09/2026 (lote 3).** Os imports sem uso foram removidos e o `request` sobrescrito saiu do `app_logging.py`. O pyflakes não aponta mais nada. *Testes:* `test_code03_*` rodam o pyflakes (requirements-dev), que teria pegado os imports apagados do BUG-01.

- [x] **CODE-04** 🟡 — [banco_dados.py:1028](banco_dados.py#L1028), [:1028](banco_dados.py#L1028), [:1129](banco_dados.py#L1129) — **Tratamento de erro frágil.**
  Há `except:` genéricos, e `raise` sem exceção ativa em `atualizar_produto`: só funciona por acidente, porque o `RuntimeError` gerado
  cai no `except:` genérico.
  ✅ **Corrigido em 26/09/2026 (lote 2).** A validação do produto foi reescrita em `_ler_numeros_produto`, e `parse_date` captura só `TypeError` e `ValueError`. Não resta nenhum `except:` genérico no código; os `raise` que sobraram relançam a exceção dentro de blocos `except`.
- [ ] **CODE-05** 🟡 — **Tudo num arquivo só, sem camadas.** Há SQL dentro das rotas (`dashboard`, `editar_usuario`, `excluir_usuario`, `visualizar_logs`, relatórios),
  `init_db()` roda na importação ([app.py:121](app.py#L121)) e as rotas estão todas no `app.py`.
  *Sugestão:* app factory (`create_app`) com blueprints (auth, produtos, fornecedores, vendas, relatórios, admin) e uma camada de serviço.

- [ ] **CODE-06** 🟡 — **A validação é manual e inconsistente.** O Flask-WTF está instalado, mas só é usado para CSRF. Usar `FlaskForm` com validadores.

- [ ] **CODE-07** 🔵 — [app.py:106-119](app.py#L106-L119) — **Dois limites de upload.** `MAX_FILE_SIZE_MB = 2` e `MAX_CONTENT_LENGTH = 3 MB` coexistem,
  e o erro 413 (arquivo grande demais) não tem handler, então aparece a página crua do Werkzeug.

- [ ] **CODE-08** 🔵 — **Comentários de rascunho no código**, como "NOVO CAMPO", "Assuming you have this decorator",
  "Adicione esta função no banco_dados.py" e "Within init_db() function, replace...".

- [ ] **CODE-09** 🔵 — [app.py:1234-1241](app.py#L1234-L1241) — O filtro `format_currency` é registrado 2×, e o `gerador_pdf.py` tem uma cópia própria dele.

- [ ] **CODE-10** 🔵 — **Valores mágicos espalhados pelo código.** Cargos, status e métodos de pagamento aparecem como strings soltas,
  assim como `per_page`, "30 dias" e "24h". Centralizar em constantes ou `Enum`.

---

## Observações sobre os dados atuais (`acougue.db`)

Registrado para quem for migrar ou limpar os dados:

- Há **categorias misturadas**: `Bovino` e `BOI` para o mesmo tipo de carne (BUG-14).
- Os **métodos de pagamento** aparecem como `dinheiro`, `Dinheiro`, `PIX` e `pagamento_prazo` (NEG-07).
- Há **estoques fracionados** numa coluna INTEGER, ex.: 91.6 e 18.235 (NEG-05).
- Há **totais com 3 casas decimais**, ex.: 96.998 e 13.008 (NEG-06).
- As **datas estão em formatos diferentes**: `2025-05-14 16:12:02.682109` e `2025-05-29` (BUG-20).
- A **venda do seed** tem total R$ 199,90, mas seus itens somam R$ 249,90 ([popular_banco.py:142-148](popular_banco.py#L142-L148)).
- Na tabela **`logs`**, 108 dos 109 registros são `alerta_validade` repetidos (BUG-10, PERF-03).
- Há **fotos com dois formatos de caminho** (BUG-03).

## Histórico

| Data | Commit base | Resumo |
|---|---|---|
| 26/09/2026 | `cb51f21` | Revisão inicial completa: 104 itens registrados. Nenhuma correção aplicada ainda. |
| 26/09/2026 | `cb51f21` + alterações não commitadas | **Correção dos 12 críticos** (BUG-01 a BUG-06, NEG-01 a NEG-03, SEC-01, SEC-02, TEST-01) e de 11 itens vizinhos que estavam nas mesmas linhas (BUG-09 a BUG-13, BUG-25, BUG-27, SEC-08, TEST-03, TEST-04, UI-10). Mais 4 itens parciais: NEG-04, NEG-06, CODE-01 e PERF-05. Novo item: BUG-28. |
| 26/09/2026 | `cb51f21` + alterações não commitadas | **Lote 2:** BUG-07, BUG-08, NEG-07, REL-03, SEC-05, BUG-14, NEG-12, SEC-03, REL-02, NEG-05, NEG-06, BUG-19, UI-01 e PERF-01, mais os vizinhos BUG-15, BUG-16, BUG-18, BUG-21, BUG-24, BUG-28, NEG-04 (restante) e SEC-11. Também CODE-04. Parciais: DB-01, NEG-09, REL-05, SEC-09, UI-07, UI-08 e UI-09. Novo item: BUG-29 (corrigido). |
| 26/09/2026 | `cb51f21` + alterações não commitadas | **Lote 3:** BUG-17, BUG-20, BUG-26, NEG-10, NEG-11, REL-01, REL-07, SEC-04, SEC-06, INF-01, UI-04, DB-02, CODE-01, CODE-03 e TEST-02. Parciais: UI-05, PERF-02, TEST-05 e TEST-06. Novo item: BUG-30 (corrigido). |

### Detalhes da correção de 26/09/2026

**Arquivos alterados:** `app.py`, `banco_dados.py`, `app_logging.py`, `gerador_pdf.py`, `popular_banco.py`, `templates/index.html`,
`templates/logs.html` (reescrito), `templates/vendas/nova.html` (reescrito), `templates/produtos/listar.html`, `templates/produtos/editar.html`,
`templates/admin/estoque.html` (novo), `tests/conftest.py` (reescrito), `tests/test_integration.py` e `tests/test_criticos.py` (novo, com 58 testes).

**Efeitos que o usuário vai notar:**
- **Migração automática do banco na primeira execução.** Antes de alterar qualquer coisa, o sistema salva uma cópia em
  `backups/acougue_pre_migracao_v0_<data>.db`. Testado numa cópia do `acougue.db` real: nenhuma linha perdida, a soma dos totais de venda
  ficou igual e não há violação de chave estrangeira.
- **Todos precisam entrar de novo uma vez,** porque a chave da sessão mudou (SEC-01). A chave nova fica em `instance/secret_key`.
- **O preço vem do cadastro do produto,** inclusive o R$/kg (NEG-01). Um produto com preço zerado não pode ser vendido até o gerente cadastrar o preço.
- **"Excluir" um usuário ou produto que tem vendas passa a desativá-lo,** e o histórico é mantido (NEG-03).
- **O modo debug só liga com `FLASK_DEBUG=1`** (SEC-02).

**Como foi verificado:**
1. `pytest tests/` passa com 80 testes. A execução não altera o `acougue.db` (o hash foi conferido) nem cria arquivos no repositório.
2. Os testes novos, rodados contra o código original, falham: 55 de 58. Com só o BUG-01 corrigido, 49 continuam falhando,
   o que mostra que cada teste detecta o próprio bug. Os que passam no original são os do próprio BUG-01, a página 404
   (o problema só aparecia rodando `python app.py`, e foi verificado no passo 3) e dois de SEC-01 que dependem do ambiente.
3. Teste ponta a ponta com o servidor real (`python app.py`), numa cópia do projeto e do banco real, passando por HTTP com login e CSRF:
   28 de 28 verificações OK. Foram cobertos a migração, a chave de sessão, a página 404 e o erro 500 sem debugger, o cadastro de usuário e de produto com foto,
   todas as imagens das telas, as páginas de estoque e de logs, a venda com preço adulterado, quantidade negativa e estoque insuficiente,
   a exclusão de usuário e de produto com vendas, e o scheduler subindo uma única vez com `FLASK_DEBUG=1`.

### Detalhes do lote 2 (26/09/2026)

**Decisão do usuário:** restaurar pela migração as categorias que o BUG-14 tinha trocado, usando o cadastro original (`popular_banco.py`) como referência.

**Arquivos alterados:** `app.py`, `banco_dados.py`, `decorators.py`, `gerador_pdf.py`, `static/styles.css`, `.gitignore`, `README.md`,
os templates `base.html`, `index.html`, `dashboard.html`, `relatorio_unificado.html`, `relatorios/dashboard.html`, `produtos/novo.html` e
`produtos/editar.html` (ambos reescritos), `produtos/listar.html`, `admin/usuarios.html`, `vendas/nova.html` e `vendas/listar_vendas_prazo.html`.
Arquivos novos: `errors/403.html`, `conta/senha.html` e `produtos/_passo_quantidade.html`. Removido: `flash_messages.html`.
Testes: `tests/test_lote2.py` (novo, com 59 testes) e ajustes em `conftest.py` e `test_criticos.py`.
No git, a remoção de `acougue.db` e `tests/acougue.db` está preparada (`git rm --cached`) e os arquivos continuam no disco.

**Efeitos que o usuário vai notar:**
- **Migração 2 automática** na primeira execução, com backup antes, como na 1. Ela:
  - troca as quantidades para decimais;
  - cria a data de pagamento;
  - padroniza as formas de pagamento;
  - arredonda os valores em centavos;
  - restaura as categorias;
  - limpa os textos "None".
- **O `admin` do banco real ainda usa a senha `admin123`,** então o sistema vai pedir uma senha nova no primeiro acesso.
- **O funcionário deixa de ver Produtos, Fornecedores e Vendas a Prazo,** e o acesso direto mostra "Acesso restrito" sem deslogar.
- **Os backups novos são pequenos (banco ~12 KB) e ficam sob retenção.** Os 6 arquivos `acougue_system_backup_*` antigos (112 MB) podem ser apagados manualmente.

**Como foi verificado:**
1. `pytest tests/` passa com 139 testes, e a execução não altera o `acougue.db` (o hash foi conferido).
2. Os testes novos, rodados contra o código de antes do lote, falham: 54 de 59. Os 5 que passam cobrem casos em que o comportamento antigo já estava certo.
3. Teste ponta a ponta com o servidor real, numa cópia do projeto e do banco real, com migração v0 → v2 sobre os dados de verdade:
   36 de 36 verificações OK. Isso inclui a troca obrigatória da senha real `admin123`, a quitação de um fiado real, o rebaixamento
   com duas sessões abertas e o reinício sem novo backup.
4. Verificação visual com capturas de tela no Chrome headless de 13 telas. Foi ela que revelou que `.btn-primary`, `.btn-danger` e `.badge-estoque`
   nunca tinham tido estilo (sintaxe Sass descartada pelo navegador), e o teste do UI-01 foi reforçado para pegar esse caso.

### Detalhes do lote 3 (26/09/2026)

**Arquivos alterados:** `app.py`, `banco_dados.py`, `app_logging.py`, `gerador_pdf.py`, `static/styles.css`, `.gitignore`, `README.md`,
`requirements.txt` (regravado em UTF-8) e os templates `base.html`, `login.html`, `dashboard.html`, `relatorio_unificado.html`,
`produtos/listar.html`, `produtos/editar.html`, `vendas/nova.html`, `vendas/listar_vendas_prazo.html`, `admin/estoque.html`,
`fornecedores/novo.html` e `fornecedores/editar.html` (os dois reescritos).
Arquivos novos: `imagens.py`, `requirements-dev.txt`, `templates/fornecedores/_form.html`, `static/img/logo-acougue-200.png` e `tests/test_lote3.py` (57 testes).
Removido: `tests/testes.py` (`git rm`).

**Efeitos que o usuário vai notar:**
- **Migração 3 automática,** com backup antes: converte os logs antigos para a hora local e ajusta o trigger. Os índices são criados em seguida.
- **Na primeira execução,** as miniaturas das fotos são geradas em segundo plano (pasta `static/uploads/produtos/miniaturas/`, fora do git).
- **O login bloqueia por 15 minutos** depois de 5 senhas erradas no mesmo usuário (ou 20 no mesmo IP), e a sessão expira em 12h.
- **Fornecedor novo precisa de CNPJ válido;** os fornecedores existentes continuam editáveis com o CNPJ que já tinham.
- **As vendas de hoje guardam a hora,** e o dashboard não zera mais depois das 21h.
- **Para instalar em outra máquina:** `pip install -r requirements.txt` (8 pacotes). Para os testes: `requirements-dev.txt`.

**Como foi verificado:**
1. **Suíte:** 189 testes passam no `.venv` do projeto, mais 7 do pyflakes, que ficam pulados porque esse ambiente não tem `pip`. Num ambiente virtual novo, instalado só pelo `requirements-dev.txt`, são 195 testes passando.
2. **Os testes detectam os bugs:** os testes novos falham no código de antes do lote, 41 de 50. Os 9 que passam protegem contra excesso de correção (campo ausente mantém o valor, bloqueio por usuário não trava os outros).
3. **Servidor real:** numa cópia do projeto e do banco real, com migração v0 → v3, deu 20 de 20 verificações OK. Isso inclui o bloqueio na 6ª senha errada, o fornecedor real salvo duas vezes sem alteração, a venda com hora no dashboard e as imagens da tela de venda caindo de 18,8 MB para 508 KB.
4. **Capturas de tela** de 10 telas. Elas mostraram que o alinhamento à direita das colunas numéricas não era aplicado (a regra `.table td` vencia), além do "23.933 kg" quebrando a linha, e os dois foram corrigidos.

