"""x402 payment wrapper - one-line integration over any paid HTTP client.

Burnwatch does not ship an x402 transport; this module wraps *your* client and mirrors metadata
after each successful payment. Fail-open: recording errors never propagate to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from burnwatch.client import BurnwatchClient


def _extract_amount(result: Any, attr: str, fallback: float | None) -> float:
    if isinstance(result, dict):
        val = result.get(attr, result.get("amount"))
    else:
        val = getattr(result, attr, None)
        if val is None:
            val = getattr(result, "amount", None)
    if val is None:
        if fallback is None:
            return 0.0
        return float(fallback)
    return float(val)


@dataclass(frozen=True)
class PaymentMirror:
    """Normalized payment metadata passed to Burnwatch after an x402 call."""

    amount: float
    recipient: str
    resource: str | None = None
    currency: str = "USDC"
    rail: str = "x402"
    status: str = "paid"
    context: dict[str, Any] | None = None


class X402Monitor:
    """Wrap paid x402 calls and auto-mirror metadata to Burnwatch.

    Example::

        bw = BurnwatchClient(endpoint="https://burnwatch.example.com", token="bw_...")
        mon = X402Monitor(bw, agent_ref="agent_7f3c", agent_name="research-bot")

        # pass your real x402 client's get function
        resp = mon.paid_get(x402_client.get, "https://api.weather.dev/forecast", max_amount=llm_cost(1))
    """

    def __init__(
        self,
        client: BurnwatchClient,
        *,
        agent_ref: str,
        agent_name: str | None = None,
    ) -> None:
        self._client = client
        self._agent_ref = agent_ref
        self._agent_name = agent_name

    def mirror(self, payment: PaymentMirror) -> None:
        """Record a completed payment explicitly."""
        self._client.record(
            agent_ref=self._agent_ref,
            agent_name=self._agent_name,
            amount=payment.amount,
            recipient=payment.recipient,
            resource=payment.resource,
            currency=payment.currency,
            rail=payment.rail,
            status=payment.status,
            context=payment.context,
        )

    def after_payment(
        self,
        result: Any,
        *,
        recipient: str,
        resource: str | None = None,
        amount_attr: str = "amount_paid",
        amount_fallback: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Mirror an already-completed payment; returns ``result`` unchanged."""
        self.mirror(
            PaymentMirror(
                amount=_extract_amount(result, amount_attr, amount_fallback),
                recipient=recipient,
                resource=resource,
                context=context,
            )
        )
        return result

    def paid_call(
        self,
        pay