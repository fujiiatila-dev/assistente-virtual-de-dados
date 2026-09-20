# ADR-205: Operação dual-mode — batch de backlog e online para o ERP

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

O enunciado descreve um backlog (processar uma pasta `data/raw`) mas o cenário real é
um fluxo contínuo alimentando o ERP: "milhares de documentos digitalizados" hoje e um
fluxo diario depois. São dois padrões de consumo diferentes: throughput máximo com custo
controlado vs. latência baixa por documento. Um único modo rígido atende mal aos dois.

Alternativas consideradas:

1. **Só batch CLI** — atende o desafio, ignora o cenário de produção que a entrevista
   vai explorar.
2. **Só serviço online** — elegância de "tudo é streaming", mas processar 1M docs
   históricos por fila HTTP é ineficiente e caro.
3. **Dual-mode: mesmo núcleo, duas portas de entrada.**

## Decisão

**Um núcleo de pipeline, duas portas de entrada:**

- **Modo batch (CLI):** `pipeline run data/raw/` — varre a pasta, registra jobs no state
  store, processa com paralelismo configurável e relatório final (sucessos, revisão,
  falhas, custo). Para o backlog e para reprocessamentos seletivos.
- **Modo online (worker):** serviço long-running que consome documentos conforme chegam
  (watch de pasta, upload via endpoint leve ou fila do ERP). Mesmos estágios, mesmo
  state store; única diferença é a política de paralelismo (baixa, para latência) e a
  prioridade (documento novo na frente do backlog).

O ERP consome a saída do state store (tabela de documentos persistidos) — o pipeline
desacopla o processamento do consumo, então o ERP nunca fica bloqueado por um documento
em revisão: ele vê o status.

## Consequências

**Positivas**
- Custo do backlog otimizável (rodar em janelas, paralelismo alto, modelo conforme
  disponibilidade); latência do online protegida.
- Zero duplicação de lógica: correção de bug ou novo prompt beneficia os dois modos.
- História natural para a entrevista: "como isso vira produção?" tem resposta desenhada,
  não improvisada.

**Negativas / Riscos**
- Duas configurações de runtime para testar.
- O modo online só se justifica com integração real — no escopo do desafio, entregamos o
  batch completo e o worker como esboço funcional.
