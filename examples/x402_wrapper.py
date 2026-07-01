"""x402 wrapper example - mirrors paid calls without touching the money path.

    BURNWATCH_ENDPOINT=https://app.burnwatch.dev \\
    BURNWATCH_TOKEN=bw_... \\
    python examples/x402_wrapper.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from burnwatch import BurnwatchClient, X402Monitor, llm_cost


@dataclass
class FakeX402Response:
    """Stand-in for a real x402 client response object."""

    amount_paid: float
    status_code: int = 200
    body: str = "ok"


class FakeX402Client:
    """Minimal fake - swap this for your real x402 HTTP client."""

    def get(self, url: str, *, max_amount: float) -> FakeX402Response:
        # pretend we paid up to max_amount for the resource
        return FakeX402Response(amount_paid=round(max_amount * 0.8, 6))


def main() -> None:
    endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
    token = os.environ["BURNWATCH_TOKEN"]
    x402 = FakeX402Client()

    with BurnwatchClient(endpoint=endpoint, token=token) as bw:
        mon = X402Monitor(bw, agent_ref="agent_demo", agent_name="x402-demo-bot")

        resp = mon.paid_get(x402.get, "https://api.weather.dev/forecast", max_amount=llm_cost(0.01, rail="weather", currency="USDC"))
        print(f"paid {resp.amount_paid} USDC - mirrored to Burnwatch")

        # manual seam (README style)
        raw = x402.get("https://search.exa.ai/query", max_amount=llm_cost(0.02, rail="search", currency="USDC"))
        mon.after_payment(raw, recipient="https://search.exa.ai/query", resource="GET /query")
        print("second payment mirrored via after_payment()")


if __name__ == "__main__":
    main()