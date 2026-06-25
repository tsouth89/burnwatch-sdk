"""Burnwatch integration example with Coinbase AgentKit.

This script demonstrates how to wrap AgentKit tools to record
blockchain transaction costs using the Burnwatch SDK.

Usage:
    BURNWATCH_ENDPOINT=http://localhost:8010 BURNWATCH_TOKEN=*** python examples/agentkit_example.py
"""
import os
import functools
from typing import Any, Callable

from burnwatch import BurnwatchClient


def burnwatch_tool_tracker(bw_client: BurnwatchClient, agent_ref: str, agent_name: str, 
                          resource_name: str, estimated_cost: float) -> Callable:
    """Decorator to track AgentKit tool execution costs."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute the actual tool
            result = func(*args, **kwargs)
            
            # Record the cost in Burnwatch
            bw_client.record(
                agent_ref=agent_ref,
                agent_name=agent_name,
                amount=estimated_cost,
                recipient="base.rpc",
                resource=resource_name
            )
            print(f"[Burnwatch] Recorded ${estimated_cost:.4f} for {resource_name}")
            
            return result
        return wrapper
    return decorator


# Mock AgentKit CDP Wallet Provider for demonstration
class MockCdpWalletProvider:
    def __init__(self):
        self.network = "base-sepolia"
        
    def request_faucet_funds(self) -> str:
        return "Transaction successful: 0xabc...123"
        
    def transfer(self, amount: float, to: str) -> str:
        return f"Transfer of {amount} ETH to {to} successful"


def main():
    endpoint = os.environ.get("BURNWATCH_ENDPOINT", "http://localhost:8010")
    token = os.environ.get("BURNWATCH_TOKEN", "demo_token")
    
    with BurnwatchClient(endpoint=endpoint, token=token) as bw:
        print("Setting up AgentKit with Burnwatch monitoring...")
        
        wallet = MockCdpWalletProvider()
        
        # In a real AgentKit setup, these would be LangChain tools wrapping CDP actions.
        # Here we mock the tools and apply our tracking decorator.
        
        @burnwatch_tool_tracker(bw, "cdp_agent", "AgentKit-Bot", "Faucet Request (L2)", 0.0005)
        def tool_request_faucet_funds() -> str:
            print("Executing faucet request on Base...")
            return wallet.request_faucet_funds()
            
        @burnwatch_tool_tracker(bw, "cdp_agent", "AgentKit-Bot", "ETH Transfer (L2)", 0.002)
        def tool_transfer(amount: float, to: str) -> str:
            print(f"Executing transfer of {amount} ETH to {to}...")
            return wallet.transfer(amount, to)

        # Simulate agent executing tools
        print("\nAgent executing task: Initializing wallet with faucet funds")
        res1 = tool_request_faucet_funds()
        print(f"Result: {res1}\n")
        
        print("Agent executing task: Paying external vendor")
        res2 = tool_transfer(0.01, "0x1234567890abcdef")
        print(f"Result: {res2}\n")
        
        print("Flushing Burnwatch events...")

if __name__ == "__main__":
    main()
