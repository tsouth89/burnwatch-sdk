"""Watch your agent's OpenAI / Anthropic spend with Burnwatch.

Wrap the client once with monitor_llm and every chat call is mirrored to Burnwatch as a payment, so
the same drain / velocity / anomaly rules that watch x402 spend also catch a runaway API bill.
Costs are estimated from a built-in price table (override with set_prices).

This demo uses a stand-in client so it runs with no API key and no openai install. In real code:

    from openai import OpenAI
    from burnwatch import BurnwatchClient, monitor_llm

    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_...")
    client = monitor_llm(OpenAI(), bw, agent_ref="agent_7f3c", agent_name="research-bot")
    client.chat.completions.create(model="gpt-4o", messages=[...])   # spend auto-recorded
"""
from burnwatch import BurnwatchClient, llm_cost, monitor_llm


# --- a stand-in for an OpenAI client so this runs offline ---
class _Usage:
    prompt_tokens = 1200
    completion_tokens = 800


class _Resp:
    usage = _Usage()
    model = "gpt-4o"


class _Completions:
    def create(self, **kwargs):
        return _Resp()


class _Chat:
    completions = _Completions()


class _FakeOpenAI:
    chat = _Chat()


if __name__ == "__main__":
    bw = BurnwatchClient(endpoint="https://app.burnwatch.dev", token="bw_demo", enabled=False)
    client = monitor_llm(_FakeOpenAI(), bw, agent_ref="agent_7f3c", agent_name="research-bot")

    resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    print("call returned normally, model:", resp.model)
    print("estimated cost of this call: $", llm_cost(resp.model, resp.usage))
    print("With monitor_llm, that cost is recorded to Burnwatch on every call - no per-call code.")
