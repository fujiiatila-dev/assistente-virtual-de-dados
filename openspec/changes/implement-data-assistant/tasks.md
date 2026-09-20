# Tasks: implement-data-assistant

Instruções para o modelo implementador:

- Trabalhe as tasks em ordem; cada uma é verificável por comando.
- NÃO invente schema: a introspecção (T2) é a única fonte de verdade do motor.
- O `anexo_desafio_1.db` é uma dependência local de integração e não deve ser versionado.
- Fixtures mínimos podem ser criados em diretórios temporários pelos testes; não crie um
  banco sintético permanente para substituir o anexo oficial.
- NÃO comite segredos; `.env` está no `.gitignore` (T1 cria).
- Ao final de cada task, rode o comando de verificação indicado.
- Cada item abaixo deve caber em no máximo duas horas; se surgir escopo extra, registre
  uma nova task antes de continuar.

## 0. Pré-execução, Git e contrato do dataset

- [ ] **T0a.** Confirmar que o diretório de implementação é
  `assistente-virtual-dados-desafio-1/`, com Git inicializado na branch `main`. Criar ou
  revisar `.gitignore` para excluir `.env`, `*.db`, `.venv/`, caches, artefatos PNG/CSV e
  segredos; versionar apenas `.env.example`. Definir o fluxo de branch por task
  (`feat/tN-nome`), commit convencional, verificação e merge em `main`. **Verificar:**
  `git status --short --branch` e `git check-ignore .env anexo_desafio_1.db`.

- [ ] **T0b.** Confirmar o ambiente (`python --version` e `uv --version`) e, se necessário,
  instalar o uv antes de iniciar T1. Criar `scripts/validate_dataset.py`, somente leitura,
  aceitando `--db` e
  validando: SQLite legível, tabelas `clientes`, `compras`, `suporte` e
  `campanhas_marketing`; colunas mínimas do enunciado; chaves estrangeiras sem órfãos;
  contagens e intervalo de datas em relatório. O script deve tolerar colunas extras,
  reportar como WARNING a divergência dos campos denormalizados de `clientes` em relação
  a `compras` e nunca criar, alterar ou copiar o banco. Registrar no README que o anexo oficial não é
  versionado. **Verificar:** `python scripts/validate_dataset.py --db ..\\anexo_desafio_1.db`.

## 1. Fundações

- [ ] **T1.** Scaffolding do projeto: `pyproject.toml` (uv, Python 3.11+), deps
  `langgraph`, `langchain-openai`, `sqlglot`, `pydantic`, `streamlit`, `pytest`,
  `python-dotenv`, `plotly`, `kaleido`; dev: `ruff`, `mypy`; `src/data_assistant/` + `tests/`;
  `scripts/`; `.env.example` (`OPENROUTER_API_KEY=`,
  `OPENROUTER_MODEL=google/gemini-2.5-flash`, `DB_PATH=../anexo_desafio_1.db`,
  `MAX_SQL_FIX_ATTEMPTS=3`, `MAX_QUERY_BUDGET=6`); `.gitignore` com `.env` e `*.db`;
  configuração de marker `llm` no pytest. **Verificar:**
  `uv sync && uv run python -c "import data_assistant"`.

- [ ] **T2.** `schema.py`: introspecção (`sqlite_master`, `PRAGMA table_info`,
  `PRAGMA foreign_key_list`) + amostragem de colunas TEXT de baixa cardinalidade
  (`SELECT DISTINCT ... LIMIT 20`) + serialização em DSL textual + cache por sessão.
  O código deve refletir colunas extras do anexo sem lista fixa. **Verificar:**
  `uv run pytest tests/test_schema.py` (usar DB fixture criado em teste).

- [ ] **T3.** `executor.py`: abertura `file:...?mode=ro`, ativação de `PRAGMA query_only=ON`
  e `PRAGMA foreign_keys=ON`, execução com injeção segura de `LIMIT` (200), timeout por
  query, retorno `list[dict]` ou exceção com mensagem original do SQLite. Cobrir caminho
  relativo/absoluto no Windows. **Verificar:**
  `uv run pytest tests/test_executor.py` (inclui escrita rejeitada, limite e timeout).

- [ ] **T4.** `validator.py`: sqlglot com dialect SQLite — whitelist `SELECT`/`WITH`,
  rejeição de múltiplos statements, blocklist (`PRAGMA`, `ATTACH`, `load_extension`)
  e rejeição de escrita. A detecção de múltiplos statements não deve quebrar strings
  literais que contenham `;`. **Verificar:** `uv run pytest tests/test_validator.py`
  (ataques, CTEs válidas, strings com pontuação e falsos positivos).

## 2. Motor LangGraph

- [ ] **T5.** `llm.py`: client compatível OpenAI apontando ao OpenRouter
  (`base_url` configurável); helpers de chamada com temperature baixa (0), timeout e
  retries. Criar `scripts/smoke_llm.py`, que falha claramente sem chave e não imprime a
  chave. **Verificar:** `uv run python scripts/smoke_llm.py` com chave configurada;
  sem chave, confirmar mensagem operacional e exit code documentado.

- [ ] **T6.** `contract.py` e `visualization.py`: modelos Pydantic `Visualization` e
  `AssistantAnswer` com `status`, `warnings` e `available_types`; validação das colunas
  referenciadas no resultado; seleção de opções compatíveis e fallback determinístico
  para `table`. **Verificar:** `uv run pytest tests/test_contract.py`.

- [ ] **T7.** `prompts.py`: prompts de interpretar, gerar SQL (com schema + valores
  categóricos + `format_hint`), corrigir (com erro real), avaliar suficiência e formatar
  (com cardápio de visuais). Incluir instruções para mês sem ano, contagem distinta de
  clientes e média por cliente; proibir invenção de tabelas/colunas e orientar resposta
  honesta para resultado vazio. **Verificar:** `uv run pytest tests/test_prompts.py`
  validando presença das restrições e exemplos nos prompts.

- [ ] **T8a.** `graph.py`: definir `AgentState` (design.md) e implementar os nós como
  funções puras, com trilha `steps` populada a cada nó. **Verificar:**
  `uv run pytest tests/test_graph_nodes.py -k nodes` (LLM/executor mockados).

- [ ] **T8b.** Montar o grafo LangGraph e suas arestas condicionais (correção ≤3,
  orçamento 6, suficiência). Definir claramente que o limite de correção conta somente
  novas tentativas após a query inicial. **Verificar:**
  `uv run pytest tests/test_graph_nodes.py` (cada aresta, resultado vazio e orçamento
  esgotado).

- [ ] **T9.** Orquestrador de alto nível `assistant.py`: `ask(question, format_hint)
  -> AssistantAnswer`, resolução `DB` > `DB_PATH` > `../anexo_desafio_1.db`, execução do
  grafo e contrato validado. **Verificar:** `uv run pytest tests/test_assistant.py`.

## 3. Aceitação determinística do anexo

- [ ] **T10.** Criar testes de integração sem LLM real contra `DB_PATH`, usando o anexo
  oficial quando disponível,
  usando respostas de LLM mockadas apenas para exercitar o motor e comparando os
  resultados com os valores de referência do `design.md`: maio/App; 33 clientes
  distintos em WhatsApp/2024; ranking de médias; 19/18/14 reclamações não resolvidas
  por canal (filtrando `tipo_contato = Reclamação`);
  série mensal por canal. Os testes devem pular com mensagem clara se o anexo não
  estiver disponível, sem mascarar falhas de código. **Verificar:**
  `uv run pytest tests/test_reference_dataset.py`.

## 4. Frontend

- [ ] **T11a.** `app.py` (Streamlit): shell de chat com `st.session_state`, as 5 perguntas
  do enunciado clicáveis, spinner por etapa, status do banco e mensagem operacional para
  banco ausente. Todo texto da interface deve estar em `pt-BR`. **Verificar:**
  `streamlit run app.py` e checklist de interação básica.

- [ ] **T11b.** Implementar painel de etapas e queries (sem expor chain-of-thought
  privado) e renderização por contrato (`line`/`bar`/`table`/`metric`) com fallback
  `table`. **Verificar:** `streamlit run app.py` e checklist manual das 5 perguntas
  usando o anexo.

- [ ] **T11c.** Implementar seletor de visualização sem nova consulta, tema `System`/
  `Light`/`Dark`, exportação de tabela para CSV/PNG e exportação dos demais visuais para
  PNG via Plotly/Kaleido. Cobrir renderer indisponível com erro operacional sem quebrar
  a resposta. **Verificar:** `uv run pytest tests/test_visualization.py` e checklist
  manual de exportação.

- [ ] **T12.** Header `?DB=...` opcional para apontar outro SQLite em runtime, com a
  mesma validação, prioridade sobre `DB_PATH` e abertura somente leitura. **Verificar:**
  executar com uma cópia temporária renomeada e confirmar que o schema é redescoberto;
  confirmar que caminho inválido gera erro operacional sem criar arquivo.

## 5. Integração LLM, documentação e entrega

- [ ] **T13.** Testes de integração end-to-end com LLM real (marcados `@pytest.mark.llm`,
  skip se `OPENROUTER_API_KEY` ausente) cobrindo as 5 perguntas do enunciado. Validar
  forma da resposta, visualização, queries somente leitura e ausência de stack trace;
  valores exatos ficam vinculados ao anexo usado no teste. **Verificar:**
  `uv run pytest -m llm` com chave configurada.

- [ ] **T14.** `README.md` (PT) + `README.en.md`: configuração, localização do anexo
  não versionado, validação do dataset, execução, arquitetura (grafo + ADRs), frontend
  Material 3, temas, visualizações e exportações, exemplos testados com resultados do
  anexo, limites conhecidos e melhorias futuras. Incluir aviso de que o Desafio 2 é
  somente arquitetura; não documentar `anexo_desafio_2.zip` como entrada do app.
  **Verificar:** revisão humana e execução dos comandos copiados do README em ambiente
  limpo.

- [ ] **T15.** Qualidade e fechamento: `uv run pytest`, `uv run ruff check .`,
  `uv run mypy src/` e `openspec validate --changes` limpos; verificar que nenhum `.env`,
  banco ou segredo está rastreado; atualizar badges e a seção de resultado do
  `HANDOFF.md`. O merge final deve ocorrer em `main`, sem `.env`, bancos ou segredos no
  histórico. **Verificar:** executar todos os quatro comandos e registrar os
  resultados no handoff.
