from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest

from data_assistant.errors import QuotaExceededError
from data_assistant.quota import QuotaStore


def test_reservations_persist_without_storing_questions_or_keys(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "quota.sqlite3"
    store = QuotaStore(path, day_provider=lambda: date(2026, 9, 22))
    assert store.acquire(2).remaining == 1
    assert QuotaStore(path, day_provider=lambda: date(2026, 9, 22)).acquire(2).remaining == 0
    with pytest.raises(QuotaExceededError):
        store.acquire(2)
    assert store.snapshot(2).used == 2
    assert path.read_bytes().find(b"OPENROUTER_API_KEY") == -1


def test_counter_resets_on_next_utc_day(tmp_path: Path) -> None:
    current = [date(2026, 9, 22)]
    store = QuotaStore(tmp_path / "quota.sqlite3", day_provider=lambda: current[0])
    store.acquire(1)
    store.mark_provider_exhausted()
    assert store.snapshot(1).remaining == 0

    current[0] = date(2026, 9, 23)
    assert store.snapshot(1).used == 0
    assert store.acquire(1).remaining == 0


def test_provider_exhaustion_blocks_further_shared_attempts(tmp_path: Path) -> None:
    store = QuotaStore(tmp_path / "quota.sqlite3")
    store.acquire(45)
    store.mark_provider_exhausted()
    with pytest.raises(QuotaExceededError):
        store.acquire(45)
    assert store.snapshot(45).provider_exhausted is True


def test_acquisition_is_atomic_across_threads(tmp_path: Path) -> None:
    path = tmp_path / "quota.sqlite3"
    store = QuotaStore(path)

    def attempt(_index: int) -> bool:
        try:
            store.acquire(5)
        except QuotaExceededError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(20)))
    assert sum(results) == 5
    assert store.snapshot(5).used == 5


def test_ledger_cannot_target_source_database(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"untouched")
    with pytest.raises(ValueError, match="separado"):
        QuotaStore(source, source_database=source)
    assert source.read_bytes() == b"untouched"
