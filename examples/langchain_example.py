"""Burnwatch integration example with LangChain.

This script demonstrates how to wrap a LangChain LLM or Tool to record
costs using the Burnwatch SDK.

Usage:
    BURNWATCH_ENDPOINT=http://localhost:8010 BURNWATCH_TOKEN=bw_... OPENAI_API_KEY=sk-... python examples/langchain_example.py
"""
import os
import time
from typing import Any, Dict, List, Optional

from burnwatch import BurnwatchClient, llm_cost
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


class BurnwatchCallbackHandler(BaseCallbackHandler):
    """Callback Handler that logs token usage to Burnwatch."""
    
    def __init__(self, bw_client: BurnwatchClient, agent_ref: str, agent_name: str,
                 rail: str = "usd", currency: str = "USD"):
        self.bw = bw_client
        self.agent_ref = agent_ref
        self.agent_name = agent_name
        self.rail = rail
        self.currency = currency

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        try:
            if not response.llm_output or "token_usage" not in response.llm_output:
                return
            
            usage = response.llm_output["token_usage"]
            model_name = response.llm_output.get("model_name", "gpt-4o-mini")
            
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            # Calculate cost using burnwatch's llm_cost helper (replaces hardcoded prices)
            cost = llm_cost(model=model_name, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
            
            if cost > 0:
                self.bw.record(
                    agent_ref=self.agent_ref,
                    agent_name=self.agent_name,
                    amount=cost,
                    rail=self.rail,
                    currency=self.currency,
                    recipient="api.openai.com",
                    resource=f"POST /v1/chat/completions ({model_name})"
                )
                print(f"[Burnwatch Callback] Recorded ${cost:.6f} for {prompt_tokens + completion_tokens} tokens")
                
        except Exception as e:
            print(f"Error in BurnwatchCallbackHandler: {e}")


def main():
    endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
    token = os.environ.get("BURNWATCH_TOKEN", "demo_token")
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Note: OPENAI_API_KEY not set. This example requires a valid OpenAI API key to run.")
        print("If you just want to see the code, check out the BurnwatchCallbackHandler class.")
        return

    print("Initializing Burnwatch client and LangChain LLM...")
    with BurnwatchClient(endpoint=endpoint, token=token) as bw:
        bw_callback = BurnwatchCallbackHandler(
            bw_client=bw, 
            agent_ref="lc_demo", 
            agent_name="LangChain-Agent"
        )
        
        # Initialize the chat model with the callback
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            callbacks=[bw_callback],
            temperature=0
        )
        
        print("Sending request to LLM...")
        message = HumanMessage(content="Explain the concept of quantum entanglement in exactly two sentences.")
        
        # The callback will automatically record the cost when this completes
        response = llm.invoke([message])
        
        print("\nLLM Response:")
        print(response.content)
        print("\nFlushing Burnwatch events...")
        # The context manager automatically calls flush() on exit


if __name__ == "__main__":
    main()
