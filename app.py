"""Streamlit interface for the Virtual Data Assistant."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

import streamlit as st

from data_assistant.assistant import DataAssistant, resolve_database_path
from data_assistant.contract import AssistantAnswer, Visualization, VisualizationType
from data_assistant.llm import LLMSettings, resolve_model_name
from data_assistant.visualization import (
    ImageExportError,
    VisualizationRenderError,
    build_plotly_figure,
    figure_to_png,
    result_to_csv,
    visualization_for_type,
)

EXAMPLE_QUESTIONS = (
    "Quais são os 5 estados com mais clientes que compraram pelo App em maio?",
    "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
    "Quais categorias tiveram o maior número de compras em média por cliente?",
    "Quantas reclamações não resolvidas existem por canal?",
    "Qual foi a tendência mensal de reclamações por canal no último ano?",
)

VISUAL_LABELS: dict[VisualizationType, str] = {
    "table": "Tabela",
    "bar": "Barras",
    "line": "Linha",
    "metric": "Métrica",
}

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


def _theme_override(mode: str) -> str:
    if mode == "System":
        return ""
    if mode == "Dark":
        tokens = """
          color-scheme: dark;
          --da-primary: oklch(0.75 0.12 265);
          --da-primary-soft: oklch(0.28 0.045 265);
          --da-surface: oklch(0.19 0.012 265);
          --da-ink: oklch(0.94 0.008 265);
          --da-muted: oklch(0.72 0.018 265);
          --da-outline: oklch(0.34 0.018 265);
        """
    else:
        tokens = """
          color-scheme: light;
          --da-primary: oklch(0.48 0.17 265);
          --da-primary-soft: oklch(0.94 0.035 265);
          --da-surface: oklch(0.98 0.004 265);
          --da-ink: oklch(0.22 0.025 265);
          --da-muted: oklch(0.46 0.025 265);
          --da-outline: oklch(0.86 0.012 265);
        """
    return f"<style>:root {{ {tokens} }}</style>"


def _initialize_session(database_path: Path) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    stored_path = st.session_state.get("assistant_database_path")
    if "assistant" not in st.session_state or stored_path != str(database_path):
        personal_key = st.session_state.get("byok_api_key")
        settings = LLMSettings.for_session_key(personal_key) if personal_key else None
        st.session_state.assistant = DataAssistant(database_path, llm_settings=settings)
        st.session_state.assistant_database_path = str(database_path)


def _activate_session_key(
    session: MutableMapping[str, Any], key: str, database_path: Path
) -> bool:
    """Keep a visitor credential only in this Streamlit session and its assistant."""
    clean_key = key.strip()
    if not clean_key or len(clean_key) > 512:
        return False
    session["byok_api_key"] = clean_key
    session["assistant"] = DataAssistant(
        database_path, llm_settings=LLMSettings.for_session_key(clean_key)
    )
    session["assistant_database_path"] = str(database_path)
    session["byok_invalid"] = False
    return True


def _clear_session_key(session: MutableMapping[str, Any], database_path: Path) -> None:
    """Discard both the widget value and clients that retain the visitor key."""
    for name in ("byok_api_key", "byok_key_input", "byok_invalid", "pending_question"):
        session.pop(name, None)
    session["assistant"] = DataAssistant(database_path)
    session["assistant_database_path"] = str(database_path)


@st.dialog("Continuar com minha chave OpenRouter")
def _byok_dialog(database_path: Path) -> None:
    issue = (
        "Sua chave atual foi rejeitada ou chegou ao limite gratuito. "
        if st.session_state.get("byok_invalid")
        else "A cota gratuita compartilhada terminou. "
    )
    st.markdown(
        issue + "Crie uma chave OpenRouter dedicada "
        "em [Chaves da OpenRouter](https://openrouter.ai/settings/keys), de preferência "
        "com limite de gasto ou expiração. A chave chega a este servidor para fazer "
        "as chamadas ao modelo gratuito e fica somente na memória desta sessão."
    )
    candidate = st.text_input(
        "Chave OpenRouter desta sessão",
        type="password",
        key="byok_key_input",
        max_chars=512,
        help="Não use uma chave principal sem limite de gasto.",
    )
    if st.button("Usar chave nesta sessão", type="primary"):
        if not _activate_session_key(st.session_state, candidate, database_path):
            st.error("Informe uma chave OpenRouter válida antes de continuar.")
            return
        st.rerun()


def _render_byok_controls(database_path: Path) -> str | None:
    """Offer a dialog after quota failure; retry only after an explicit click."""
    pending = st.session_state.get("pending_question")
    if not isinstance(pending, str) or not pending:
        return None
    if st.session_state.get("byok_api_key") and not st.session_state.get("byok_invalid"):
        st.info("Sua chave está ativa apenas nesta sessão. A pergunta não será repetida sozinha.")
        if st.button("Repetir pergunta pendente", key="byok_retry"):
            st.session_state.pop("pending_question", None)
            return pending
        return None
    st.caption("A consulta não será repetida até você escolher continuar.")
    label = (
        "Trocar chave"
        if st.session_state.get("byok_invalid")
        else "Continuar com minha chave"
    )
    if st.button(label, key="byok_open_dialog"):
        _byok_dialog(database_path)
    return None


def _query_database_path() -> Path:
    """Use only the operator-configured source, never visitor URL parameters."""
    return resolve_database_path()


@st.cache_data(show_spinner=False)
def _cached_png(
    data_json: str,
    visualization_json: str,
    dark: bool,
) -> tuple[bytes | None, str | None]:
    data = json.loads(data_json)
    visualization = Visualization.model_validate_json(visualization_json)
    try:
        figure = build_plotly_figure(data, visualization, dark=dark)
        return figure_to_png(figure), None
    except (ImageExportError, VisualizationRenderError) as exc:
        return None, str(exc)


def _is_dark_theme(theme_mode: str) -> bool:
    if theme_mode == "Dark":
        return True
    if theme_mode == "Light":
        return False
    context_theme = getattr(getattr(st.context, "theme", None), "type", "light")
    return context_theme == "dark"


def _render_visualization(answer: AssistantAnswer, *, key_prefix: str, theme_mode: str) -> None:
    if not answer.data:
        return
    available = answer.visualization.available_types
    selected = st.selectbox(
        "Visualização",
        options=available,
        index=available.index(answer.visualization.type),
        format_func=lambda kind: VISUAL_LABELS[kind],
        key=f"{key_prefix}_visual_type",
    )
    selected_type = cast(VisualizationType, selected)
    visualization = (
        answer.visualization
        if selected_type == answer.visualization.type
        else visualization_for_type(answer.data, selected_type, title=answer.visualization.title)
    )
    dark = _is_dark_theme(theme_mode)
    try:
        figure = build_plotly_figure(answer.data, visualization, dark=dark)
    except VisualizationRenderError as exc:
        st.warning(f"Não foi possível montar o gráfico: {exc} Exibindo a tabela.")
        visualization = visualization_for_type(
            answer.data, "table", title=answer.visualization.title
        )
        figure = build_plotly_figure(answer.data, visualization, dark=dark)

    if visualization.type == "table":
        st.dataframe(answer.data, use_container_width=True, hide_index=True)
    else:
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})

    data_json = json.dumps(answer.data, ensure_ascii=False, default=str, sort_keys=True)
    png, png_error = _cached_png(data_json, visualization.model_dump_json(), dark)
    actions = st.columns(2 if visualization.type == "table" else 1)
    if visualization.type == "table":
        actions[0].download_button(
            "Baixar CSV",
            data=result_to_csv(answer.data),
            file_name="resultado.csv",
            mime="text/csv",
            key=f"{key_prefix}_csv",
            use_container_width=True,
        )
        png_slot = actions[1]
    else:
        png_slot = actions[0]
    if png is not None:
        png_slot.download_button(
            "Baixar PNG",
            data=png,
            file_name=f"resultado-{visualization.type}.png",
            mime="image/png",
            key=f"{key_prefix}_png",
            use_container_width=True,
        )
    elif png_error:
        st.info(png_error)


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


def _render_answer(answer: AssistantAnswer, *, key_prefix: str, theme_mode: str) -> None:
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
    _render_visualization(answer, key_prefix=key_prefix, theme_mode=theme_mode)
    _render_evidence(answer)


def _render_history(messages: list[dict[str, Any]], theme_mode: str) -> None:
    for index, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and isinstance(
                message.get("answer"), AssistantAnswer
            ):
                _render_answer(
                    message["answer"],
                    key_prefix=f"answer_{index}",
                    theme_mode=theme_mode,
                )
            else:
                st.markdown(str(message["content"]))


def _sidebar(database_path: Path) -> tuple[str | None, str]:
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
        st.caption(f"Modelo · {resolve_model_name()}")
        if st.session_state.get("byok_api_key"):
            st.caption("Chave própria ativa somente nesta sessão")
            if st.button("Limpar minha chave", key="byok_clear"):
                _clear_session_key(st.session_state, database_path)
                st.rerun()
        theme_mode = st.selectbox(
            "Tema",
            options=("System", "Light", "Dark"),
            key="theme_mode",
            help=(
                "O tema System segue o navegador. Os overrides ajustam superfícies próprias "
                "e visualizações; controles nativos seguem a configuração do Streamlit."
            ),
        )
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
    return selected_question, str(theme_mode)


def main() -> None:
    st.set_page_config(
        page_title="Assistente Virtual de Dados",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(MATERIAL_STYLES, unsafe_allow_html=True)
    database_path = _query_database_path()
    _initialize_session(database_path)
    selected_question, theme_mode = _sidebar(database_path)
    override = _theme_override(theme_mode)
    if override:
        st.markdown(override, unsafe_allow_html=True)

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
    _render_history(messages, theme_mode)
    had_pending = bool(st.session_state.get("pending_question"))
    retry_question = _render_byok_controls(database_path)
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
    question = retry_question or selected_question or typed_question
    if not question:
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Interpretando a pergunta e consultando o banco…"):
            assistant: DataAssistant = st.session_state.assistant
            answer = assistant.ask(question)
        _render_answer(answer, key_prefix=f"answer_{len(messages)}", theme_mode=theme_mode)
    messages.append({"role": "assistant", "content": answer.response, "answer": answer})
    if answer.operational_code in ("quota_exhausted", "invalid_key"):
        st.session_state.pending_question = question
        if answer.operational_code == "invalid_key" or (
            answer.operational_code == "quota_exhausted" and st.session_state.get("byok_api_key")
        ):
            st.session_state.byok_invalid = True
        if not had_pending:
            _render_byok_controls(database_path)


if __name__ == "__main__":
    main()
