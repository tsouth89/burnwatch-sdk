"""Burnwatch integration example with CrewAI.

This script demonstrates how to wrap CrewAI Agents to record LLM costs
and tool execution costs using the Burnwatch SDK.

Usage:
    BURNWATCH_ENDPOINT=http://localhost:8010 BURNWATCH_TOKEN=*** OPENAI_API_KEY=*** python examples/crewai_example.py
"""
import os
from typing import Any, Dict

from burnwatch import BurnwatchClient
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


# Reuse the LangChain callback handler since CrewAI uses LangChain under the hood
class BurnwatchCallbackHandler(BaseCallbackHandler):
    """Callback Handler that logs token usage to Burnwatch."""
    
    def __init__(self, bw_client: BurnwatchClient, agent_ref: str, agent_name: str):
        self.bw = bw_client
        self.agent_ref = agent_ref
        self.agent_name = agent_name
        # Approximate pricing (in USD)
        self.prices = {
            "gpt-4o-mini": {"prompt": 0.150 / 1_000_000, "completion": 0.600 / 1_000_000}
        }

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            if not response.llm_output or "token_usage" not in response.llm_output:
                return
            
            usage = response.llm_output["token_usage"]
            model_name = response.llm_output.get("model_name", "gpt-4o-mini")
            
            cost = (usage.get("prompt_tokens", 0) * self.prices.get(model_name, self.prices["gpt-4o-mini"])["prompt"] +
                    usage.get("completion_tokens", 0) * self.prices.get(model_name, self.prices["gpt-4o-mini"])["completion"])
            
            if cost > 0:
                self.bw.record(
                    agent_ref=self.agent_ref,
                    agent_name=self.agent_name,
                    amount=cost,
                    recipient="api.openai.com",
                    resource=f"POST /v1/chat/completions ({model_name})"
                )
                print(f"[Burnwatch Callback] Recorded ${cost:.6f} for {self.agent_name}")
        except Exception:
            pass


def main():
    endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
    token = os.environ.get("BURNWATCH_TOKEN", "demo_token")
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Note: OPENAI_API_KEY not set. This example requires a valid OpenAI API key to run.")
        return

    with BurnwatchClient(endpoint=endpoint, token=token) as bw:
        print("Setting up CrewAI with Burnwatch monitoring...")
        
        # We define a custom tool that also logs its cost
        @tool("Search Tool")
        def search_tool(query: str) -> str:
            """Simulates a search tool that costs money."""
            # Record the tool cost directly to Burnwatch
            bw.record(
                agent_ref="crewai_demo",
                agent_name="Researcher",
                amount=0.01,  # Fake 1 cent per search
                recipient="api.search.provider",
                resource="GET /search"
            )
            print(f"[Burnwatch Tool] Recorded $0.010000 for Search Tool execution")
            return f"Search results for: {query} (simulation)"

        # Initialize LLMs with the Burnwatch callback
        researcher_llm = ChatOpenAI(
            model="gpt-4o-mini",
            callbacks=[BurnwatchCallbackHandler(bw, "crewai_demo", "Researcher")]
        )
        
        writer_llm = ChatOpenAI(
            model="gpt-4o-mini",
            callbacks=[BurnwatchCallbackHandler(bw, "crewai_demo", "Writer")]
        )

        # Define Agents
        researcher = Agent(
            role='Senior Researcher',
            goal='Uncover groundbreaking technologies',
            backstory='Driven by curiosity, you are at the forefront of innovation.',
            verbose=False,
            allow_delegation=False,
            tools=[search_tool],
            llm=researcher_llm
        )

        writer = Agent(
            role='Tech Content Strategist',
            goal='Craft compelling content on tech advancements',
            backstory='You are a renowned Content Strategist, known for your insightful articles.',
            verbose=False,
            allow_delegation=False,
            llm=writer_llm
        )

        # Define Tasks
        task1 = Task(
            description='Research the latest advancements in AI agents.',
            expected_output='A bullet list of 3 key advancements.',
            agent=researcher
        )

        task2 = Task(
            description='Write a short 1-paragraph summary based on the research.',
            expected_output='A short 1-paragraph summary.',
            agent=writer
        )

        # Create the Crew
        crew = Crew(
            agents=[researcher, writer],
            tasks=[task1, task2],
            process=Process.sequential,
            verbose=False
        )

        print("\nStarting the crew...")
        result = crew.kickoff()
        
        print("\nFinal Output:")
        print(result)
        print("\nFlushing Burnwatch events...")

if __name__ == "__main__":
    main()