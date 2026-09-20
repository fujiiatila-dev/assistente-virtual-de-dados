# Prompt do modelo implementador

Você é o modelo responsável por implementar o **Desafio Técnico 1 — Assistente
Virtual de Dados** neste repositório.

## Contexto e objetivo

Trabalhe exclusivamente dentro de `assistente-virtual-dados-desafio-1/`, que é um
repositório Git independente. Implemente um agente capaz de receber perguntas de
negócio em linguagem natural, descobrir dinamicamente o schema de um SQLite, gerar e
validar SQL somente leitura, corrigir erros de SQL de forma limitada e apresentar o
resultado em um frontend Streamlit em `pt-BR`.

Implemente somente o Desafio 1. Não escreva código para `docs/desafio-2-pipeline/`.
Esse diretório é material de referência arquitetural para a entrevista.

## Leitura obrigatória antes de codificar

Leia integralmente, nesta ordem:

1. `openspec/config.yaml`;
2. `openspec/changes/implement-data-assistant/proposal.md`;
3. `openspec/changes/implement-data-assistant/specs/data-assistant/spec.md`;
4. `openspec/changes/implement-data-assistant/design.md`;
5. `openspec/changes/implement-data-assistant/tasks.md`;
6. todos os ADRs `docs/adr/adr-001` até `docs/adr/adr-008`;
7. `HANDOFF.md`.

Esses arquivos são a fonte de verdade. Não redecida a arquitetura já aprovada.
Se surgir um desvio necessário, pare a implementação daquela decisão e registre o
motivo, impacto e alternativa em `docs/notes/deviations.md` para revisão humana.

## Git e segurança operacional

- A branch permanente é `main`; nunca codifique diretamente nela.
- Antes de cada task, crie uma branch a partir de `main`: `feat/tN-nome` para feature
  ou `fix/tN-nome` para correção.
- Execute a task em ordem, rode seu comando de verificação, faça um commit
  Conventional Commits e só depois faça merge da branch em `main`.
- Após o merge validado, remova a branch local da task. Não avance se a verificação
  falhar.
- Nunca use `git reset --hard`, `git checkout --` ou outra operação destrutiva para
  apagar trabalho existente.
- O arquivo `.env` na raiz pode conter credenciais locais e nunca pode ser rastreado.
  Versione apenas `.env.example`.
- Nunca versione bancos SQLite (`*.db`, `*.sqlite` e arquivos WAL/journal), chaves,
  tokens, logs, CSVs, PNGs exportados, caches ou relatórios locais.
- Antes do merge final, confira `git status`, `git ls-files` e o histórico para provar
  que nenhum segredo, banco ou artefato proibido foi commitado.

## Stack obrigatória

- Python 3.11+ e `uv`;
- LangGraph para orquestração;
- LangChain/OpenAI-compatible client via OpenRouter;
- modelo padrão `google/gemini-2.5-flash`, configurável por `OPENROUTER_MODEL`;
- SQLite via `sqlite3`, `sqlglot`, Pydantic e `python-dotenv`;
- Streamlit com componentes nativos, linguagem `pt-BR` e linguagem visual Material 3;
- Plotly e Kaleido para gráficos e PNG;
- Pytest, Ruff e Mypy.

O acesso à API deve usar `OPENROUTER_API_KEY` exclusivamente pelo ambiente. Testes
unitários não chamam a API. Testes reais de LLM devem usar o marker `llm` e pular com
mensagem clara se a chave não estiver configurada.

## Dados e regras de consulta

O anexo local de referência fica em `../anexo_desafio_1.db` durante o desenvolvimento.
Ele não pertence ao repositório. O script `scripts/validate_dataset.py` deve aceitá-lo
por `--db`, operar somente em leitura e reportar tabelas, colunas, chaves estrangeiras,
contagens, intervalo de datas e colunas extras.

O motor deve:

- abrir o SQLite com URI `mode=ro`;
- ativar `PRAGMA query_only=ON` e `PRAGMA foreign_keys=ON`;
- aceitar apenas `SELECT`/`WITH`, rejeitando escrita, múltiplos statements,
  `PRAGMA`, `ATTACH` e `load_extension`;
- aplicar `LIMIT` padrão 200, timeout e orçamento máximo de 6 queries;
- permitir no máximo 3 novas tentativas de correção após a query inicial;
- descobrir o schema em runtime, incluindo colunas extras, sem schema hardcoded;
- usar `compras` como fonte de verdade para métricas operacionais quando os campos
  denormalizados de `clientes` divergirem;
- filtrar reclamações não resolvidas com `tipo_contato = 'Reclamação'`.

## Comportamento do agente e frontend

Implemente o grafo LangGraph e os contratos Pydantic descritos no design, com trilha
de etapas, queries executadas e resultados intermediários. Não exponha chain-of-thought
privado: mostre somente um painel operacional resumido.

O contrato de resposta deve conter `status`, `warnings` e `available_types`, além dos
dados e da visualização. Os tipos são `table`, `bar`, `line` e `metric`, com fallback
determinístico para `table`. O usuário pode trocar o tipo disponível sem refazer a
consulta.

O Streamlit deve oferecer:

- shell de chat e as cinco perguntas do enunciado como atalhos;
- status operacional do banco e erro amigável quando ele estiver ausente;
- tema `System` como padrão, com opções `Light` e `Dark`;
- tabela exportável para CSV e PNG;
- outros gráficos exportáveis para PNG;
- tratamento operacional quando o renderer PNG não estiver disponível;
- suporte opcional a `?DB=...`, com prioridade sobre `DB_PATH`, mesma validação e
  abertura somente leitura.

## Ordem de execução

Execute rigorosamente `T0a`, `T0b`, `T1` ... `T15` de
`openspec/changes/implement-data-assistant/tasks.md`. Cada item possui seu comando de
verificação. Marque `- [x]` somente depois que a verificação passar e depois faça o
commit e merge previstos.

Os critérios de aceite incluem as cinco perguntas do enunciado, os valores de referência
do anexo, descoberta de schema sem lista fixa, rejeição de SQL inseguro, autocorreção
limitada, fallback de visualização, painel operacional, temas, exportações e suite limpa:

```text
python scripts/validate_dataset.py --db ..\anexo_desafio_1.db
uv run pytest
uv run ruff check .
uv run mypy src/
openspec validate --changes
```

No encerramento, deixe todas as tasks concluídas, `main` atualizada, branches de task
integradas/removidas e um parágrafo `Resultado da execução` em `HANDOFF.md` contendo
tasks, desvios, cobertura, commits/merges e instruções de reprodução. Se qualquer
critério não puder ser comprovado, não declare o projeto concluído: registre o bloqueio
com evidência e aguarde revisão.
