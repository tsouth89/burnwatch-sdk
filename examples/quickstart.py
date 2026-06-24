"""Minimal Burnwatch SDK example.

    BURNWATCH_ENDPOINT=http://localhost:8010 BURNWATCH_TOKEN=bw_... python examples/quickstart.py
"""
import os

from burnwatch import BurnwatchClient

endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
token = os.environ["BURNWATCH_TOKEN"]

with BurnwatchClient(endpoint=endpoint, token=token) as bw:
    # pretend our agent just paid for a few API calls
    bw.record(agent_ref="agent_demo", agent_name="quickstart-bot", amount=0.002,
              recipient="api.weather.dev", resource="GET /forecast")
    bw.record(agent_ref="agent_demo", amount=0.004, recipient="search.exa.ai", resource="POST /search")
    bw.record(agent_ref="agent_demo", amount=0.001, recipient="rpc.base.org", resource="eth_call")
    print("recorded 3 payments; flushing on exit…")
