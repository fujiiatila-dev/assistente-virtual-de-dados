# ADR-206: Persistência como contrato versionado

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

O enunciado aceita "arquivo JSON consolidado, CSV ou banco de dados" e o destino é o
ERP. A escolha define como o ERP integra, como se audita e como o pipeline evolui sem
quebrar consumidores.

Alternativas consideradas:

1. **Só JSON consolidado único** — simples, mas o ERP precisa ler o arquivo inteiro para
   achar um documento; sem status por documento.
2. **Só banco de dados (Postgres)** — ideal em produção, mas adiciona infraestrutura ao
   desafio cujo avaliador precisa executar.
3. **JSON consolidado + CSV por tipo, com contrato versionado e caminho de upgrade para DB.**

## Decisão

**Persistência em duas camadas, com contrato explícito:**

1. **State store** (ADR-204) como fonte de verdade operacional: status por documento,
   IR, tentativas, custos — não é o dado de negócio, é o chão de fábrica.
2. **Artefatos de saída por execução:** `out/<run_id>/documents.jsonl` (um JSON por
   linha, consolidado) + `out/<run_id>/<tipo>.csv` (visão tabular por tipo para carga
   simples no ERP) + `out/<run_id>/manifest.json` (resumo da run: versões, contagens,
   custo).

Cada registro de saída carrega o envelope de reprodutibilidade:

```json
{
  "document_id": "sha256:...",
  "type": "nota_fiscal",
  "data": { "...campos do schema do tipo..." },
  "confidence": 0.97,
  "status": "extracted | review | failed",
  "pipeline_version": "1.0.0",
  "prompt_version": "extract-nf@3",
  "model_id": "google/gemini-2.5-flash",
  "processed_at": "2026-09-20T12:00:00Z"
}
```

O schema de cada tipo é versionado (JSON Schema com `$id` e versão); quebra de contrato
= versão nova, nunca mutação silenciosa. Migração para Postgres em produção é mapear o
JSONL para tabelas por tipo — os schemas já são a DDL conceitual.

## Consequências

**Positivas**
- Avaliador executa sem infraestrutura; produção tem caminho claro de upgrade.
- JSONL permite leitura streaming de milhões de registros (vs. JSON único em memória).
- Envelope versionado torna cada saída auditável e reproduzível — liga direto ao
  requisito de reprodutibilidade do enunciado.

**Negativas / Riscos**
- Dois formatos de saída para manter (JSONL + CSV) — CSV é conveniência para o ERP,
  gerado do JSONL, nunca fonte.
- Sem DB, consultas ad-hoc ficam mais difíceis — aceitável no escopo; o state store
  SQLite cobre as consultas operacionais.
