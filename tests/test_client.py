"""BurnwatchClient: record / flush / buffer behavior."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from burnwatch.client import BurnwatchClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BurnwatchClient:
    # Long flush interval so the background thread stays idle during tests.
    bw = BurnwatchClient(
        "https://example.test",
        "bw_test",
        flush_interval=3600,
        max_batch=2,
        max_buffer=4,
        timeout=0.5,
    )
    # Keep a no-op transport for fixture teardown: client.close() drains the buffer,
    # and monkeypatch undoes per-test stubs only after this fixture tears down.
    monkeypatch.setattr(bw, "_post", lambda _payload: None)
    yield bw
    bw.close()


def test_enabled_false_is_noop() -> None:
    bw = BurnwatchClient("https://example.test", "bw_test", enabled=False)
    assert bw._thread is None
    bw.record(agent_ref="a1", amount=1.0, recipient="payee")
    assert bw._buf == []
    bw.flush()  # must not raise
    bw.close()


def test_record_queues_event(client: BurnwatchClient, monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[dict[str, Any]] = []
    monkeypatch.setattr(client, "_post", lambda payload: posted.append(payload))

    ts = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    client.record(
        agent_ref="agent_1",
        amount=0.02,
        recipient="api.example.com",
        resource="GET /x",
        agent_name="bot",
        context={"tx_hash": "0xabc"},
        ts=ts,
    )
    assert len(client._buf) == 1
    event = client._buf[0]
    assert event["agent_ref"] == "agent_1"
    assert event["amount"] == 0.02
    assert event["recipient"] == "api.example.com"
    assert event["resource"] == "GET /x"
    assert event["agent_name"] == "bot"
    assert event["context"] == {"tx_hash": "0xabc"}
    assert event["ts"] == ts.isoformat()
    assert posted == []


def test_record_auto_flush_at_max_batch(
    client: BurnwatchClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list[dict[str, Any]] = []
    monkeypatch.setattr(client, "_post", lambda payload: posted.append(payload))

    client.record(agent_ref="a", amount=1.0, recipient="r1")
    assert posted == []
    client.record(agent_ref="a", amount=2.0, recipient="r2")  # hits max_batch=2
    assert len(posted) == 1
    assert len(posted[0]["events"]) == 2
    assert client._buf == []


def test_flush_requeues_on_failure(
    client: BurnwatchClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def flaky(payload: dict[str, Any]) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("backend down")

    monkeypatch.setattr(client, "_post", flaky)
    client.record(agent_ref="a", amount=1.0, recipient="r1")
    client.flush()
    assert len(client._buf) == 1  # re-queued
    assert client._buf[0]["recipient"] == "r1"

    client.flush()
    assert calls["n"] == 2
    assert client._buf == []


def test_flush_evicts_oldest_when_buffer_full(
    client: BurnwatchClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        client,
        "_post",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("down")),
    )

    # max_batch=2, max_buffer=4 — keep recording and failing flushes.
    for i in range(6):
        client.record(agent_ref="a", amount=float(i), recipient=f"r{i}")
        client.flush()

    recipients = [e["recipient"] for e in client._buf]
    # Newest max_buffer events retained after repeated failed re-queues.
    assert recipients == ["r2", "r3", "r4", "r5"]
