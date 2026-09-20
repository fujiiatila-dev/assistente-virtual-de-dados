# Desafio 2 — Pipeline de Documentos: Arquitetura de Referência

> **Nota:** desafio **não implementado** por escolha deliberada. Conforme o enunciado,
> a arquitetura deste sistema é o foco da discussão na entrevista técnica.
>
> Material complementar: [diagramas de sequência do fluxo completo](sequence-diagrams.md)
> (fluxo feliz, desvios de falha e otimização opcional).

## 1. Problema

Processar milhares de documentos digitalizados (PDF) de 3 tipos — **Nota Fiscal**,
**Contrato de Prestação de Serviços**, **Relatório de Manutenção** — extraindo campos
específicos por tipo em JSON estrito, para alimentar o ERP.

Requisitos não-funcionais do enunciado e o que eles realmente exigem:

| Requisito | Tradução arquitetural |
|---|---|
| **Eficiência** (milhões de docs, latência e custo) | Processamento barato por documento + paralelismo + cache; LLM só onde necessário |
| **Robustez** (não falhar com anômalos) | Isolamento de falha por item + fila de revisão humana; sem poision message |
| **Reprodutibilidade** (resultados consistentes) | Versionamento de tudo que afeta a saída: prompt, modelo, código, pipeline |

## 2. Visão geral da solução

```
                       ┌──────────────────────────────────────────────┐
                       │            ORQUESTRAÇÃO (state store)        │
                       │  idempotência · retentativas · status · DLQ  │
                       └──────────────┬───────────────────────────────┘
                                      │
data/raw/*.pdf ──► ingestão ──► IR intermediária ──► classificação ──► roteamento
                   (scan PDF)     (texto+layout)     (cascata)          por tipo
                                                                            │
                              ┌─────────────────────────────────────────────┤
                              ▼                        ▼                    ▼
                        extração NF              extração Contrato    extração Relatório
                              └───────────────┬───────────────────────┴────────────┘
                                              ▼
                                    validação de saída (JSON Schema + regras)
                                              │
                        ┌─────────────────────┼──────────────────────┐
                        ▼                     ▼                      ▼
                  revisão humana          persistência           métricas/observabilidade
                  (baixa confiança)      (JSON consolidado,     (taxas, custos, confiança,
                                          CSV/Parquet, DB)       versões, tracing)
```

Fluxo em uma frase: **cada documento é um job idempotente** que atravessa os estágios
com estado persistido em cada transição — nada é reprocessado do zero, nada é perdido.

## 3. Estágios e decisões (índice de ADRs)

| # | Estágio | ADR | Decisão em uma linha |
|---|---|---|---|
| 1 | Ingestão + IR | [ADR-201](adr-201-hybrid-extraction-ir.md) | Extração híbrida: camada de texto primeiro, OCR só se necessário; IR intermediária desacopla classificação/extracão |
| 2 | Classificação | [ADR-202](adr-202-cascade-classification.md) | Cascata: regras → modelo pequeno; roteamento por tipo com fila de revisão |
| 3 | Extração | [ADR-203](adr-203-validated-extraction-model-ladder.md) | JSON Schema estrito + validação + "escada" de modelos por dificuldade |
| 4 | Persistência | [ADR-206](adr-206-persistence-versioned-contract.md) | Contrato versionado; JSON consolidado + CSV; DB como evolução natural |
| — | Execução | [ADR-204](adr-204-idempotent-state-store.md) | Jobs idempotentes com state store (batch e online compartilham o núcleo) |
| — | Operação | [ADR-205](adr-205-dual-mode-operation.md) | Dual-mode: CLI batch para backlog, worker online para o ERP |

## 4. Camada de IA — visão consolidada

Três toques de LLM por documento (mínimo teórico: 2; classificação e extração podem
fundir em um prompt único para docs de alta confiança):

1. **Classificação** — modelo pequeno/barato (Gemini Flash), saída JSON fechada
   (`{type, confidence}`).
2. **Extração** — modelo forte (Gemini Pro), *constrained decoding*/function calling
   contra o schema do tipo identificado.
3. **Validador semântico leve** (opcional) — checagens baratas de coerência
   (ex.: soma dos itens ≈ total da NF) antes de cravar confiança alta.

Escada de dificuldade (ADR-203): tentativa barata primeiro; só escala para o modelo
forte se confiança baixa ou validação falhar — **economia média estimada de ~60%**
vs. usar o modelo forte para tudo.

## 5. Custo e escala

Para 1M documentos/mês (hipótese de dimensionamento):

- Ingestão/IR: compute puro, sem custo de API.
- Classificação: ~1M chamadas Flash ≈ dezenas de dólares.
- Extração: ~60% Flash (docs fáceis) + 40% Pro (difíceis) ≈ poucas centenas de dólares.
- Revisão humana esperada: 2–5% dos documentos (fila de baixa confiança).
- Paralelismo limitado por rate limit do provedor; state store absorve picos (backlog roda
  em janelas de custo menor).

## 6. Observabilidade e reprodutibilidade

- **Versionamento:** cada registro de saída carrega `pipeline_version`, `prompt_version`,
  `model_id`, `code_version` — reprocessar com a mesma versão reproduz a mesma saída.
- **Métricas:** taxa de classificação por tipo, taxa de extração validada em 1ª tentativa,
  taxa de revisão humana, custo por documento, p50/p95 por estágio.
- **Tracing:** cada job tem ID; logs estruturados por estágio com hash do conteúdo.
- **Golden set:** amostra anotada à mão para regressão de qualidade a cada mudança de
  prompt/modelo.

## 7. Matriz de riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| PDF sem camada de texto (scan puro) | Extração impossível | Detector de camada de texto; OCR como estágio dedicado (ADR-201) |
| Doc ambíguo ou tipo novo | Classificação errada | Fila de revisão; nunca "chutar" tipo com confiança baixa (ADR-202) |
| Alucinação de campo pelo LLM | Dado errado no ERP | JSON Schema estrito + validação + revisão (ADR-203) |
| Pico de backlog | Custo/latência | Paralelismo configurável + state store; processar em janelas (ADR-205) |
| Mudança de prompt/modelo quebra saída | Regressão silenciosa | Golden set + versionamento (seção 6) |
