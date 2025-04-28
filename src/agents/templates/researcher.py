"""
Researcher Agent Template

This module provides a specialized agent template for research tasks,
focusing on information gathering, analysis, and synthesis.
"""

from typing import Any, Dict, List, Optional

from langchain.agents import AgentType, initialize_agent, Tool
from langchain.agents.agent import AgentExecutor
from langchain.tools import BaseTool
from langchain.memory import ConversationBufferMemory
from langchain.callbacks.base import BaseCallbackManager
from langchain.callbacks.manager import CallbackManager
from langchain.agents import BaseSingleActionAgent
from langchain.schema.runnable import Runnable
from langchain.prompts import PromptTemplate

from .base_agent import BaseAgent
from ...llm.client import get_llm_model
from ...utils.logging.logger import get_logger

logger = get_logger()

# Default system message for Researcher agent
DEFAULT_RESEARCHER_SYSTEM_MESSAGE = """You are a Research Agent, specialized in gathering, analyzing, and synthesizing information.

Your key capabilities include:
1. Finding relevant information from multiple sources
2. Evaluating the credibility and reliability of sources
3. Summarizing complex information clearly and accurately
4. Identifying patterns, trends, and connections between different pieces of information
5. Providing well-organized, comprehensive research reports

Approach each task methodically:
- Understand the research question clearly
- Break down complex questions into simpler sub-questions
- Gather information from appropriate sources
- Analyze and evaluate the information critically
- Synthesize findings into a coherent response
- Cite sources when appropriate
- Acknowledge limitations and gaps in available information

Always maintain objectivity and avoid personal bias in your research.
"""


class ResearcherAgent(BaseAgent):
    """
    Specialized agent template for research tasks.
    
    Focuses on gathering information, analyzing data,
    and synthesizing findings into coherent responses.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str = "Research Agent",
        agent_description: str = "Specialized in gathering and analyzing information.",
        system_message: Optional[str] = None,
        search_tools: bool = True,
        **kwargs
    ):
        """
        Initialize a researcher agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent (uses default if None)
            search_tools: Whether to include default search tools
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Use default system message if none provided
        system_message = system_message or DEFAULT_RESEARCHER_SYSTEM_MESSAGE
        
        # Initialize base agent
        super().__init__(
            agent_id=agent_id,
            agent_type="researcher",
            agent_name=agent_name,
            agent_role="Research specialist",
            agent_description=agent_description,
            system_message=system_message,
            **kwargs
        )
        
        # Add default search tools if requested
        if search_tools:
            self._add_default_search_tools()
    
    def _add_default_search_tools(self) -> None:
        """Add default search tools to the agent."""
        # Add web search tool if available
        try:
            from langchain.tools import WikipediaQueryRun
            from langchain.utilities import WikipediaAPIWrapper
            
            wikipedia_tool = Tool(
                name="Wikipedia",
                description="Search Wikipedia for information on a topic.",
                func=WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()).run
            )
            self.add_tool(wikipedia_tool)
            logger.debug(f"Added Wikipedia search tool to researcher agent {self.agent_id}")
        except ImportError:
            logger.warning("Wikipedia tool not available. Install wikipedia package to enable it.")
        
        # Add search tools if available
        try:
            from langchain.tools import DuckDuckGoSearchRun
            
            search_tool = Tool(
                name="Web Search",
                description="Search the web for information on a topic.",
                func=DuckDuckGoSearchRun().run
            )
            self.add_tool(search_tool)
            logger.debug(f"Added web search tool to researcher agent {self.agent_id}")
        except ImportError:
            logger.warning("DuckDuckGo search tool not available. Install duckduckgo-search package to enable it.")
    
    def _create_agent(self) -> BaseSingleActionAgent:
        """
        Create the concrete LangChain agent implementation.
        
        Returns:
            Configured LangChain agent
        """
        # Set up LangChain memory adapter
        langchain_memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Get recent messages from memory
        recent_messages = self.memory.get_conversation_history(max_messages=10)
        for message in recent_messages:
            if message["role"] == "user":
                langchain_memory.chat_memory.add_user_message(message["content"])
            elif message["role"] == "assistant":
                langchain_memory.chat_memory.add_ai_message(message["content"])
        
        # Initialize ReAct agent
        agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            verbose=self.verbose,
            memory=langchain_memory,
            handle_parsing_errors=True,
            max_iterations=self.max_iterations,
            early_stopping_method="generate",
            agent_kwargs={
                "system_message": self.system_message,
                "human_message": "I need your help with a research task."
            }
        )
        
        return agent 