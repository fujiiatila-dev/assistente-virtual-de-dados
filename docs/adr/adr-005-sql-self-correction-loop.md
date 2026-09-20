# ADR-005: Loop de auto-correção de SQL

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O enunciado exige: "Se o sistema gerar SQL inválido, ele deve ser capaz de perceber o erro
e tentar corrigir sozinho". Erros vêm de três fontes: (a) SQL sintaticamente inválido,
(b) SQL válido mas contra colunas/tabelas inexistentes, (c) SQL válido cujo resultado não
responde a pergunta (vazio, incompleto ou dimensionalmente errado).

Alternativas consideradas:

1. **Sem correção (falhar rápido)** — viola o requisito.
2. **Regenerar do zero a cada erro** — joga fora o contexto do erro; o modelo tende a
   repetir o mesmo equívoco.
3. **Loop de correção com feedback estruturado** — o erro real do SQLite e a query anterior
   voltam para o prompt, o modelo ajusta; limitado por orçamento de tentativas.

## Decisão

Loop de correção no grafo (ver ADR-001) com **feedback estruturado**:

1. Nó `executar` captura a exceção do SQLite **com a mensagem original** (`sqlite3.OperationalError: no such column: ...`).
2. Nó `corrigir` recebe: pergunta, schema, SQL anterior, mensagem de erro e resultado
   (quando houver) e gera uma nova query.
3. Aresta condicional retorna a `executar` com orçamento de **3 tentativas de correção**;
   exaustas, o nó `formatar_resposta` produz uma resposta honesta de incapacidade
   (explicando o que tentou), nunca um erro cru.

Para erros do tipo (c) — "respondeu, mas não responde a pergunta" — o nó avaliador decide
por **refinamento** (nova consulta complementar, ex.: agregação faltante) em vez de
correção da mesma query, e o orçamento total de consultas por pergunta é 6.

Todo passo do loop é registrado no estado (queries, erros, tentativas) e aparece na UI
(transparência de raciocínio).

## Consequências

**Positivas**
- Mensagem de erro real do SQLite é o melhor sinal possível para o LLM — corrige
  `no such column` e afins com alta taxa de sucesso.
- Orçamento limita custo e evita loop infinito; comportamento de falha é determinístico
  e testável (mockando o executor).
- Distinção correção vs refinamento evita o anti-padrão de regenerar a mesma query.

**Negativas / Riscos**
- Até 6 consultas + até ~6 chamadas de LLM por pergunta no pior caso — custo ainda baixo
  com Gemini Flash; monitorável via contadores no estado.
- Critério de "suficiência dos dados" é julgado por LLM e pode falhar — mitigado por
  prompt estrito e heurística determinística (resultado vazio + pergunta quantitativa
  força refinamento).
