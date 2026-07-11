"""Client-side context redaction."""
from __future__ import annotations

from typing import Any

import pytest

from burnwatch.client import BurnwatchClient
from burnwatch.redact import dangerous_context_keys, scrub_context


def test_scrub_context_drops_denylisted_keys() -> None:
    cleaned = scrub_context(
        {
            "tx_hash": "0xabc",
            "private_key": "0xdead",
            "Secret": "shh",
            "AUTHORIZATION": "Bearer x",
            "agent_note": "ok",
        }
    )
    assert cleaned == {"tx_hash": "0xabc", "agent_note": "ok"}


def test_scrub_context_drops_bw_prefix_keys() -> None:
    assert scrub_context({"_bw": {"x": 1}, "tx_hash": "0x1"}) == {"tx_hash": "0x1"}
    assert scrub_context({"_bw_meta": "nope"}) is None


def test_scrub_context_empty_and_none() -> None:
    assert scrub_context(None) is None
    assert scrub_context({}) is None
    assert scrub_context({"mnemonic": "twelve words"}) is None


def test_dangerous_context_keys_sorted_case_insensitive() -> None:
    keys = dangerous_context_keys({"tx_hash": "0x1", "Private_Key": "x", "seed": "y"})
    assert keys == ["Private_Key", "seed"]
    assert dangerous_context_keys(None) == []
    assert dangerous_context_keys({"ok": 1}) == []


def test_record_scrubs_context_before_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bw = BurnwatchClient(
        "https://example.test",
        "bw_test",
        flush_interval=3600,
        max_batch=10,
        timeout=0.5,
    )
    monkeypatch.setattr(bw, "_post", lambda _payload: None)
    try:
        bw.record(
            agent_ref="a1",
            amount=1.0,
            recipient="payee",
            context={
                "tx_hash": "0xabc",
                "private_key": "should-not-leave-process",
                "signature": "0xsig",
            },
        )
        assert len(bw._buf) == 1
        assert bw._buf[0]["context"] == {"tx_hash": "0xabc"}
    finally:
        bw.close()


def test_record_omits_context_when_fully_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bw = BurnwatchClient(
        "https://example.test",
        "bw_test",
        flush_interval=3600,
        max_batch=10,
        timeout=0.5,
    )
    monkeypatch.setattr(bw, "_post", lambda _payload: None)
    try:
        bw.record(
            agent_ref="a1",
            amount=1.0,
            recipient="payee",
            context={"secret": "x", "mnemonic": "y"},
        )
        assert "context" not in bw._buf[0]
    finally:
        bw.close()


def test_scrub_does_not_walk_nested_dicts() -> None:
    # Same contract as backend: only top-level keys are filtered.
    nested: dict[str, Any] = {"ok": {"private_key": "nested"}}
    assert scrub_context(nested) == nested
