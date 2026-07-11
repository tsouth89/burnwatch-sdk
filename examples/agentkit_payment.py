"""Coinbase AgentKit-style spend mirroring with Burnwatch (offline).

AgentKit agents often pay via wallets / x402 after tool actions. Burnwatch stays observe-only:
record metadata after the payment succeeds — never wrap the signing path.

This example uses a fake wallet action so it runs with no AgentKit install and no keys.
"""
from __future__ import annotations

from burnwatch import BurnwatchClient


class _FakeWalletAction:
    """Stand-in for an AgentKit tool result after a successful onchain / x402 payment."""

    amount = 0.002
    recipient = "api.weather.dev"
    resource = "GET /forecast"
    tx_hash = "0xabc123"


def after_agentkit_payment(bw: BurnwatchClient, *, agent_ref: str, action: _FakeWalletAction) -> None:
    bw.record(
        agent_ref=agent_ref,
        agent_name="agentkit-bot",
        amount=action.amount,
        recipient=action.recipient,
        resource=action.resource,
        rail="x402",
        currency="USDC",
        context={"tx_hash": action.tx_hash},
    )


if __name__ == "__main__":
    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_demo", enabled=False)
    after_agentkit_payment(bw, agent_ref="agentkit_demo", action=_FakeWalletAction())
    print("recorded AgentKit-shaped x402 payment (offline).")
    print("Wire after_agentkit_payment() after your real wallet/tool action succeeds.")
