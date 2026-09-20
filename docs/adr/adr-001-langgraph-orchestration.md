# ADR-001: LangGraph como orquestrador do agente

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O motor de inteligência precisa responder perguntas de negócio com raciocínio em múltiplos
passos: interpretar a pergunta, descobrir o schema, gerar SQL, executar, validar, corrigir
erros e formatar a resposta. O fluxo não é linear — há ciclos (correção de SQL) e condições
(suficiência dos dados). O enunciado sugere LangChain/LangGraph e o prazo é de 5 dias.

Alternativas consideradas:

1. **Chain única (LangChain LCEL)** — pipeline linear prompt → LLM → parser. Não suporta
   naturalmente loops de correção nem ramificação condicional; exigiria orquestração manual
   frágil com `try/except` encadeados.
2. **Framework de agentes próprio (while loop + state dict)** — controle total, zero
   dependências, mas reimplementa serialização de estado, checkpointing e observabilidade
   que a biblioteca já entrega; em 5 dias o custo de manutenção supera o benefício.
3. **LangGraph** — grafo de nós explícitos com estado tipado, ciclos nativos, condicionais
   e integração com LangChain (tool calling, parsers).

## Decisão

Usar **LangGraph** como orquestrador. O fluxo principal será um grafo:

```
interpretar → descobrir_schema → gerar_sql → validar → executar
                                   ↑             ↓ (erro)
                                   └── corrigir ←┘
                                     (máx. N tentativas)
executar → (dados suficientes?) → sim → formatar_resposta
                                → não → refinar_consulta → executar
```

O estado compartilhado (`AgentState`) carrega: pergunta, schema, hipóteses, queries
executadas, resultados e erros. Nós são funções puras testáveis; as arestas condicionais
ficam em funções dedicadas, também testáveis sem chamar o LLM.

## Consequências

**Positivas**
- Ciclo de correção de SQL é um recurso de primeira classe (ver ADR-005).
- Grafo explícito alimenta diretamente a transparência do raciocínio exigida na UI
  (cada nó executado vira um passo visível no Streamlit).
- Estado tipado com `TypedDict` facilita testes unitários por nó.

**Negativas / Riscos**
- Dependência adicional (langgraph) com churn de API relativamente frequente — mitigado
  por versionamento pinado em `pyproject.toml`.
- Curva de aprendizado maior que LCEL; documentação do fluxo no README compensa.

**Neutras**
- O fluxo acima é ilustrativo: a implementação final pode mesclar nós (ex.: gerar e
  validar no mesmo nó) desde que preserve o ciclo de correção e a trilha de passos.
