"""
Base State Classes for Agent State Management

This module provides the base State class and related utilities for managing
agent state using TypedDict and LangGraph annotations.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict, Annotated, TypeVar, get_type_hints
from datetime import datetime
from pydantic import BaseModel, Field

from langchain.schema import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langgraph.graph.message import add_messages

# Type variable for generic functions that work with state
StateType = TypeVar('StateType', bound='BaseState')


class BaseState(TypedDict, total=False):
    """
    Base state class for agents using TypedDict.
    
    TypedDict provides static typing benefits while keeping the dictionary interface.
    The 'total=False' means all fields are optional.
    """
    # Messages for conversation history, annotated to append rather than replace
    messages: Annotated[List[Dict[str, Any]], add_messages]
    
    # Metadata for storing arbitrary state information
    metadata: Dict[str, Any]
    
    # Thread ID for conversation identification (useful for persistence)
    thread_id: str
    
    # Agent configuration
    agent_type: str
    
    # Timestamp fields for tracking state changes
    created_at: float
    updated_at: float
    
    # Storage for key decisions or reasoning paths
    decisions: List[Dict[str, Any]]
    
    # Reference to external resources (e.g., document IDs, knowledge base entries)
    resources: List[Dict[str, Any]]


def create_empty_state() -> BaseState:
    """
    Create an empty state with default values.
    
    Returns:
        BaseState: A new state instance with initialized fields.
    """
    current_time = time.time()
    return {
        "messages": [],
        "metadata": {},
        "thread_id": str(uuid.uuid4()),
        "agent_type": "default",
        "created_at": current_time,
        "updated_at": current_time,
        "decisions": [],
        "resources": []
    }


def update_state_timestamp(state: StateType) -> StateType:
    """
    Update the timestamp of a state.
    
    Args:
        state: The state to update.
        
    Returns:
        The updated state with a new timestamp.
    """
    state["updated_at"] = time.time()
    return state


def add_message_to_state(
    state: StateType, 
    content: str, 
    role: str = "human",
    additional_kwargs: Optional[Dict[str, Any]] = None
) -> StateType:
    """
    Add a message to the state's message history.
    
    Args:
        state: The state to update.
        content: The message content.
        role: The message role ("human", "ai", or "system").
        additional_kwargs: Additional message metadata.
        
    Returns:
        The updated state with the new message.
    """
    # Ensure messages exist
    if "messages" not in state:
        state["messages"] = []
    
    # Create message dictionary
    message = {
        "role": role,
        "content": content
    }
    
    # Add additional kwargs if provided
    if additional_kwargs:
        message["additional_kwargs"] = additional_kwargs
    
    # Add to messages and update timestamp
    if "messages" in state:
        new_messages = state["messages"] + [message]
        state = {**state, "messages": new_messages}
    else:
        state = {**state, "messages": [message]}
    
    return update_state_timestamp(state)


def add_decision_to_state(
    state: StateType,
    decision: str,
    reasoning: Optional[str] = None,
    action: Optional[str] = None
) -> StateType:
    """
    Add a decision to the state's decision history.
    
    Args:
        state: The state to update.
        decision: The decision made.
        reasoning: The reasoning behind the decision.
        action: The action taken based on the decision.
        
    Returns:
        The updated state with the new decision.
    """
    # Ensure decisions exist
    if "decisions" not in state:
        state["decisions"] = []
    
    # Create decision dictionary
    decision_entry = {
        "decision": decision,
        "timestamp": time.time(),
    }
    
    # Add optional fields if provided
    if reasoning:
        decision_entry["reasoning"] = reasoning
    if action:
        decision_entry["action"] = action
    
    # Add to decisions and update timestamp
    if "decisions" in state:
        new_decisions = state["decisions"] + [decision_entry]
        state = {**state, "decisions": new_decisions}
    else:
        state = {**state, "decisions": [decision_entry]}
    
    return update_state_timestamp(state)


def update_metadata(
    state: StateType,
    key: str,
    value: Any
) -> StateType:
    """
    Update a specific metadata field in the state.
    
    Args:
        state: The state to update.
        key: The metadata key to update.
        value: The new value.
        
    Returns:
        The updated state with the new metadata.
    """
    # Ensure metadata exists
    if "metadata" not in state:
        state["metadata"] = {}
    
    # Update metadata and overall state
    new_metadata = {**state.get("metadata", {}), key: value}
    state = {**state, "metadata": new_metadata}
    
    return update_state_timestamp(state)


def format_state_for_prompt(state: BaseState) -> str:
    """
    Format the state into a string representation for including in prompts.
    
    Args:
        state: The state to format.
        
    Returns:
        A string representation of relevant state information.
    """
    prompt_parts = ["# Current State\n"]
    
    # Add thread ID
    if "thread_id" in state:
        prompt_parts.append(f"Conversation ID: {state['thread_id']}\n")
    
    # Add important metadata if it exists
    if "metadata" in state and state["metadata"]:
        prompt_parts.append("\n## Context\n")
        for key, value in state["metadata"].items():
            if isinstance(value, (str, int, float, bool)):
                prompt_parts.append(f"{key}: {value}")
    
    # Add recent decisions if they exist
    if "decisions" in state and state["decisions"]:
        prompt_parts.append("\n## Recent Decisions\n")
        # Only include the last 3 decisions to save tokens
        for decision in state["decisions"][-3:]:
            timestamp = datetime.fromtimestamp(decision["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            prompt_parts.append(f"- {decision['decision']} ({timestamp})")
    
    # Add message summary
    if "messages" in state and state["messages"]:
        message_count = len(state["messages"])
        prompt_parts.append(f"\n## Conversation History ({message_count} messages)\n")
        # Note: Actual messages are typically included separately in LLM requests
    
    return "\n".join(prompt_parts)


class AgentState(BaseState):
    """
    Extended state class for agents with additional typing information.
    
    This provides a more specific state structure for different agent types.
    """
    # Agent-specific fields
    agent_name: str
    agent_role: str
    agent_goal: str
    
    # Status fields
    status: str
    is_active: bool
    
    # Performance metrics
    success_count: int
    failure_count: int
    
    # Specialized memory fields
    working_memory: Dict[str, Any]
    context_window: List[Dict[str, Any]] 