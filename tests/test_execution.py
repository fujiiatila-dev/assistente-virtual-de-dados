from __future__ import annotations

import threading
import time

import pytest

from data_assistant.contract import AssistantAnswer, Visualization
from data_assistant.execution import (
    ExecutionCancelledError,
    ExecutionCapacityError,
    ExecutionControl,
    ExecutionRegistry,
    PublicPhase,
)


def _answer(response: str = "Concluído") -> AssistantAnswer:
    return AssistantAnswer(
        status="success",
        response=response,
        visualization=Visualization(type="table", title="Resultado"),
    )


def _wait_until_done(registry: ExecutionRegistry, execution_id: str) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = registry.snapshot(execution_id)
        if snapshot is None or snapshot.done:
            return
        time.sleep(0.01)
    pytest.fail("A execução não terminou dentro do limite do teste")


def test_cancellation_before_work_and_progress_use_only_public_phases() -> None:
    published: list[PublicPhase] = []
    control = ExecutionControl(on_progress=published.append)
    control.request_cancel()

    with pytest.raises(ExecutionCancelledError):
        control.publish_progress(PublicPhase.QUERYING)
    assert published == []

    uncancelled = ExecutionControl()
    with pytest.raises(ValueError):
        uncancelled.publish_progress("SQL privado")  # type: ignore[arg-type]


def test_in_flight_provider_result_is_discarded_after_cancellation() -> None:
    control = ExecutionControl()
    provider_started = threading.Event()
    provider_release = threading.Event()
    results: list[str] = []
    errors: list[ExecutionCancelledError] = []

    def call() -> None:
        try:
            value = control.call_provider(
                lambda: (provider_started.set(), provider_release.wait(2), "conteúdo privado")[-1]
            )
            results.append(value)
        except ExecutionCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=call)
    worker.start()
    assert provider_started.wait(1)
    assert control.request_cancel()
    provider_release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert results == []
    assert len(errors) == 1
    assert errors[0].may_have_consumed_quota is True


def test_execution_handles_are_isolated_and_released_after_consumption() -> None:
    registry = ExecutionRegistry(max_workers=2)
    first_started = threading.Event()
    first_release = threading.Event()

    def slow(control: ExecutionControl) -> AssistantAnswer:
        control.publish_progress(PublicPhase.VALIDATING)
        first_started.set()
        first_release.wait(2)
        control.checkpoint()
        return _answer("não deve ser exibida")

    try:
        first_id = registry.start(slow)
        assert first_started.wait(1)
        second_id = registry.start(lambda _control: _answer("sessão independente"))
        assert first_id != second_id

        first_snapshot = registry.snapshot(first_id)
        assert first_snapshot is not None
        assert first_snapshot.phase is PublicPhase.VALIDATING
        assert registry.cancel(first_id)
        cancelled_snapshot = registry.snapshot(first_id)
        assert cancelled_snapshot is not None and cancelled_snapshot.cancellation_requested

        _wait_until_done(registry, second_id)
        second_answer = registry.consume(second_id)
        assert second_answer is not None
        assert second_answer.response == "sessão independente"

        first_release.set()
        _wait_until_done(registry, first_id)
        first_answer = registry.consume(first_id)
        assert first_answer is not None
        assert first_answer.status == "cancelled"
        assert first_answer.data == []
        assert first_answer.queries == []
        assert registry.snapshot(first_id) is None
    finally:
        first_release.set()
        registry.shutdown()


def test_registry_rejects_work_beyond_its_concurrency_bound() -> None:
    registry = ExecutionRegistry(max_workers=1)
    started = threading.Event()
    release = threading.Event()

    def worker(control: ExecutionControl) -> AssistantAnswer:
        started.set()
        release.wait(2)
        control.checkpoint()
        return _answer()

    try:
        execution_id = registry.start(worker)
        assert started.wait(1)
        with pytest.raises(ExecutionCapacityError, match="atendendo outras perguntas"):
            registry.start(lambda _control: _answer())
        assert registry.cancel(execution_id)
        release.set()
        _wait_until_done(registry, execution_id)
        assert registry.consume(execution_id) is not None
        assert registry.start(lambda _control: _answer())
    finally:
        release.set()
        registry.shutdown()
