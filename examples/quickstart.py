"""Minimal Burnwatch SDK example.

    BURNWATCH_ENDPOINT=http://localhost:8010 BURNWATCH_TOKEN=bw_... python examples/quickstart.py
"""
import os

from burnwatch import BurnwatchClient, llm_cost

endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
token = os.environ["BURNWATCH_TOKEN"]

with BurnwatchClient(endpoint=endpoint, token=token) as bw:
    # pretend our agent just paid for a few API calls
    bw.record(agent_ref="agent_demo", agent_name="quickstart-bot", amount=llm_cost(2), rail="USD",
              recipient="api.weather.dev", resource="GET /forecast")
    bw.record(agent_ref="agent_demo", amount=llm_cost(4), rail="USD",
              recipient="search.exa.ai", resource="POST /search")
    bw.record(agent_ref="agent_demo", amount=llm_cost(1), rail="USD",
              recipient="rpc.base.org", resource="eth_call")
    print("recorded 3 payments; flushing on exit…")