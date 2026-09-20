# ADR-204: Orquestração idempotente com state store

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

O pipeline processa milhares de documentos por execução. Falhas são esperadas: PDF
corrompido, rate limit da API, crash do worker, rede instável. Requisitos afetados:
**robustez** (um anômalo não pode derrubar o lote) e **reprodutibilidade** (reexecutar
produz resultados consistentes). A pergunta de orquestração: usar um framework pesado
(Airflow, Temporal) ou orquestração própria leve?

Alternativas consideradas:

1. **Script sequencial com for** — falha em qualquer erro; reexecução refaz tudo
   (custo dobrado); sem visibilidade de status.
2. **Airflow/Dagster** — robustos, mas operacionalmente pesados para o escopo do desafio
   (infra, UI, agendador); overkill para um pipeline linear de 5 estágios.
3. **Orquestração própria com state store local** — cada documento é um job com estado
   persistido por estágio; workers paralelos consomem a fila.

## Decisão

**Orquestração própria enxuta sobre um state store** (SQLite em produção local; a
interface permite trocar por Postgres/Redis):

- **Documento = job.** Chave de idempotência: `SHA-256(conteúdo do arquivo)` — o mesmo
  arquivo reprocessado não gera trabalho novo; mudou o arquivo, é job novo.
- **Estados por estágio:** `ingested → ir_ready → classified → extracted → validated →
  persisted`, mais `review_queue`, `failed`, `superseded`. Cada transição grava também
  `model_id`, `prompt_version`, `code_version`, timestamps e custo acumulado.
- **Workers paralelos** com pool configurável; retentativa com backoff para erros
  transientes (rate limit), sem retentar erros permanentes (PDF corrompido → `failed`
  com motivo estruturado).
- **Checkpoint por estágio:** crash no meio do lote não refaz estágios concluídos —
  reiniciar o comando retoma de onde parou (base da reprodutibilidade).
- **Sem agendador embutido:** o modo batch é um comando; o modo online é um worker
  long-running (ver ADR-205).

## Consequências

**Positivas**
- Reprocessamento seletivo: trocou o prompt de extração → reprocessar só `ir_ready`/`classified`.
- Falha isolada por documento; o lote segue (robustez).
- Estado consultável responde "onde está o doc X?" sem ferramenta externa.

**Negativas / Riscos**
- Orquestração própria exige disciplina (transações de estado, backoff) — volume de código
  moderado, mas sob controle por ser pipeline linear sem paralelismo entre estágios.
- Se a escala exigir múltiplas máquinas, o state store migra para Postgres — a abstração
  existe justamente para isso; discutir na entrevista como evolução.
