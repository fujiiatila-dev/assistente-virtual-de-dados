# ADR-004: Descoberta dinâmica de schema

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O enunciado exige que o sistema "entenda a estrutura do banco (schema) dinamicamente" e
proíbe queries hardcoded. O banco de avaliação tem 4 tabelas conhecidas, mas o sistema
precisa funcionar se as tabelas, colunas ou o próprio arquivo mudarem — essa é uma
explicitamente avaliada.

Alternativas consideradas:

1. **Schema embutido no prompt (hardcoded)** — simples, mas viola diretamente o requisito
   de Descoberta; reprovatório.
2. **Introspecção em runtime a cada pergunta** — consulta `sqlite_master` + `PRAGMA
   table_info` para montar o schema no momento da pergunta; custo mínimo (SQLite local),
   sempre atualizado.
3. **RAG sobre o schema** — embeddings de tabelas/colunas; útil para dezenas/centenas de
   tabelas, overkill para 4 tabelas e adiciona latência e custo.

## Decisão

**Introspecção em runtime** no início de cada execução do grafo (nó `descobrir_schema`):

- `sqlite_master` para listar tabelas e views;
- `PRAGMA table_info(<tabela>)` para colunas, tipos e flags (PK, not null);
- `PRAGMA foreign_key_list(<tabela>)` para relações entre tabelas;
- amostragem leve de dados (primeiras linhas de colunas categóricas de baixa cardinalidade,
  ex.: `canal`, `categoria`, `tipo_contato`) para dar ao LLM os **valores válidos** —
  informação crítica para filtrar corretamente sem inventar valores.

O resultado é serializado em DSL textual compacta e injetado no prompt do nó gerador.
Cardinalidades amostradas com `SELECT DISTINCT ... LIMIT` e cacheadas por sessão.

## Consequências

**Positivas**
- Atende literalmente ao requisito de descoberta; funciona com qualquer banco SQLite.
- Valores de exemplo de colunas categóricas reduzem alucinação de filtros (`canal = 'app'`
  vs `'Aplicativo'`) — fonte comum de erro em text-to-SQL.
- Custo desprezível comparado a RAG.

**Negativas / Riscos**
- Amostragem de valores pode ser imprecisa em colunas de alta cardinalidade — mitigado
  limitando a amostragem a colunas TEXT com cardinalidade estimada baixa.
- Se o banco crescer para muitas tabelas, será preciso evoluir para seleção de tabelas
  relevantes (não é escopo do desafio; registrado em "melhorias" do README).
