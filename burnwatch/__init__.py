"""Burnwatch SDK - observe-only spend mirroring for AI agents.

Wrap your agent's payment client, call ``record()`` after each payment, and Burnwatch watches the
metadata for drains, overspends, and unknown counterparties. It never holds your keys or funds and
never sits in the payment path: mirroring is async, batched, and fail-open - if Burnwatch is
unreachable, your agent keeps paying as normal.

    from burnwatch import BurnwatchClient

    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_...")
    # ... after your agent makes an x402 payment ...
    bw.record(agent_ref="agent_7f3c", amount=0.002, recipient="api.weather.dev", resource="GET /forecast")
    bw.close()  # or use `with BurnwatchClient(...) as bw:`
"""
from burnwatch.client import BurnwatchClient
from burnwatch.llm import llm_cost, monitor_llm, set_prices
from burnwatch.x402 import PaymentMirror, X402Monitor

__all__ = [
    "BurnwatchClient",
    "X402Monitor",
    "PaymentMirror",
    "monitor_llm",
    "llm_cost",
    "set_prices",
]
__version__ = "0.2.0"
