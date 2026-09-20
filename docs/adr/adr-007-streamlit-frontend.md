# ADR-007: Streamlit como frontend

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O entregável exige interface simples onde o usuário converse com o assistente, veja
visualizações apropriadas e acompanhe o raciocínio (passos e queries). O prazo é de 5 dias
e o foco da avaliação é o motor de inteligência, não o frontend.

Alternativas consideradas:

1. **Streamlit** — apps de dados em Python puro; `st.chat_message`/`st.chat_input` nativos;
   execução com um comando.
2. **FastAPI + React** — separação limpa e demo mais "produto", mas o custo de build de UI
   ( bundling, CORS, deploy de dois serviços ) consome dias do prazo sem pontuar nos
   requisitos.
3. **Gradio** — também rápido, mas o layout de chat + painéis laterais fica menos
   flexível que Streamlit.

## Decisão

**Streamlit** (`app.py`) com:

- Chat central (`st.chat_message`, `st.chat_input`) com histórico em `st.session_state`;
- **Painel do raciocínio** por resposta: `st.expander` com a linha do tempo de nós
  executados, cada query SQL executada em bloco de código e o resultado/tabla que cada
  uma retornou (transparência exigida pelo enunciado);
- Renderizador de visualização conforme ADR-006;
- Seletor de exemplo de perguntas (as 5 do enunciado) para demo em um clique;
- Barra lateral com configuração de modelo (somente leitura) e status da conexão ao banco.

O Streamlit conversa com o motor **em processo** (import direto do pacote do agente) —
sem API intermediária, pois o escopo é single-user. `streamlit run app.py` deve ser o
único comando necessário além de configurar a `.env`.

## Consequências

**Positivas**
- Menor risco de prazo; foco de engenharia permanece no motor LangGraph.
- Re-execução nativa por interação encaixa no modelo do agente (uma pergunta = uma
  execução do grafo).
- O expander de raciocínio vira diferencial visual na demo — mostra exatamente o que o
  enunciado pede ("transparência sobre como chegou àquela conclusão").

**Negativas / Riscos**
- Execução em-processo bloqueia a UI durante o raciocínio — mitigado com spinner por
  etapa (status do nó atual).
- Sem API HTTP separada, reuso programático do motor fica implícito — o pacote do agente
  será desenhado independente do Streamlit (imports limpos), deixando a extração de uma
  API como melhoria futura no README.
