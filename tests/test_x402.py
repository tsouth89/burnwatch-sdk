"""X402Monitor amount extraction + mirror."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from burnwatch.client import BurnwatchClient
from burnwatch.x402 import PaymentMirror, X402Monitor, _extract_amount


@pytest.fixture
def monitor(monkeypatch: pytest.MonkeyPatch) -> tuple[X402Monitor, list[dict[str, Any]]]:
    bw = BurnwatchClient(
        "https://example.test",
        "bw_test",
        enabled=False,  # no background thread; we only use record()
    )
    # enabled=False makes record a no-op — re-enable recording path only.
    bw._enabled = True
    recorded: list[dict[str, Any]] = []

    def capture(**kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr(bw, "record", capture)
    return X402Monitor(bw, agent_ref="agent_7f3c", agent_name="bot"), recorded


def test_extract_amount_from_dict_attr() -> None:
    assert _extract_amount({"amount_paid": 0.05}, "amount_paid", None) == 0.05


def test_extract_amount_from_dict_amount_fallback_key() -> None:
    assert _extract_amount({"amount": 0.12}, "amount_paid", None) == 0.12


def test_extract_amount_from_object() -> None:
    assert _extract_amount(SimpleNamespace(amount_paid=0.07), "amount_paid", None) == 0.07


def test_extract_amount_uses_fallback_when_missing() -> None:
    assert _extract_amount({}, "amount_paid", 0.01) == 0.01


def test_extract_amount_missing_without_fallback_is_zero() -> None:
    assert _extract_amount({}, "amount_paid", None) == 0.0


def test_after_payment_mirrors(
    monitor: tuple[X402Monitor, list[dict[str, Any]]],
) -> None:
    mon, recorded = monitor
    result = {"amount_paid": 0.03, "ok": True}
    out = mon.after_payment(result, recipient="api.weather.dev", resource="GET /f")
    assert out is result
    assert len(recorded) == 1
    assert recorded[0]["agent_ref"] == "agent_7f3c"
    assert recorded[0]["amount"] == 0.03
    assert recorded[0]["recipient"] == "api.weather.dev"
    assert recorded[0]["resource"] == "GET /f"


def test_mirror_payment_mirror(
    monitor: tuple[X402Monitor, list[dict[str, Any]]],
) -> None:
    mon, recorded = monitor
    mon.mirror(
        PaymentMirror(amount=1.5, recipient="0xabc", currency="USDC", context={"tx_hash": "0x1"})
    )
    assert recorded[0]["amount"] == 1.5
    assert recorded[0]["context"] == {"tx_hash": "0x1"}


def test_paid_get_calls_fn_and_mirrors(
    monitor: tuple[X402Monitor, list[dict[str, Any]]],
) -> None:
    mon, recorded = monitor
    calls: list[tuple] = []

    def fake_get(url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((url, kwargs))
        return {"amount_paid": 0.02}

    out = mon.paid_get(fake_get, "https://api.weather.dev/f", max_amount=0.05)
    assert out["amount_paid"] == 0.02
    assert calls == [("https://api.weather.dev/f", {"max_amount": 0.05})]
    assert recorded[0]["amount"] == 0.02
    assert recorded[0]["recipient"] == "https://api.weather.dev/f"
