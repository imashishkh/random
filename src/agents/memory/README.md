# Agent Memory System

This module provides a comprehensive memory system for intelligent agents, integrating both short-term and long-term memory capabilities.

## Overview

The memory system is composed of three main components:

1. **Short-Term Memory**: Handles recent conversation history and working memory.
2. **Long-Term Memory**: Provides persistent storage with semantic search capabilities.
3. **Integrated Memory**: Combines both systems with automatic memory consolidation.

## Features

- **Conversation History**: Store and retrieve conversation messages
- **Working Memory**: Key-value store for temporary information
- **Long-Term Storage**: Persistent memory with importance-based retention
- **Semantic Search**: Find relevant memories using natural language queries
- **Memory Consolidation**: Automatically transfer important information from short-term to long-term memory
- **Context Augmentation**: Enhance prompts with relevant memories

## Usage

```python
from src.agents.memory import AgentMemory

# Initialize the memory system
memory = AgentMemory(
    agent_id="my_agent",
    openai_api_key="your_openai_api_key",  # Optional, will use env var if not provided
    max_conversation_messages=100,
    consolidation_threshold=0.7  # Importance threshold for auto-consolidation
)

# Add messages to conversation
memory.add_message(
    content="You are a helpful assistant.",
    role="system",
    importance=0.9
)

memory.add_message(
    content="What's the weather like today?",
    role="user",
    importance=0.5
)

# Set working memory
memory.set_working_memory("user_location", "San Francisco")
memory.set_working_memory("current_task", "weather_inquiry")

# Get current conversation for LLM
messages = memory.get_llm_messages()

# Add facts to long-term memory
memory.add_to_long_term_memory(
    content="The user lives in San Francisco.",
    entry_type="fact",
    importance=0.8
)

# Search long-term memory
results = memory.search_long_term_memory(
    query="Where does the user live?",
    limit=3
)

# Augment a prompt with relevant memories
prompt = "Tell me about transportation options."
augmented_prompt = memory.augment_context_with_memories(prompt)

# Save memory to disk
memory.save()
```

## Module Structure

```
memory/
├── __init__.py
├── memory.py         # Main integrated memory system
├── short_term.py     # Short-term memory implementation
├── long_term.py      # Long-term memory implementation
└── examples/         # Usage examples
    └── memory_example.py
```

## Dependencies

- Python 3.7+
- OpenAI Python package (optional, for embeddings)
- NumPy (for vector operations)

## Example

See the `examples/memory_example.py` file for a complete usage example.

## Note on Embeddings

The long-term memory uses OpenAI embeddings for semantic search. If the OpenAI package is not available, it will fall back to a simple mock embedding system, but search quality will be significantly reduced. 