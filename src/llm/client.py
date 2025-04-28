"""
LLM Client Module

This module provides a client for interacting with OpenAI LLMs through LangChain,
with proper error handling, retries, and logging.
"""

import time
from typing import Dict, List, Any, Optional, Union, Callable

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

from .config import get_llm_config
from ..utils.retry.retry import retry_openai_api
from ..utils.logging.logger import get_logger, log_llm_request, log_llm_response

# Get logger
logger = get_logger()

# Get configuration
llm_config = get_llm_config()


class LLMClient:
    """Client for interacting with OpenAI LLMs through LangChain."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: bool = False,
        callback_manager: Optional[CallbackManager] = None,
        **kwargs
    ):
        """
        Initialize the LLM client.
        
        Args:
            model: The model identifier.
            temperature: The temperature parameter.
            max_tokens: The maximum tokens parameter.
            streaming: Whether to stream the response.
            callback_manager: Custom callback manager.
            **kwargs: Additional parameters to pass to the LLM.
        """
        # Use default values from config if not provided
        self.model = model or llm_config.default_model
        self.temperature = temperature if temperature is not None else llm_config.default_temperature
        self.max_tokens = max_tokens or llm_config.default_max_tokens
        self.streaming = streaming
        self.request_timeout = kwargs.get("request_timeout", llm_config.request_timeout)
        
        # Create callback manager if streaming is enabled and no custom manager is provided
        if streaming and not callback_manager:
            callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
        self.callback_manager = callback_manager
        
        # Create OpenAI LLM client
        self.client = self._create_client(**kwargs)
    
    def _create_client(self, **kwargs) -> ChatOpenAI:
        """
        Create an OpenAI client with proper configuration.
        
        Args:
            **kwargs: Additional parameters to pass to the client.
            
        Returns:
            ChatOpenAI: The configured ChatOpenAI client.
        """
        # Create client configuration
        client_config = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "request_timeout": self.request_timeout
        }
        
        # Add optional parameters
        if self.streaming:
            client_config["streaming"] = True
        if self.callback_manager:
            client_config["callback_manager"] = self.callback_manager
        
        # Add OpenAI API key
        client_config["api_key"] = llm_config.openai_api_key
        
        # Add organization ID if available
        if llm_config.openai_org_id:
            client_config["organization"] = llm_config.openai_org_id
        
        # Add additional parameters
        client_config.update(kwargs)
        
        # Create client
        return ChatOpenAI(**client_config)
    
    @retry_openai_api
    async def acompletion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a completion asynchronously.
        
        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional parameters to pass to the LLM.
            
        Returns:
            Dict: The LLM response.
        """
        # Convert messages to LangChain format
        langchain_messages = self._convert_to_langchain_messages(messages)
        
        # Log request
        system_message = next((m["content"] for m in messages if m["role"] == "system"), "")
        last_user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        log_llm_request(
            logger,
            self.model,
            messages,
            prompt=f"System: {system_message}\nUser: {last_user_message}",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **kwargs
        )
        
        # Measure latency
        start_time = time.time()
        
        # Generate completion
        response = await self.client.agenerate([langchain_messages])
        
        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Extract response
        generation = response.generations[0][0]
        result = {
            "content": generation.text,
            "model": self.model,
            "finish_reason": getattr(generation, "finish_reason", None)
        }
        
        # Add token usage if available
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            result["usage"] = token_usage
            tokens_used = token_usage.get("total_tokens", None)
        else:
            tokens_used = None
        
        # Log response
        log_llm_response(
            logger,
            self.model,
            result,
            tokens_used=tokens_used,
            latency_ms=latency_ms
        )
        
        return result
    
    @retry_openai_api
    def completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a completion synchronously.
        
        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional parameters to pass to the LLM.
            
        Returns:
            Dict: The LLM response.
        """
        # Convert messages to LangChain format
        langchain_messages = self._convert_to_langchain_messages(messages)
        
        # Log request
        system_message = next((m["content"] for m in messages if m["role"] == "system"), "")
        last_user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        log_llm_request(
            logger,
            self.model,
            messages,
            prompt=f"System: {system_message}\nUser: {last_user_message}",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **kwargs
        )
        
        # Measure latency
        start_time = time.time()
        
        # Generate completion
        response = self.client.generate([langchain_messages])
        
        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Extract response
        generation = response.generations[0][0]
        result = {
            "content": generation.text,
            "model": self.model,
            "finish_reason": getattr(generation, "finish_reason", None)
        }
        
        # Add token usage if available
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            result["usage"] = token_usage
            tokens_used = token_usage.get("total_tokens", None)
        else:
            tokens_used = None
        
        # Log response
        log_llm_response(
            logger,
            self.model,
            result,
            tokens_used=tokens_used,
            latency_ms=latency_ms
        )
        
        return result
    
    def _convert_to_langchain_messages(self, messages: List[Dict[str, str]]):
        """
        Convert messages to LangChain format.
        
        Args:
            messages: List of messages in the conversation.
            
        Returns:
            List: List of LangChain message objects.
        """
        langchain_messages = []
        
        for message in messages:
            role = message["role"]
            content = message["content"]
            
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                logger.warning(f"Unknown message role: {role}")
        
        return langchain_messages


# Factory function to create LLM clients
def create_llm_client(**kwargs) -> LLMClient:
    """
    Create an LLM client with the specified parameters.
    
    Args:
        **kwargs: Parameters to pass to the LLM client.
        
    Returns:
        LLMClient: The configured LLM client.
    """
    return LLMClient(**kwargs)


def get_llm_model(
    model_name: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    streaming: bool = False,
    **kwargs
) -> ChatOpenAI:
    """
    Get a language model instance for use in agents and chains.
    
    Args:
        model_name: The model identifier (defaults to configured default)
        openai_api_key: OpenAI API key (defaults to configured key)
        temperature: The temperature parameter (defaults to configured default)
        max_tokens: The maximum tokens parameter (defaults to configured default)
        streaming: Whether to use streaming response
        **kwargs: Additional parameters to pass to the LLM
        
    Returns:
        ChatOpenAI: The configured LLM
    """
    # Use default values from config if not provided
    config = get_llm_config()
    
    model = model_name or config.default_model
    api_key = openai_api_key or config.openai_api_key
    temp = temperature if temperature is not None else config.default_temperature
    tokens = max_tokens or config.default_max_tokens
    
    # Create client configuration
    client_config = {
        "model": model,
        "temperature": temp,
        "max_tokens": tokens,
        "api_key": api_key,
        "streaming": streaming,
    }
    
    # Add organization ID if available
    if config.openai_org_id:
        client_config["organization"] = config.openai_org_id
    
    # Add additional parameters
    client_config.update(kwargs)
    
    # Create and return LLM
    logger.debug(f"Creating LLM with model={model}, temp={temp}, max_tokens={tokens}")
    return ChatOpenAI(**client_config) 