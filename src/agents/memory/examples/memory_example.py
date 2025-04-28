#!/usr/bin/env python3
"""
Memory System Example

This example demonstrates how to use the AgentMemory system,
which integrates short-term and long-term memory components.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add the parent directory to the path so we can import the modules
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from .memory.memory import AgentMemory
from ....utils.logging.logger import get_logger, configure_logging

# Configure logging
configure_logging(level="INFO")
logger = get_logger()


def main():
    """Run the memory system example."""
    print("\n==== AGENT MEMORY SYSTEM EXAMPLE ====\n")
    
    # Initialize the memory system
    agent_id = "example_agent"
    memory = AgentMemory(
        agent_id=agent_id,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        max_conversation_messages=10,
        consolidation_threshold=0.7
    )
    
    print(f"Initialized memory system for agent: {agent_id}")
    
    # Example 1: Add messages to conversation history
    print("\n--- Example 1: Add Messages ---")
    system_msg_id = memory.add_message(
        content="You are a helpful AI assistant.",
        role="system",
        importance=0.9
    )
    
    user_msg_id = memory.add_message(
        content="Can you help me understand how neural networks work?",
        role="user", 
        importance=0.7
    )
    
    assistant_msg_id = memory.add_message(
        content="Neural networks are computational models inspired by the human brain. "
                "They consist of layers of interconnected nodes or 'neurons' that process information.",
        role="assistant",
        importance=0.8
    )
    
    print("Added 3 messages to conversation history")
    
    # Example 2: Get conversation history
    print("\n--- Example 2: Get Conversation History ---")
    messages = memory.get_conversation_history()
    print(f"Retrieved {len(messages)} messages from conversation history:")
    for msg in messages:
        print(f"  [{msg.role}]: {msg.content[:50]}...")
    
    # Example 3: Get LLM-formatted messages
    print("\n--- Example 3: Get LLM Messages ---")
    llm_messages = memory.get_llm_messages()
    print(f"Retrieved {len(llm_messages)} messages in LLM format:")
    print(json.dumps(llm_messages, indent=2))
    
    # Example 4: Working memory operations
    print("\n--- Example 4: Working Memory Operations ---")
    memory.set_working_memory("current_topic", "neural networks")
    memory.set_working_memory("user_proficiency", "beginner")
    memory.set_working_memory("explanation_depth", "detailed")
    
    print("Set 3 items in working memory")
    
    topic = memory.get_working_memory("current_topic")
    proficiency = memory.get_working_memory("user_proficiency")
    print(f"Retrieved working memory: topic='{topic}', proficiency='{proficiency}'")
    
    all_working_memory = memory.get_all_working_memory()
    print(f"All working memory items: {json.dumps(all_working_memory, indent=2)}")
    
    # Example 5: Long-term memory operations
    print("\n--- Example 5: Long-term Memory Operations ---")
    fact1_id = memory.add_to_long_term_memory(
        content="Neural networks require large amounts of data for training.",
        entry_type="fact",
        importance=0.8
    )
    
    fact2_id = memory.add_to_long_term_memory(
        content="Deep learning is a subset of machine learning based on neural networks with many layers.",
        entry_type="fact",
        importance=0.9
    )
    
    experience_id = memory.add_to_long_term_memory(
        content="User asked about neural networks and seemed interested in practical applications.",
        entry_type="experience",
        importance=0.6,
        metadata={"user_interest": "practical_applications"}
    )
    
    print(f"Added 3 entries to long-term memory: {fact1_id[:8]}, {fact2_id[:8]}, {experience_id[:8]}")
    
    # Example 6: Search long-term memory
    print("\n--- Example 6: Search Long-term Memory ---")
    search_results = memory.search_long_term_memory(
        query="What are neural networks good for?",
        limit=2
    )
    
    print(f"Search results: {json.dumps(search_results, indent=2)}")
    
    # Example 7: Retrieve relevant memories for context
    print("\n--- Example 7: Retrieve Relevant Memories ---")
    context = "The user wants to understand how to train neural networks efficiently."
    memories = memory.retrieve_relevant_memories(context, limit=2)
    
    print(f"Retrieved {len(memories)} memories relevant to: '{context}'")
    for i, memory_item in enumerate(memories, 1):
        similarity = memory_item.get("similarity", 0)
        print(f"  {i}. [{memory_item['entry_type']}] {memory_item['content']} (relevance: {similarity:.2f})")
    
    # Example 8: Augment context with memories
    print("\n--- Example 8: Augment Context with Memories ---")
    prompt = "Explain how to train neural networks for a beginner."
    augmented_prompt = memory.augment_context_with_memories(
        context=prompt,
        limit=2,
        entry_types=["fact"]
    )
    
    print(f"Original prompt: {prompt}")
    print(f"Augmented prompt: {augmented_prompt}")
    
    # Example 9: Memory statistics
    print("\n--- Example 9: Memory Statistics ---")
    stats = memory.get_stats()
    print(f"Memory statistics: {json.dumps(stats, indent=2)}")
    
    # Example 10: Save memory to disk
    print("\n--- Example 10: Save Memory to Disk ---")
    saved = memory.save()
    print(f"Memory saved successfully: {saved}")
    
    print("\nMemory system example completed!")


if __name__ == "__main__":
    main() 