"""Cooperative execution controls and a bounded, session-polled worker registry."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from data_assistant.contract import AssistantAnswer, Visualization

ResultT = TypeVar("ResultT")
ProgressCallback = Callable[["PublicPhase"], None]
Worker = Callable[["ExecutionControl"], AssistantAnswer]


class PublicPhase(StrEnum):
    """Closed vocabulary of progress messages safe to show to visitors."""

    UNDERSTANDING = "Entendendo a pergunta"
    SCHEMA = "Lendo a estrutura do banco"
    VALIDATING = "Validando a consulta"
    QUERYING = "Consultando o banco"
    CHECKING = "Conferindo o resultado"
    FORMATTING = "Preparando a resposta"


class ExecutionCancelledError(RuntimeError):
    """Internal signal used to unwind a graph after a cooperative stop request."""

    def __init__(self, *, may_have_consumed_quota: bool = False) -> None:
        self.may_have_consumed_quota = may_have_consumed_quota
        super().__init__("A execução foi interrompida pelo visitante.")


class ExecutionCapacityError(RuntimeError):
    """Raised when every bounded background worker is already occupied."""


class ExecutionControl:
    """Thread-safe cancellation and allow-listed progress for one graph run."""

    def __init__(self, on_progress: ProgressCallback | None = None) -> None:
        self.cancel_event = threading.Event()
        self._on_progress = on_progress
        self._lock = threading.Lock()
        self._provider_calls_started = 0
        self._may_have_consumed_quota = False

    def checkpoint(self) -> None:
        """Stop before any new node, query, or provider call after cancellation."""
        with self._lock:
            if self.cancel_event.is_set():
                raise ExecutionCancelledError(
                    may_have_consumed_quota=self._may_have_consumed_quota
                )

    @property
    def may_have_consumed_quota(self) -> bool:
        """Whether this run started any provider call before cancellation."""
        with self._lock:
            return self._may_have_consumed_quota

    def publish_progress(self, phase: PublicPhase) -> None:
        """Publish only one of the predefined operational messages."""
        self.checkpoint()
        safe_phase = PublicPhase(phase)
        if self._on_progress is not None:
            self._on_progress(safe_phase)
        self.checkpoint()

    def request_cancel(self) -> bool:
        """Set the stop signal once and report whether it was newly accepted."""
        with self._lock:
            if self.cancel_event.is_set():
                return False
            self._may_have_consumed_quota = self._provider_calls_started > 0
            self.cancel_event.set()
            return True

    def call_provider(self, operation: Callable[[], ResultT]) -> ResultT:
        """Run an in-flight HTTP call without killing it, then discard on stop."""
        with self._lock:
            if self.cancel_event.is_set():
                raise ExecutionCancelledError(
                    may_have_consumed_quota=self._may_have_consumed_quota
                )
            self._provider_calls_started += 1

        try:
            result = operation()
        except Exception:
            self.checkpoint()
            raise
        self.checkpoint()
        return result


def cancelled_answer(*, may_have_consumed_quota: bool = False) -> AssistantAnswer:
    """Build the neutral public contract without any partial SQL or query data."""
    warnings = (
        [
            "Uma chamada ao provedor já iniciada pode ter consumido cota; "
            "o resultado foi descartado."
        ]
        if may_have_consumed_quota
        else []
    )
    return AssistantAnswer(
        status="cancelled",
        response="Execução interrompida. Nenhum resultado parcial foi apresentado.",
        visualization=Visualization(
            type="table",
            title="Execução interrompida",
            available_types=["table"],
        ),
        warnings=warnings,
        operational_code="cancelled",
    )


def _worker_error_answer() -> AssistantAnswer:
    return AssistantAnswer(
        status="error",
        response="Não foi possível concluir a execução. Tente novamente.",
        visualization=Visualization(
            type="table",
            title="Falha operacional",
            available_types=["table"],
        ),
        operational_code="local_error",
    )


@dataclass
class _ExecutionHandle:
    control: ExecutionControl
    future: Future[AssistantAnswer] | None
    phase: PublicPhase
    created_at: float


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Safe state for one polling cycle; no worker object crosses into Streamlit."""

    phase: PublicPhase
    cancellation_requested: bool
    may_have_consumed_quota: bool
    done: bool


class ExecutionRegistry:
    """Bounded process-local worker pool addressed by opaque per-run identifiers."""

    def __init__(
        self,
        *,
        max_workers: int = 2,
        max_runtime_seconds: float = 180.0,
        completed_retention_seconds: float = 300.0,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers deve ser maior que zero")
        self._max_workers = max_workers
        self._max_runtime_seconds = max_runtime_seconds
        self._completed_retention_seconds = completed_retention_seconds
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="data-assistant"
        )
        self._handles: dict[str, _ExecutionHandle] = {}

    def start(self, worker: Worker) -> str:
        """Submit one run unless every bounded worker is already occupied."""
        with self._lock:
            now = time.monotonic()
            self._cleanup_locked(now)
            active = sum(
                handle.future is not None and not handle.future.done()
                for handle in self._handles.values()
            )
            if active >= self._max_workers:
                raise ExecutionCapacityError(
                    "O assistente está atendendo outras perguntas. Aguarde e tente novamente."
                )

            execution_id = secrets.token_urlsafe(24)
            control = ExecutionControl(
                on_progress=lambda phase: self._set_progress(execution_id, phase)
            )
            handle = _ExecutionHandle(
                control=control,
                future=None,
                phase=PublicPhase.SCHEMA,
                created_at=now,
            )
            self._handles[execution_id] = handle
            try:
                handle.future = self._pool.submit(worker, control)
            except Exception:
                self._handles.pop(execution_id, None)
                raise
            return execution_id

    def snapshot(self, execution_id: str) -> ExecutionSnapshot | None:
        """Return only allow-listed progress and lifecycle flags for polling."""
        with self._lock:
            self._cleanup_locked(time.monotonic())
            handle = self._handles.get(execution_id)
            if handle is None:
                return None
            future = handle.future
            return ExecutionSnapshot(
                phase=handle.phase,
                cancellation_requested=handle.control.cancel_event.is_set(),
                may_have_consumed_quota=handle.control.may_have_consumed_quota,
                done=future is None or future.done(),
            )

    def cancel(self, execution_id: str) -> bool:
        """Request cancellation for this opaque handle only."""
        with self._lock:
            handle = self._handles.get(execution_id)
            if handle is None or handle.future is None or handle.future.done():
                return False
            return handle.control.request_cancel()

    def consume(self, execution_id: str) -> AssistantAnswer | None:
        """Take a completed answer once and release its registry entry."""
        with self._lock:
            handle = self._handles.get(execution_id)
            if handle is None or handle.future is None or not handle.future.done():
                return None
            self._handles.pop(execution_id, None)
            future = handle.future

        try:
            return future.result()
        except ExecutionCancelledError as exc:
            return cancelled_answer(may_have_consumed_quota=exc.may_have_consumed_quota)
        except Exception:
            return _worker_error_answer()

    def shutdown(self) -> None:
        """Stop the pool; exposed for deterministic tests and process teardown."""
        with self._lock:
            for handle in self._handles.values():
                handle.control.request_cancel()
        self._pool.shutdown(wait=True, cancel_futures=True)

    def _set_progress(self, execution_id: str, phase: PublicPhase) -> None:
        with self._lock:
            handle = self._handles.get(execution_id)
            if handle is not None:
                handle.phase = phase

    def _cleanup_locked(self, now: float) -> None:
        stale: list[str] = []
        for execution_id, handle in self._handles.items():
            age = now - handle.created_at
            future = handle.future
            if future is None:
                continue
            if future.done() and age >= self._completed_retention_seconds:
                stale.append(execution_id)
            elif not future.done() and age >= self._max_runtime_seconds:
                handle.control.request_cancel()
        for execution_id in stale:
            self._handles.pop(execution_id, None)


EXECUTIONS = ExecutionRegistry()
