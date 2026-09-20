"""Streamlit interface for the Virtual Data Assistant."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from data_assistant.assistant import DataAssistant, resolve_database_path
from data_assistant.contract import AssistantAnswer
from data_assistant.llm import DEFAULT_MODEL
from data_assistant.visualization import VisualizationRenderError, build_plotly_figure

EXAMPLE_QUESTIONS = (
    "Quais são os 5 estados com mais clientes que compraram pelo App em maio?",
    "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
    "Quais categorias tiveram o maior número de compras em média por cliente?",
    "Quantas reclamações não resolvidas existem por canal?",
    "Qual foi a tendência mensal de reclamações por canal no último ano?",
)

MATERIAL_STYLES = """
<style>
:root {
  color-scheme: light dark;
  --da-primary: oklch(0.48 0.17 265);
  --da-primary-soft: oklch(0.94 0.035 265);
  --da-surface: oklch(0.98 0.004 265);
  --da-ink: oklch(0.22 0.025 265);
  --da-muted: oklch(0.46 0.025 265);
  --da-outline: oklch(0.86 0.012 265);
  --da-success: oklch(0.48 0.12 150);
}
@media (prefers-color-scheme: dark) {
  :root {
    --da-primary: oklch(0.75 0.12 265);
    --da-primary-soft: oklch(0.28 0.045 265);
    --da-surface: oklch(0.19 0.012 265);
    --da-ink: oklch(0.94 0.008 265);
    --da-muted: oklch(0.72 0.018 265);
    --da-outline: oklch(0.34 0.018 265);
    --da-success: oklch(0.72 0.12 150);
  }
}
.da-header {
  padding: 0.6rem 0 1.4rem;
  max-width: 72ch;
}
.da-header h1 {
  color: var(--da-ink);
  font-size: 2rem;
  letter-spacing: -0.025em;
  line-height: 1.18;
  margin: 0 0 0.45rem;
  text-wrap: balance;
}
.da-header p {
  color: var(--da-muted);
  font-size: 1rem;
  line-height: 1.55;
  margin: 0;
  max-width: 68ch;
  text-wrap: pretty;
}
.da-empty {
  background: var(--da-primary-soft);
  border: 1px solid var(--da-outline);
  border-radius: 1rem;
  color: var(--da-ink);
  margin: 1.5rem 0;
  padding: 1.25rem 1.4rem;
}
.da-empty strong { display: block; margin-bottom: 0.35rem; }
.da-empty span { color: var(--da-muted); line-height: 1.5; }
.da-db-label {
  color: var(--da-muted);
  font-size: 0.875rem;
  margin-bottom: 0.35rem;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
"""


def _initialize_session(database_path: Path) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    stored_path = st.session_state.get("assistant_database_path")
    if "assistant" not in st.session_state or stored_path != str(database_path):
        st.session_state.assistant = DataAssistant(database_path)
        st.session_state.assistant_database_path = str(database_path)


def _render_visualization(answer: AssistantAnswer) -> None:
    if not answer.data:
        return
    try:
        figure = build_plotly_figure(answer.data, answer.visualization)
    except VisualizationRenderError as exc:
        st.warning(f"Não foi possível montar o gráfico: {exc} Exibindo a tabela.")
        st.dataframe(answer.data, use_container_width=True, hide_index=True)
        return

    if answer.visualization.type == "table":
        st.dataframe(answer.data, use_container_width=True, hide_index=True)
    else:
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def _render_evidence(answer: AssistantAnswer) -> None:
    with st.expander("Etapas e evidências da resposta", expanded=False):
        if not answer.steps:
            st.caption("Nenhuma etapa foi registrada para esta resposta.")
            return
        for index, step in enumerate(answer.steps, start=1):
            node = str(step.get("node", "etapa")).replace("_", " ").title()
            st.markdown(f"**{index}. {node}**")
            st.caption(str(step.get("detail", "Etapa concluída.")))
            if step.get("sql"):
                st.code(str(step["sql"]), language="sql")
            if step.get("error"):
                st.warning(str(step["error"]))
            rows = step.get("rows")
            if isinstance(rows, list) and rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_answer(answer: AssistantAnswer) -> None:
    status_renderers = {
        "error": st.error,
        "partial": st.warning,
        "empty": st.info,
    }
    renderer = status_renderers.get(answer.status)
    if renderer:
        renderer(answer.response)
    else:
        st.markdown(answer.response)
    for warning in answer.warnings:
        st.warning(warning)
    _render_visualization(answer)
    _render_evidence(answer)


def _render_history(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and isinstance(
                message.get("answer"), AssistantAnswer
            ):
                _render_answer(message["answer"])
            else:
                st.markdown(str(message["content"]))


def _sidebar(database_path: Path) -> str | None:
    selected_question: str | None = None
    with st.sidebar:
        st.subheader("Assistente de Dados")
        st.caption("Consultas auditáveis em SQLite")
        st.divider()
        st.markdown('<p class="da-db-label">Fonte de dados</p>', unsafe_allow_html=True)
        if database_path.is_file():
            st.success(f"Conectado · {database_path.name}", icon="✅")
        else:
            st.error(f"Banco ausente · {database_path.name}", icon="⚠️")
            st.caption("Configure DB_PATH no arquivo .env e reinicie a aplicação.")
        st.caption(f"Modelo · {DEFAULT_MODEL}")
        st.divider()
        st.subheader("Perguntas para explorar")
        for index, question in enumerate(EXAMPLE_QUESTIONS, start=1):
            if st.button(
                question,
                key=f"example_{index}",
                use_container_width=True,
                disabled=not database_path.is_file(),
            ):
                selected_question = question
        st.divider()
        st.caption("As consultas são validadas e executadas somente para leitura.")
    return selected_question


def main() -> None:
    st.set_page_config(
        page_title="Assistente Virtual de Dados",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(MATERIAL_STYLES, unsafe_allow_html=True)
    database_path = resolve_database_path()
    _initialize_session(database_path)
    selected_question = _sidebar(database_path)

    st.markdown(
        """
        <section class="da-header">
          <h1>Converse com seus dados</h1>
          <p>Faça uma pergunta de negócio. O assistente descobre o schema, gera uma consulta
          segura e apresenta os dados com evidências para conferência.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    messages: list[dict[str, Any]] = st.session_state.messages
    _render_history(messages)
    if not messages:
        st.markdown(
            """
            <div class="da-empty">
              <strong>Comece por uma pergunta concreta</strong>
              <span>Escolha um exemplo na barra lateral ou escreva sua própria pergunta.
              Resultados, SQL e etapas ficam disponíveis na mesma conversa.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    typed_question = st.chat_input(
        "Pergunte sobre clientes, compras, suporte ou campanhas",
        disabled=not database_path.is_file(),
    )
    question = selected_question or typed_question
    if not question:
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Interpretando a pergunta e consultando o banco…"):
            assistant: DataAssistant = st.session_state.assistant
            answer = assistant.ask(question)
        _render_answer(answer)
    messages.append({"role": "assistant", "content": answer.response, "answer": answer})


if __name__ == "__main__":
    main()
