"""Streamlit interface for the Virtual Data Assistant."""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

import streamlit as st

from data_assistant.assistant import DataAssistant, resolve_database_path
from data_assistant.contract import AssistantAnswer, Visualization, VisualizationType
from data_assistant.execution import (
    EXECUTIONS,
    ExecutionCapacityError,
    ExecutionSnapshot,
)
from data_assistant.llm import DEFAULT_MODEL, LLMSettings
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
ROBOT_ASSET = Path(__file__).resolve().parent / "assets" / "robot.svg"

MATERIAL_STYLES = """
<style>
.da-brand {
  align-items: center;
  color: inherit;
  display: flex;
  font-size: 0.92rem;
  font-weight: 650;
  gap: 0.7rem;
  line-height: 1.25;
  margin: 0.2rem 0 1rem;
}
.da-brand img {
  height: 2.25rem;
  width: 2.25rem;
}
.da-header {
  padding: 0.6rem 0 1.4rem;
  max-width: 72ch;
}
.da-header h1 {
  color: inherit;
  font-size: 2rem;
  letter-spacing: -0.025em;
  line-height: 1.18;
  margin: 0 0 0.45rem;
  text-wrap: balance;
}
.da-header p {
  color: inherit;
  font-size: 1rem;
  line-height: 1.55;
  margin: 0;
  max-width: 68ch;
  opacity: 0.78;
  text-wrap: pretty;
}
.da-empty {
  background: transparent;
  border: 1px solid color-mix(in srgb, currentColor 24%, transparent);
  border-radius: 1rem;
  color: inherit;
  margin: 1.5rem 0;
  padding: 1.25rem 1.4rem;
}
.da-empty strong { display: block; margin-bottom: 0.35rem; }
.da-empty span { color: inherit; line-height: 1.5; opacity: 0.78; }
.da-loading {
  align-items: center;
  color: inherit;
  display: flex;
  font-size: 0.95rem;
  gap: 0.75rem;
  min-height: 2.5rem;
  padding: 0.35rem 0;
}
.da-loading-mark {
  display: inline-block;
  flex: 0 0 2rem;
  height: 2rem;
  position: relative;
  width: 2rem;
}
.da-loading-mark span {
  animation: da-pulse 0.95s ease-in-out infinite;
  animation-delay: calc(var(--i) * -0.14s);
  background: currentColor;
  border-radius: 999px;
  height: 0.6rem;
  left: 0.875rem;
  opacity: 0.28;
  position: absolute;
  top: 0.1rem;
  transform: rotate(calc(var(--i) * 60deg));
  transform-origin: 0.125rem 0.9rem;
  width: 0.25rem;
}
.da-progress-note {
  color: inherit;
  font-size: 0.85rem;
  margin: 0.2rem 0 0.6rem 2.75rem;
  max-width: 68ch;
  opacity: 0.78;
}
@keyframes da-pulse {
  0%, 100% { opacity: 0.28; }
  48% { opacity: 1; }
}
:where(button, input, textarea, [role="button"]):focus-visible {
  outline: 2px solid currentColor !important;
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .da-loading-mark span { animation: none; opacity: 0.85; }
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
"""


def _brand_markup() -> str:
    """Render the exact favicon asset with an accessible text alternative."""
    encoded = b64encode(ROBOT_ASSET.read_bytes()).decode("ascii")
    return (
        '<div class="da-brand">'
        f'<img src="data:image/svg+xml;base64,{encoded}" '
        'alt="Robô do Assistente Virtual de Dados">'
        '<span>Assistente Virtual de Dados</span></div>'
    )


def _loading_markup(message: str = "Entendendo a pergunta") -> str:
    capsules = "".join(
        f'<span style="--i:{index}" aria-hidden="true"></span>' for index in range(6)
    )
    return (
        '<div class="da-loading" role="status" aria-live="polite">'
        f'<span class="da-loading-mark" aria-hidden="true">{capsules}</span>'
        f"<span>{message}</span></div>"
    )


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


def _is_dark_theme() -> bool:
    """Read the session override or the effective browser/system theme."""
    return _effective_theme() == "dark"


def _effective_theme() -> str:
    """Read the viewer's active theme from Streamlit's built-in settings menu."""
    context_theme = getattr(getattr(st.context, "theme", None), "type", "light")
    return "dark" if context_theme == "dark" else "light"


def _progress_markup(snapshot: ExecutionSnapshot) -> str:
    """Render only allow-listed public phases and cancellation status."""
    if snapshot.cancellation_requested:
        message = "Solicitação de parada enviada. Encerrando a etapa atual."
    else:
        message = snapshot.phase.value
    markup = _loading_markup(message)
    if snapshot.cancellation_requested and snapshot.may_have_consumed_quota:
        markup += (
            '<div class="da-progress-note" role="status" aria-live="polite">'
            "Uma chamada já iniciada pode ter consumido cota; o resultado será descartado."
            "</div>"
        )
    return markup


def _render_visualization(answer: AssistantAnswer, *, key_prefix: str) -> None:
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
    dark = _is_dark_theme()
    try:
        figure = build_plotly_figure(answer.data, visualization)
    except VisualizationRenderError as exc:
        st.warning(f"Não foi possível montar o gráfico: {exc} Exibindo a tabela.")
        visualization = visualization_for_type(
            answer.data, "table", title=answer.visualization.title
        )
        figure = build_plotly_figure(answer.data, visualization)

    if visualization.type == "table":
        st.dataframe(answer.data, use_container_width=True, hide_index=True)
    else:
        st.plotly_chart(
            figure,
            use_container_width=True,
            config={"displayModeBar": False},
            theme="streamlit",
        )

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


def _render_answer(answer: AssistantAnswer, *, key_prefix: str) -> None:
    if answer.status == "cancelled":
        st.info(answer.response)
        for warning in answer.warnings:
            st.warning(warning)
        return
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
    _render_visualization(answer, key_prefix=key_prefix)
    _render_evidence(answer)


def _store_answer(answer: AssistantAnswer) -> None:
    """Append a completed worker result once and preserve the explicit BYOK flow."""
    messages: list[dict[str, Any]] = st.session_state.messages
    messages.append({"role": "assistant", "content": answer.response, "answer": answer})
    question = next(
        (
            str(message.get("content", ""))
            for message in reversed(messages[:-1])
            if message.get("role") == "user"
        ),
        "",
    )
    if answer.operational_code in ("quota_exhausted", "invalid_key"):
        st.session_state.pending_question = question
        if answer.operational_code == "invalid_key" or (
            answer.operational_code == "quota_exhausted"
            and st.session_state.get("byok_api_key")
        ):
            st.session_state.byok_invalid = True


@st.fragment(run_every=0.5)
def _poll_active_execution(execution_id: str) -> None:
    """Poll a worker without starting another query or touching it from the worker."""
    if st.session_state.get("active_execution_id") != execution_id:
        return
    snapshot = EXECUTIONS.snapshot(execution_id)
    if snapshot is None:
        answer = AssistantAnswer(
            status="error",
            response="A execução expirou antes de retornar. Envie a pergunta novamente.",
            visualization=Visualization(
                type="table", title="Execução expirada", available_types=["table"]
            ),
            operational_code="local_error",
        )
        st.session_state.pop("active_execution_id", None)
        _store_answer(answer)
        st.rerun()
        return
    if snapshot.done:
        answer = EXECUTIONS.consume(execution_id)
        if answer is None:
            answer = AssistantAnswer(
                status="error",
                response="Não foi possível recuperar a resposta. Envie a pergunta novamente.",
                visualization=Visualization(
                    type="table", title="Falha operacional", available_types=["table"]
                ),
                operational_code="local_error",
            )
        st.session_state.pop("active_execution_id", None)
        _store_answer(answer)
        st.rerun()
        return

    st.markdown(_progress_markup(snapshot), unsafe_allow_html=True)
    cancel_clicked = st.button(
        "Parar execução",
        key=f"stop_execution_{execution_id}",
        disabled=snapshot.cancellation_requested,
    )
    if cancel_clicked:
        EXECUTIONS.cancel(execution_id)


def _render_history(messages: list[dict[str, Any]]) -> None:
    for index, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and isinstance(
                message.get("answer"), AssistantAnswer
            ):
                _render_answer(
                    message["answer"],
                    key_prefix=f"answer_{index}",
                )
            else:
                st.markdown(str(message["content"]))


def _sidebar(database_path: Path, *, busy: bool = False) -> str | None:
    selected_question: str | None = None
    with st.sidebar:
        st.subheader("Assistente de Dados")
        st.caption("Perguntas de negócio com SQL auditável")
        st.divider()
        st.caption("FONTE DE DADOS")
        st.caption(f"Fonte de dados · {database_path.name}")
        if database_path.is_file():
            st.caption("Pronta para consultas somente leitura")
        else:
            st.error("Banco ausente. Configure DB_PATH e reinicie a aplicação.")
        st.caption(f"Modelo · {DEFAULT_MODEL}")
        if st.session_state.get("byok_api_key"):
            st.caption("Chave própria ativa somente nesta sessão")
            if st.button("Limpar minha chave", key="byok_clear"):
                _clear_session_key(st.session_state, database_path)
                st.rerun()
        st.divider()
        st.caption("EXPLORE OS DADOS")
        for index, question in enumerate(EXAMPLE_QUESTIONS, start=1):
            if st.button(
                question,
                key=f"example_{index}",
                use_container_width=True,
                disabled=not database_path.is_file() or busy,
            ):
                selected_question = question
        st.divider()
        st.caption("As consultas são validadas e executadas somente para leitura.")
    return selected_question


def main() -> None:
    st.set_page_config(
        page_title="Assistente Virtual de Dados",
        page_icon=str(ROBOT_ASSET),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(MATERIAL_STYLES, unsafe_allow_html=True)
    database_path = _query_database_path()
    _initialize_session(database_path)
    active_execution_id = st.session_state.get("active_execution_id")
    if not isinstance(active_execution_id, str):
        active_execution_id = None
    busy = active_execution_id is not None
    selected_question = _sidebar(database_path, busy=busy)
    st.markdown(_brand_markup(), unsafe_allow_html=True)

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
    if active_execution_id is not None:
        with st.chat_message("assistant"):
            _poll_active_execution(active_execution_id)
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
        disabled=not database_path.is_file() or busy,
    )
    question = None if busy else (retry_question or selected_question or typed_question)
    if not question:
        return

    messages.append({"role": "user", "content": question})
    assistant: DataAssistant = st.session_state.assistant
    try:
        execution_id = EXECUTIONS.start(
            lambda control: assistant.ask(question, execution_control=control)
        )
    except ExecutionCapacityError:
        _store_answer(
            AssistantAnswer(
                status="error",
                response=(
                    "O assistente está atendendo outras perguntas. "
                    "Aguarde e tente novamente."
                ),
                visualization=Visualization(
                    type="table", title="Execução indisponível", available_types=["table"]
                ),
                operational_code="rate_limited",
            )
        )
    else:
        st.session_state.active_execution_id = execution_id
    st.rerun()


if __name__ == "__main__":
    main()
