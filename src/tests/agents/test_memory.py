import os
import pytest
import tempfile
import json
import shutil
from unittest.mock import patch, MagicMock

from ...agents.memory.memory import AgentMemory


class TestAgentMemory:
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test memory storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def memory(self, temp_dir):
        """Create a memory instance for testing."""
        return AgentMemory(
            agent_id="test_agent",
            openai_api_key="fake_key",
            persistence_dir=temp_dir,
            max_conversation_messages=5,
            consolidation_threshold=3
        )

    def test_initialization(self, memory, temp_dir):
        """Test that the memory is initialized correctly."""
        assert memory.agent_id == "test_agent"
        assert memory.persistence_dir == temp_dir
        assert memory.max_conversation_messages == 5
        assert memory.consolidation_threshold == 3
        assert memory.conversation_memory == []
        assert memory.working_memory == {}
        assert memory.long_term_memory == []
        assert os.path.exists(os.path.join(temp_dir, "test_agent"))

    def test_add_message(self, memory):
        """Test adding messages to conversation memory."""
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi there")
        
        assert len(memory.conversation_memory) == 2
        assert memory.conversation_memory[0] == {"role": "user", "content": "Hello"}
        assert memory.conversation_memory[1] == {"role": "assistant", "content": "Hi there"}

    def test_max_conversation_limit(self, memory):
        """Test that conversation memory respects the max limit."""
        # Add more messages than the max limit
        for i in range(10):
            memory.add_message("user", f"Message {i}")
        
        # Should only keep the latest max_conversation_messages
        assert len(memory.conversation_memory) == 5
        assert memory.conversation_memory[0]["content"] == "Message 5"
        assert memory.conversation_memory[4]["content"] == "Message 9"

    def test_working_memory(self, memory):
        """Test working memory operations."""
        # Set and get working memory
        memory.set_working_memory("key1", "value1")
        memory.set_working_memory("key2", {"nested": "data"})
        
        assert memory.get_working_memory("key1") == "value1"
        assert memory.get_working_memory("key2") == {"nested": "data"}
        
        # Clear working memory
        memory.clear_working_memory()
        assert memory.working_memory == {}

    def test_conversation_history(self, memory):
        """Test retrieving conversation history."""
        messages = [
            ("user", "Hello"),
            ("assistant", "Hi there"),
            ("user", "How are you?"),
            ("assistant", "I'm fine, thanks")
        ]
        
        for role, content in messages:
            memory.add_message(role, content)
        
        history = memory.get_conversation_history()
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "Hello"}
        
        # Test with limit
        limited_history = memory.get_conversation_history(limit=2)
        assert len(limited_history) == 2
        assert limited_history[0] == {"role": "user", "content": "How are you?"}
        assert limited_history[1] == {"role": "assistant", "content": "I'm fine, thanks"}

    def test_llm_messages(self, memory):
        """Test getting messages formatted for LLM."""
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi there")
        
        llm_messages = memory.get_llm_messages(system_message="You are a helpful assistant")
        assert llm_messages[0]["role"] == "system"
        assert llm_messages[0]["content"] == "You are a helpful assistant"
        assert llm_messages[1]["role"] == "user"
        assert llm_messages[1]["content"] == "Hello"
        assert llm_messages[2]["role"] == "assistant"
        assert llm_messages[2]["content"] == "Hi there"

    @patch("src.agents.memory.memory.embeddings_api")
    def test_long_term_memory(self, mock_embeddings, memory):
        """Test long-term memory operations."""
        # Mock the embeddings API
        mock_embedding = [0.1] * 1536
        mock_embeddings.get_embedding.return_value = mock_embedding
        
        # Add to long-term memory
        memory.add_to_long_term_memory("This is an important fact")
        
        assert len(memory.long_term_memory) == 1
        assert memory.long_term_memory[0]["content"] == "This is an important fact"
        assert memory.long_term_memory[0]["embedding"] == mock_embedding
        
        # Test searching long-term memory
        mock_embeddings.get_embedding.return_value = mock_embedding
        results = memory.search_long_term_memory("Related query", k=1)
        assert len(results) == 1
        assert results[0]["content"] == "This is an important fact"
        
        # Test forgetting
        memory_id = memory.long_term_memory[0]["id"]
        memory.forget_long_term_entry(memory_id)
        assert len(memory.long_term_memory) == 0

    def test_memory_consolidation(self, memory):
        """Test memory consolidation logic."""
        with patch.object(memory, '_should_consolidate', return_value=True), \
             patch.object(memory, 'add_to_long_term_memory') as mock_add:
            
            # Add messages to trigger consolidation
            for i in range(5):
                memory.add_message("user", f"Important message {i}")
                
            # Check that add_to_long_term_memory was called
            assert mock_add.call_count > 0

    def test_save_and_load(self, memory, temp_dir):
        """Test saving and loading memory from disk."""
        # Add some data
        memory.add_message("user", "Hello")
        memory.set_working_memory("key", "value")
        memory.add_to_long_term_memory("Long-term fact")
        
        # Save memory
        memory.save()
        
        # Create a new memory instance that loads from the same directory
        new_memory = AgentMemory(
            agent_id="test_agent",
            openai_api_key="fake_key",
            persistence_dir=temp_dir
        )
        
        # Check that data was loaded correctly
        assert len(new_memory.conversation_memory) == 1
        assert new_memory.conversation_memory[0]["content"] == "Hello"
        assert new_memory.working_memory["key"] == "value"
        assert len(new_memory.long_term_memory) == 1
        assert new_memory.long_term_memory[0]["content"] == "Long-term fact"

    @patch("src.agents.memory.memory.embeddings_api")
    def test_augment_context(self, mock_embeddings, memory):
        """Test augmenting context with relevant memories."""
        # Mock the embeddings API
        mock_embedding = [0.1] * 1536
        mock_embeddings.get_embedding.return_value = mock_embedding
        
        # Add some memories
        memory.add_to_long_term_memory("Relevant fact 1")
        memory.add_to_long_term_memory("Relevant fact 2")
        
        # Test augmenting context
        context = "Original context"
        augmented = memory.augment_context_with_memories(context, k=2)
        
        assert "Original context" in augmented
        assert "Relevant fact 1" in augmented
        assert "Relevant fact 2" in augmented

    def test_get_stats(self, memory):
        """Test getting memory statistics."""
        # Add some data
        memory.add_message("user", "Hello")
        memory.set_working_memory("key", "value")
        memory.add_to_long_term_memory("Long-term fact")
        
        stats = memory.get_stats()
        assert stats["conversation_memory_count"] == 1
        assert stats["working_memory_count"] == 1
        assert stats["long_term_memory_count"] == 1 