# ADR-202: Classificação em cascata com fila de revisão

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

Cada documento precisa ser classificado em um de 3 tipos antes da extração, pois o
schema de extração depende do tipo. As classes têm assinaturas textuais fortes
("NOTA FISCAL", "CONTRATO DE PRESTAÇÃO DE SERVIÇOS", termos técnicos de manutenção),
o que sugere que um classificador caro é desperdício. Em produção, porém, surgirão
documentos anômalos ou de tipos fora dos 3 conhecidos — o pipeline não pode falhar
nem "forçar" uma classe.

Alternativas consideradas:

1. **LLM classificando tudo** — simples, mas o documento mais caro possível para uma
   tarefa que regras resolvem na maioria dos casos.
2. **Classificador tradicional (TF-IDF + regressão logística)** — baratíssimo e rápido,
   mas exige treino/rotulação e sofre com variações de template.
3. **Cascata regras → LLM pequeno → revisão humana** — custo proporcional à dificuldade.

## Decisão

**Cascata de 3 níveis:**

1. **Regras determinísticas** (rápido, grátis): regex/palavras-chave fortes por tipo +
   regras de estrutura (ex.: NF tem bloco de itens com valores). Confiança alta →
   segue direto. **Meta: resolver ~80% dos documentos.**
2. **LLM pequeno/barato** (ex.: Gemini Flash) para os ambíguos: recebe trecho
   representativo da IR (primeira página + seções com título) e responde JSON fechado
   `{type, confidence}` via constrained output.
3. **Fila de revisão humana** quando: regras inconclusivas E confiança do modelo abaixo
   do limiar, OU classe com distribuição improvável (ex.: contrato de 40 páginas com
   bloco de itens de NF), OU documento que não se encaixa em nenhum tipo.

A decisão de cada nível e o motivo ficam registrados no job (observabilidade).

## Consequências

**Positivas**
- Custo médio de classificação perto de zero (maioria resolvida por regras).
- Documentos anômalos têm destino seguro (revisão) — pilar do requisito de robustez.
- A fila de revisão produz dados rotulados que realimentam as regras/golden set.

**Negativas / Riscos**
- Regras exigem manutenção à medida que templates variam — mitigado por relatório de
  "fugas" (docs que regras não resolveram).
- Três caminhos de classificação para testar; complexidade compensada por cada nível
  ser simples e auditável.

**Nota de entrevista:** um classificador tradicional treinado é a evolução natural se a
fila de revisão crescer; a cascata permite plugar o modelo treinado no lugar do LLM sem
mudar o roteamento.
