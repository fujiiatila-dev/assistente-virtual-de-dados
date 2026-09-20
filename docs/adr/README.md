# Architecture Decision Records

Decisões de arquitetura do **Assistente Virtual de Dados** (Desafio Técnico 1 — Engenheiro(a) de IA Pleno).

Formato: [MADR](https://adr.github.io/madr/) simplificado — Contexto → Decisão → Consequências.

| ADR | Título | Status |
|-----|--------|--------|
| [ADR-001](adr-001-langgraph-orchestration.md) | LangGraph como orquestrador do agente | Aceito |
| [ADR-002](adr-002-llm-provider-portability.md) | Provedor LLM via OpenRouter com portabilidade | Aceito |
| [ADR-003](adr-003-sql-guardrails.md) | Guardrails e execução segura de SQL | Aceito |
| [ADR-004](adr-004-dynamic-schema-discovery.md) | Descoberta dinâmica de schema | Aceito |
| [ADR-005](adr-005-sql-self-correction-loop.md) | Loop de auto-correção de SQL | Aceito |
| [ADR-006](adr-006-model-directed-visualization.md) | Visualização dirigida pelo modelo com fallback | Aceito |
| [ADR-007](adr-007-streamlit-frontend.md) | Streamlit como frontend | Aceito |
| [ADR-008](adr-008-frontend-rendering-and-export.md) | Material 3, Plotly e exportação de resultados | Aceito |

## Série 2xx — Desafio Técnico 2 (arquitetura de referência)

Os ADRs do **Pipeline de Documentos** (Desafio 2, não implementado — foco da entrevista
técnica) vivem em [`docs/desafio-2-pipeline/`](../desafio-2-pipeline/README.md), junto do
documento de arquitetura de referência.

## Mudanças futuras

Novos ADRs devem ser numerados sequencialmente e nunca editados após aceitos — correções
viram um novo ADR que supersedea o anterior.
