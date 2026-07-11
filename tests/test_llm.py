"""llm_cost / price matching."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from burnwatch.llm import llm_cost, set_prices


def test_llm_cost_exact_model() -> None:
    # gpt-4o: $2.50 / $10.00 per 1M → 1000 in + 500 out = 0.0025 + 0.005 = 0.0075
    cost = llm_cost("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert cost == 0.0075


def test_llm_cost_prefix_match_dated_snapshot() -> None:
    cost = llm_cost(
        "gpt-4o-2024-08-06",
        {"prompt_tokens": 1_000_000, "completion_tokens": 0},
    )
    assert cost == 2.5


def test_llm_cost_anthropic_shaped_usage() -> None:
    usage = SimpleNamespace(input_tokens=1000, output_tokens=1000)
    cost = llm_cost("claude-3-5-sonnet", usage)
    # 1000 * 3.0 / 1e6 + 1000 * 15.0 / 1e6 = 0.018
    assert cost == 0.018


def test_llm_cost_unknown_model_returns_none() -> None:
    assert llm_cost("mystery-model-9", {"prompt_tokens": 10, "completion_tokens": 10}) is None


def test_llm_cost_none_usage_returns_none() -> None:
    assert llm_cost("gpt-4o", None) is None


def test_set_prices_override() -> None:
    from burnwatch import llm as llm_mod

    previous = llm_mod.PRICES.get("custom-model")
    llm_mod.PRICES["custom-model"] = (9.0, 9.0)
    set_prices({"custom-model": (1.0, 2.0)})
    try:
        cost = llm_cost("custom-model", {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
        assert cost == 3.0
    finally:
        if previous is None:
            llm_mod.PRICES.pop("custom-model", None)
        else:
            llm_mod.PRICES["custom-model"] = previous
