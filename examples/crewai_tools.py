"""CrewAI-style spend capture with Burnwatch (offline).

CrewAI agents usually burn money two ways: LLM calls and paid tools. This example shows both
without importing crewai — so it runs with no API key and no framework install.

In a real CrewAI app:
  * LLM: attach a LangChain callback (see langchain_callback.py) or wrap the LLM client with
    ``monitor_llm``.
  * Tools: call ``bw.record(...)`` inside the tool body after the paid call succeeds.
"""
from __future__ import annotations

from burnwatch import BurnwatchClient, llm_cost


def record_llm_turn(bw: BurnwatchClient, *, agent_ref: str, agent_name: str, model: str, usage: dict) -> None:
    cost = llm_cost(model, usage)
    if cost is None:
        return
    bw.record(
        agent_ref=agent_ref,
        agent_name=agent_name,
        amount=cost,
        recipient=model,
        rail="openai",
        currency="USD",
        resource=f"crewai.llm ({model})",
    )


def paid_search_tool(bw: BurnwatchClient, *, agent_ref: str, agent_name: str, query: str) -> str:
    """Stand-in for a CrewAI ``@tool`` that hits a paid search API."""
    # After the real HTTP call succeeds, mirror the fee — never in the money path before pay.
    bw.record(
        agent_ref=agent_ref,
        agent_name=agent_name,
        amount=0.01,
        recipient="api.search.provider",
        rail="http",
        currency="USD",
        resource="GET /search",
        # Never put raw query text in context — it can contain PII/secrets.
        context={"query_chars": len(query)},
    )
    return f"results for: {query}"


if __name__ == "__main__":
    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_demo", enabled=False)

    record_llm_turn(
        bw,
        agent_ref="crew_demo",
        agent_name="Researcher",
        model="gpt-4o-mini",
        usage={"prompt_tokens": 500, "completion_tokens": 120},
    )
    print(paid_search_tool(bw, agent_ref="crew_demo", agent_name="Researcher", query="x402 agents"))
    print("recorded LLM + tool spend for a CrewAI-shaped turn (offline).")
