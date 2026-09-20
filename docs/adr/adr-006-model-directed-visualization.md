# ADR-006: Visualização dirigida pelo modelo com fallback determinístico

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

A UI deve exibir os dados "da forma mais apropriada para a pergunta" — tabela para listas,
gráfico de linha para tendências, barra para comparações — ou conforme pedido pelo usuário.
Duas formas de decidir: heurística determinística sobre o resultado, ou o próprio LLM
decidindo no momento da formatação.

Alternativas consideradas:

1. **Só heurística** — determinística e barata, mas cega ao **intento** (a mesma tabela
   de série temporal é tendência se a pergunta fala em "evolução" e comparação se fala em
   "qual canal vende mais").
2. **Só LLM** — capta intent, mas não é determinístico e pode alucinar tipos.
3. **Híbrido: LLM escolhe entre um cardápio fechado; heurística valida e faz fallback.**

## Decisão

**Híbrido.** O nó `formatar_resposta` do grafo retorna, junto com a resposta, um bloco de
apresentação:

```json
{
  "response": "texto da resposta em linguagem natural",
  "visualization": {
    "type": "line | bar | table | metric",
    "title": "Título",
    "x": "coluna x", "y": "colunas y", "group": null
  }
}
```

O cardápio é fechado (`line`, `bar`, `table`, `metric`) e o frontend valida:
- tipo desconhecido → fallback para `table`;
- colunas referenciadas inexistentes no resultado → fallback para `table`;
- resultado com mais de N séries → quebra ou fallback.

Se o usuário pediu explicitamente um formato ("mostre como gráfico de barras"), esse pedido
entra no prompt com prioridade declarada sobre a escolha automática.

Streamlit renderiza: `line`/`bar` via `st.bar_chart`/`st.line_chart` (ou Altair para
controle de eixos), `table` via `st.dataframe`, `metric` via `st.metric`.

## Consequências

**Positivas**
- Escolha ciente de intent com rede de segurança determinística — nunca quebra a UI.
- Contrato JSON explícito entre motor e frontend: testável com fixtures sem LLM.
- O mesmo contrato serve para o README documentar exemplos (pergunta → visual).

**Negativas / Riscos**
- Uma chamada LLM extra para formatação (com Gemini Flash, custo desprezível).
- Gráficos avançados (compostos, duplo eixo) ficam fora do cardápio — suficiente para o
  escopo; extensão natural registrada no README.
