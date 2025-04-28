"""
Memory Summarization Utilities

This module provides utilities for summarizing agent memory, particularly
conversation history, to manage token usage effectively.
"""

import time
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from langchain.schema import AIMessage, HumanMessage, SystemMessage, BaseMessage

from .state.base import BaseState, StateType, update_state_timestamp
from ...llm.client import create_llm_client
from ...utils.logging.logger import get_logger

# Get logger
logger = get_logger()

# Estimated token counts for message overhead
ROLE_TOKEN_ESTIMATE = 4
BASIC_OVERHEAD_ESTIMATE = 10

# System prompt for summarization
SUMMARIZATION_SYSTEM_PROMPT = """
You are a helpful assistant that summarizes conversations. Your goal is to create a concise summary that:
1. Captures the key points and decisions
2. Preserves important context needed for future reference
3. Reduces token usage by eliminating redundant or less important information
4. Maintains the overall flow of the conversation
5. Highlights action items or follow-ups

Focus on facts, decisions, and conclusions rather than pleasantries or repetitive exchanges.
"""


def estimate_message_tokens(message: Dict[str, Any]) -> int:
    """
    Estimate the number of tokens in a message.
    
    This is a rough estimate based on word count, not a precise token count.
    For precise token counts, use a proper tokenizer.
    
    Args:
        message: The message to estimate tokens for.
        
    Returns:
        Estimated token count.
    """
    content = message.get("content", "")
    
    # Rough estimate based on words (4 chars ~ 1 token)
    word_count = len(content.split())
    token_estimate = word_count * 1.3  # Adjust for tokenization overhead
    
    # Add overhead for role and basic message structure
    token_estimate += ROLE_TOKEN_ESTIMATE + BASIC_OVERHEAD_ESTIMATE
    
    return int(token_estimate)


def estimate_conversation_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    Estimate the total number of tokens in a conversation.
    
    Args:
        messages: List of messages to estimate tokens for.
        
    Returns:
        Estimated total token count.
    """
    return sum(estimate_message_tokens(message) for message in messages)


def should_summarize(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    message_count_threshold: int = 30
) -> bool:
    """
    Determine if a conversation should be summarized.
    
    Args:
        messages: The conversation history.
        max_tokens: Maximum token threshold before summarizing.
        message_count_threshold: Message count threshold before summarizing.
        
    Returns:
        Whether the conversation should be summarized.
    """
    # Check message count first (faster than token estimation)
    if len(messages) >= message_count_threshold:
        return True
    
    # Estimate tokens and check against threshold
    token_estimate = estimate_conversation_tokens(messages)
    return token_estimate >= max_tokens


def summarize_messages_with_llm(
    messages: List[Dict[str, Any]],
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.3
) -> str:
    """
    Summarize messages using an LLM.
    
    Args:
        messages: The messages to summarize.
        model: The LLM model to use.
        temperature: The temperature parameter for the LLM.
        
    Returns:
        A summary of the conversation.
    """
    # Create LLM client
    llm_client = create_llm_client(model=model, temperature=temperature)
    
    # Prepare the conversation for summarization
    conversation_text = ""
    for message in messages:
        role = message.get("role", "unknown")
        content = message.get("content", "")
        conversation_text += f"\n{role.upper()}: {content}"
    
    # Prepare the prompt for the LLM
    prompt_messages = [
        {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Please summarize the following conversation:\n\n{conversation_text}\n\nSummary:"}
    ]
    
    # Generate the summary
    try:
        response = llm_client.completion(prompt_messages)
        summary = response.get("content", "")
        logger.info(f"Generated conversation summary (original: {len(messages)} messages)")
        return summary
    except Exception as e:
        logger.error(f"Failed to generate summary: {str(e)}")
        # Return a basic summary with the message count if LLM fails
        return f"Conversation with {len(messages)} messages. Summarization failed."


def create_summary_message(
    messages: List[Dict[str, Any]],
    include_timestamp: bool = True,
    model: str = "gpt-3.5-turbo"
) -> Dict[str, Any]:
    """
    Create a summary message from a list of messages.
    
    Args:
        messages: The messages to summarize.
        include_timestamp: Whether to include a timestamp in the summary.
        model: The LLM model to use for summarization.
        
    Returns:
        A summary message that can be added to the conversation history.
    """
    # Generate summary
    summary_content = summarize_messages_with_llm(messages, model=model)
    
    # Add timestamp if requested
    if include_timestamp:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        summary_content = f"[Summary as of {timestamp}]\n{summary_content}"
    
    # Create summary message
    return {
        "role": "system",
        "content": summary_content,
        "is_summary": True,
        "summarized_messages": len(messages),
        "timestamp": time.time()
    }


def compress_conversation_history(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    message_count_threshold: int = 30,
    keep_last_n: int = 5,
    model: str = "gpt-3.5-turbo"
) -> List[Dict[str, Any]]:
    """
    Compress a conversation history by summarizing older messages.
    
    Args:
        messages: The conversation history to compress.
        max_tokens: Maximum token threshold before summarizing.
        message_count_threshold: Message count threshold before summarizing.
        keep_last_n: Number of recent messages to keep (not summarize).
        model: The LLM model to use for summarization.
        
    Returns:
        A compressed conversation history.
    """
    # If the conversation doesn't need summarization, return as is
    if not should_summarize(messages, max_tokens, message_count_threshold):
        return messages
    
    # Split messages into those to summarize and those to keep
    messages_to_summarize = messages[:-keep_last_n] if keep_last_n < len(messages) else messages
    messages_to_keep = messages[-keep_last_n:] if keep_last_n < len(messages) else []
    
    # If there's nothing to summarize, return the original messages
    if not messages_to_summarize:
        return messages
    
    # Create summary message
    summary_message = create_summary_message(messages_to_summarize, model=model)
    
    # Create new message list with summary followed by recent messages
    return [summary_message] + messages_to_keep


def update_state_with_summarized_messages(
    state: StateType,
    max_tokens: int = 4000,
    message_count_threshold: int = 30,
    keep_last_n: int = 5,
    model: str = "gpt-3.5-turbo"
) -> StateType:
    """
    Update state with a summarized conversation history if needed.
    
    Args:
        state: The state to update.
        max_tokens: Maximum token threshold before summarizing.
        message_count_threshold: Message count threshold before summarizing.
        keep_last_n: Number of recent messages to keep (not summarize).
        model: The LLM model to use for summarization.
        
    Returns:
        The updated state with summarized messages if necessary.
    """
    # Check if messages exist and need summarization
    if "messages" not in state or not state["messages"]:
        return state
    
    messages = state["messages"]
    
    # Check if summarization is needed
    if not should_summarize(messages, max_tokens, message_count_threshold):
        return state
    
    # Compress the conversation history
    summarized_messages = compress_conversation_history(
        messages,
        max_tokens=max_tokens,
        message_count_threshold=message_count_threshold,
        keep_last_n=keep_last_n,
        model=model
    )
    
    # Update state with summarized messages
    state["messages"] = summarized_messages
    
    # Update metadata to track summarization
    if "metadata" not in state:
        state["metadata"] = {}
    
    state["metadata"]["last_summarized_at"] = time.time()
    state["metadata"]["summarization_count"] = state["metadata"].get("summarization_count", 0) + 1
    
    # Update timestamp
    return update_state_timestamp(state)


class PeriodicSummarizer:
    """
    Utility class for periodically summarizing conversation history.
    
    This class tracks the conversation and triggers summarization
    based on configurable thresholds.
    """
    
    def __init__(
        self,
        max_tokens: int = 4000,
        message_count_threshold: int = 30,
        keep_last_n: int = 5,
        model: str = "gpt-3.5-turbo"
    ):
        """
        Initialize the periodic summarizer.
        
        Args:
            max_tokens: Maximum token threshold before summarizing.
            message_count_threshold: Message count threshold before summarizing.
            keep_last_n: Number of recent messages to keep (not summarize).
            model: The LLM model to use for summarization.
        """
        self.max_tokens = max_tokens
        self.message_count_threshold = message_count_threshold
        self.keep_last_n = keep_last_n
        self.model = model
        self.last_summarized_at = 0
    
    def check_and_summarize(self, state: StateType) -> Tuple[StateType, bool]:
        """
        Check if summarization is needed and summarize if necessary.
        
        Args:
            state: The current state.
            
        Returns:
            Tuple of (updated state, whether summarization occurred).
        """
        # Skip if no messages or recently summarized
        if "messages" not in state or not state["messages"]:
            return state, False
        
        # Check if summarization is needed
        if not should_summarize(
            state["messages"],
            max_tokens=self.max_tokens,
            message_count_threshold=self.message_count_threshold
        ):
            return state, False
        
        # Summarize the conversation
        updated_state = update_state_with_summarized_messages(
            state,
            max_tokens=self.max_tokens,
            message_count_threshold=self.message_count_threshold,
            keep_last_n=self.keep_last_n,
            model=self.model
        )
        
        # Update last summarized timestamp
        self.last_summarized_at = time.time()
        
        return updated_state, True 