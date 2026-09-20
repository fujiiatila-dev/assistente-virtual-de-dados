# ADR-203: Extração estruturada validada com escada de modelos

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

A extração é o estágio crítico: a saída alimenta o ERP e o enunciado exige JSON estrito.
Três schemas fixos por tipo (Nota Fiscal, Contrato, Relatório de Manutenção). Os riscos
são alucinação de campos, valores mal parseados (moeda, data) e custo — extração é o
estágio mais caro do pipeline.

Alternativas consideradas:

1. **Regex/templates por campo** — determinístico e grátis, mas quebra a cada variação
   de template; inviável para contratos com linguagem variável.
2. **LLM forte para tudo com function calling** — melhor qualidade, maior custo por doc.
3. **Escada de modelos com validação obrigatória** — começa barato, escala por caso.

## Decisão

**Escada de modelos + validação em camadas:**

1. **Schemas como fonte de verdade:** um JSON Schema por tipo (contrato versionado do
   pipeline, ver ADR-206), com tipos, campos obrigatórios e regras de negócio.
2. **1ª tentativa — modelo barato** (Gemini Flash) com *constrained decoding*
   (function calling / JSON mode) contra o schema do tipo. Prompt com definição dos
   campos + trechos relevantes da IR.
3. **Validação determinística pós-geração:**
   - sintática: conformidade ao JSON Schema;
   - semântica: regras baratas (ex.: NF — soma dos itens ≈ valor total; datas plausíveis;
     CNPJ com dígitos verificadores válidos);
   - coerência: valores extraídos aparecem na IR (ancoragem anti-alucinação).
4. **2ª tentativa — modelo forte** (Gemini Pro) para os que falharam na validação,
   com o erro retornado como feedback no prompt.
5. **Fila de revisão** para os que falharem nas duas tentativas — com os erros
   anexados para o humano corrigir rápido.

Confiança calibrada: proporção de campos validados + presença de âncoras; alimenta a
decisão de roteamento.

## Consequências

**Positivas**
- Custo por documento cai ~60% (maioria extrai na 1ª tentativa com modelo barato) sem
  sacrificar o teto de qualidade do modelo forte.
- JSON estrito garantido por máquina (schema), não por promessa do LLM.
- Validação semântica de NF é uma rede anti-alucinação quase gratuita.

**Negativas / Riscos**
- Dois modelos para operar e monitorar.
- Regras semânticas por tipo exigem manutenção — começar com as de alto valor (totais,
   CNPJ) e crescer com os casos da fila de revisão.
- Latência do 2º nível para docs difíceis — aceitável em batch; no modo online o ERP
  recebe "em revisão" até validar (ver ADR-205).
