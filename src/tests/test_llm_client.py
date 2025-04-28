"""
Test LLM Client Module

Tests for the LLM client implementation using pytest.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from ..llm.client import create_llm_client, LLMClient


class TestLLMClient:
    """Test cases for LLM client."""
    
    def test_client_initialization(self):
        """Test that the client initializes with default parameters."""
        client = create_llm_client()
        assert isinstance(client, LLMClient)
        assert client.model is not None
        assert 0 <= client.temperature <= 1
    
    def test_client_custom_parameters(self):
        """Test that the client initializes with custom parameters."""
        client = create_llm_client(
            model="gpt-3.5-turbo",
            temperature=0.5,
            max_tokens=100
        )
        assert client.model == "gpt-3.5-turbo"
        assert client.temperature == 0.5
        assert client.max_tokens == 100
    
    @pytest.mark.asyncio
    @patch('langchain_openai.ChatOpenAI')
    async def test_acompletion(self, mock_chat_openai):
        """Test async completion with mocked response."""
        # Setup mock
        mock_instance = MagicMock()
        mock_chat_openai.return_value = mock_instance
        
        # Create mock response
        mock_generation = MagicMock()
        mock_generation.text = "This is a test response"
        mock_generation.finish_reason = "stop"
        
        mock_generations = [[mock_generation]]
        mock_response = MagicMock()
        mock_response.generations = mock_generations
        mock_response.llm_output = {"token_usage": {"total_tokens": 50}}
        
        # Configure mock to return the response
        mock_instance.agenerate.return_value = mock_response
        
        # Create client
        client = create_llm_client()
        
        # Test completion
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        response = await client.acompletion(messages)
        
        # Assert response
        assert response["content"] == "This is a test response"
        assert response["model"] == client.model
        assert response["finish_reason"] == "stop"
        assert response["usage"]["total_tokens"] == 50
    
    @patch('langchain_openai.ChatOpenAI')
    def test_completion(self, mock_chat_openai):
        """Test sync completion with mocked response."""
        # Setup mock
        mock_instance = MagicMock()
        mock_chat_openai.return_value = mock_instance
        
        # Create mock response
        mock_generation = MagicMock()
        mock_generation.text = "This is a test response"
        mock_generation.finish_reason = "stop"
        
        mock_generations = [[mock_generation]]
        mock_response = MagicMock()
        mock_response.generations = mock_generations
        mock_response.llm_output = {"token_usage": {"total_tokens": 50}}
        
        # Configure mock to return the response
        mock_instance.generate.return_value = mock_response
        
        # Create client
        client = create_llm_client()
        
        # Test completion
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        response = client.completion(messages)
        
        # Assert response
        assert response["content"] == "This is a test response"
        assert response["model"] == client.model
        assert response["finish_reason"] == "stop"
        assert response["usage"]["total_tokens"] == 50
    
    def test_convert_to_langchain_messages(self):
        """Test conversion of messages to LangChain format."""
        client = create_llm_client()
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
            {"role": "user", "content": "Great!"}
        ]
        
        langchain_messages = client._convert_to_langchain_messages(messages)
        
        assert len(langchain_messages) == 4
        assert langchain_messages[0].content == "You are a helpful assistant."
        assert langchain_messages[1].content == "Hello, how are you?"
        assert langchain_messages[2].content == "I'm doing well, thank you!"
        assert langchain_messages[3].content == "Great!" 