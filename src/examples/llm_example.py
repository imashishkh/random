"""
LLM Client Example

A simple example that demonstrates how to use the LLM client.
"""

import asyncio
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ..llm.client import create_llm_client
from ..utils.logging.logger import setup_logger


# Set up logger with debug level
setup_logger(log_level="DEBUG")


async def async_example():
    """Example of using the LLM client asynchronously."""
    print("\n=== Async Example ===")
    
    # Create LLM client
    client = create_llm_client(temperature=0.7, max_tokens=500)
    
    # Create messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides short, concise answers."},
        {"role": "user", "content": "What is LangChain and how does it relate to LangGraph?"}
    ]
    
    # Generate completion
    response = await client.acompletion(messages)
    
    # Print response
    print(f"\nResponse: {response['content']}")
    
    # Print usage if available
    if "usage" in response:
        print(f"\nToken usage: {response['usage']}")


def sync_example():
    """Example of using the LLM client synchronously."""
    print("\n=== Sync Example ===")
    
    # Create LLM client
    client = create_llm_client(model="gpt-3.5-turbo", temperature=0.5)
    
    # Create messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides short, concise answers."},
        {"role": "user", "content": "Explain the concept of AI agents in one sentence."}
    ]
    
    # Generate completion
    response = client.completion(messages)
    
    # Print response
    print(f"\nResponse: {response['content']}")
    
    # Print usage if available
    if "usage" in response:
        print(f"\nToken usage: {response['usage']}")


def streaming_example():
    """Example of using the LLM client with streaming."""
    print("\n=== Streaming Example ===")
    
    # Create LLM client with streaming enabled
    client = create_llm_client(streaming=True, temperature=0.7)
    
    # Create messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides detailed explanations."},
        {"role": "user", "content": "Explain how to use LangGraph for orchestrating multiple AI agents. Provide a simple example."}
    ]
    
    # Generate completion (streaming output will be printed to stdout)
    print("\nResponse (streaming):")
    response = client.completion(messages)
    
    # Print usage if available
    if "usage" in response:
        print(f"\nToken usage: {response['usage']}")


# Main function
async def main():
    """Run examples."""
    try:
        # Run examples
        await async_example()
        sync_example()
        streaming_example()
    except Exception as e:
        print(f"Error: {str(e)}")


# Run main function
if __name__ == "__main__":
    asyncio.run(main()) 