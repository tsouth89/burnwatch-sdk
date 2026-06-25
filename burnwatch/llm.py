"""Auto-capture LLM / API spend (OpenAI, Anthropic, and compatible) into Burnwatch.

Wrap your client once and every chat/completion call is mirrored to Burnwatch as a payment, so the
same drain, velocity, and anomaly rules that watch x402 spend also watch your API bill - a runaway
loop that burns $900 of tokens overnight trips the exact same alerts as a wallet drain.

Stdlib-only and duck-typed: it never imports openai or anthropic. It reads the token usage off
whatever response your client returns and prices it from a built-in table (override via set_prices).

    from burnwatch import BurnwatchClient, monitor_llm

    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_...")
    client = monitor_llm(OpenAI(), bw, agent_ref="agent_7f3c")
    client.chat.completions.create(model="gpt-4o", messages=[...])   # spend auto-recorded

Captures sync, non-streaming calls. For streaming or async, call llm_cost() yourself and pass it to
bw.record(). Prices are approximate and change often - keep PRICES current or use set_prices().
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("burnwatch")

# USD per 1,000,000 tokens, as (input, output). Approximate; override with set_prices().
PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
}


def set_prices(prices: dict[str, tuple[float, float]]) -> None:
    """Merge in or override model prices (USD per 1M tokens, as (input, output))."""
    PRICES.update(prices)


def _match_price(model: str) -> tuple[float, float] | None:
    if model in PRICES:
        return PRICES[model]
    # prefix match so dated snapshots resolve (gpt-4o-2024-08-06, claude-3-5-sonnet-20241022)
    for key, price in PRICES.items():
        if model.startswith(key):
            return price
    return None


def _tokens(usage: Any) -> tuple[int, int]:
    """(input, output) tokens from an OpenAI- or Anthropic-shaped usage object or dict."""
    def get(*names: str) -> int:
        for n in names:
            v = usage.get(n) if isinstance(usage, dict) else getattr(usage, n, None)
            if v is not None:
                return int(v)
        return 0
    return get("prompt_tokens", "input_tokens"), get("completion_tokens", "output_tokens")


def llm_cost(model: str, usage: Any) -> float | None:
    """USD cost of one call, or None if the model's price is unknown."""
    price = _match_price(model)
    if price is None or usage is None:
        return None
    in_tok, out_tok = _tokens(usage)
    return round((in_tok * price[0] + out_tok * price[1]) / 1_000_000, 6)


def _provider(model: str) -> str:
    if model.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if model.startswith("claude"):
        return "anthropic"
    return "llm"


def _record(bw: Any, agent_ref: str, agent_name: str | None, result: Any, kwargs: dict) -> None:
    """Best-effort: pull usage + model off a response and mirror the cost. Never raises."""
    try:
        usage = result.get("usage") if isinstance(result, dict) else getattr(result, "usage", None)
        if usage is None:
            return  # not an LLM response (e.g. a sub-resource or a non-usage call)
        model = (result.get("model") if isinstance(result, dict) else getattr(result, "model", None)) \
            or kwargs.get("model")
        if not model:
            return
        cost = llm_cost(model, usage)
        if cost is None:
            log.debug("burnwatch: no price for model %s; not recording. add it via set_prices()", model)
            return
        bw.record(
            agent_ref=agent_ref,
            agent_name=agent_name,
            amount=cost,
            recipient=model,
            rail=_provider(model),
            currency="USD",
        )
    except Exception as exc:  # noqa: BLE001 - never break the caller's LLM call
        log.debug("burnwatch: llm spend capture failed: %s", exc)


_PRIMITIVES = (str, bytes, int, float, bool, type(None), list, tuple, dict, set)


class _Proxy:
    """Transparent proxy over an LLM client. Forwards every attribute and call unchanged, but when a
    call returns a response carrying token usage, it records the priced spend to Burnwatch."""

    def __init__(self, target: Any, bw: Any, agent_ref: str, agent_name: str | None) -> None:
        self._t = target
        self._bw = bw
        self._ref = agent_ref
        self._name = agent_name

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._t, name)
        if callable(attr) and not isinstance(attr, type):
            def wrapped(*a: Any, **k: Any) -> Any:
                result = attr(*a, **k)
                _record(self._bw, self._ref, self._name, result, k)
                return result
            return wrapped
        if isinstance(attr, _PRIMITIVES):
            return attr
        # a sub-resource (client.chat, .completions, .messages, ...) - keep proxying down to .create
        return _Proxy(attr, self._bw, self._ref, self._name)


def monitor_llm(client: Any, bw: Any, *, agent_ref: str, agent_name: str | None = None) -> Any:
    """Wrap an OpenAI/Anthropic-style client so its calls auto-record spend to Burnwatch.

    Returns a proxy you use exactly like the original client. The returned object is drop-in: no
    call sites change. Unknown models are skipped (add them with set_prices()).
    """
    return _Proxy(client, bw, agent_ref, agent_name)
