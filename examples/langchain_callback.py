"""LangChain-style spend capture with Burnwatch (offline).

Shows the callback pattern people copy into LangChain apps. Uses a stand-in LLM result so
this runs with no langchain / openai install and no API key.

In a real LangChain app, attach the same handler via ``callbacks=[...]`` on the model, and
prefer ``llm_cost(model, usage)`` over hand-rolled pricing.

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[BurnwatchSpendCallback(bw, ...)])
"""
from __future__ import annotations

from typing import Any

from burnwatch import BurnwatchClient, llm_cost


class BurnwatchSpendCallback:
    """Minimal stand-in for a LangChain ``BaseCallbackHandler.on_llm_end``.

    Real LangChain handlers receive an ``LLMResult``; here we accept the same shape as a
    plain dict so the example stays stdlib-only.
    """

    def __init__(
        self,
        bw: BurnwatchClient,
        *,
        agent_ref: str,
        agent_name: str | None = None,
    ) -> None:
        self.bw = bw
        self.agent_ref = agent_ref
        self.agent_name = agent_name

    def on_llm_end(self, llm_output: dict[str, Any]) -> None:
        usage = llm_output.get("token_usage")
        model = str(llm_output.get("model_name") or "gpt-4o-mini")
        cost = llm_cost(model, usage)
        if cost is None:
            return
        # LLM spend is USD API bill spend — not x402/USDC.
        self.bw.record(
            agent_ref=self.agent_ref,
            agent_name=self.agent_name,
            amount=cost,
            recipient=model,
            rail="openai" if model.startswith(("gpt", "o1", "o3", "o4")) else "llm",
            currency="USD",
            resource=f"chat.completions ({model})",
        )


if __name__ == "__main__":
    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_demo", enabled=False)
    cb = BurnwatchSpendCallback(bw, agent_ref="lc_demo", agent_name="LangChain-Agent")

    # Fake what LangChain puts in LLMResult.llm_output after a chat call.
    fake_llm_output = {
        "model_name": "gpt-4o-mini",
        "token_usage": {"prompt_tokens": 800, "completion_tokens": 200},
    }
    cb.on_llm_end(fake_llm_output)

    cost = llm_cost("gpt-4o-mini", fake_llm_output["token_usage"])
    print(f"recorded estimated LLM spend: ${cost}")
    print("In LangChain, wire BurnwatchSpendCallback via model callbacks=[...].")
