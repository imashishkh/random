"""
Executor Agent Template

This module provides a specialized agent template for execution tasks,
focusing on implementing plans, problem-solving, and taking action.
"""

from typing import Any, Dict, List, Optional, Union

from langchain.agents import AgentType, initialize_agent, Tool, create_openai_functions_agent
from langchain.agents.agent import AgentExecutor
from langchain.tools import BaseTool
from langchain.memory import ConversationBufferMemory
from langchain.callbacks.base import BaseCallbackManager
from langchain.callbacks.manager import CallbackManager
from langchain.agents import BaseSingleActionAgent
from langchain.schema.runnable import Runnable
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.prompts.chat import HumanMessagePromptTemplate, SystemMessagePromptTemplate

from .base_agent import BaseAgent
from ...llm.client import get_llm_model
from ...utils.logging.logger import get_logger

logger = get_logger()

# Default system message for Executor agent
DEFAULT_EXECUTOR_SYSTEM_MESSAGE = """You are an Executor Agent, specialized in implementing plans, solving problems, and taking action.

Your key capabilities include:
1. Executing tasks with precision and attention to detail
2. Problem-solving and troubleshooting when obstacles arise
3. Adapting to changing conditions while maintaining focus on goals
4. Following procedural instructions precisely
5. Efficiently using available tools and resources
6. Reporting results clearly and accurately

Approach each execution task methodically:
- Understand what needs to be done and the expected outcome
- Break complex tasks into executable steps
- Follow instructions precisely
- Troubleshoot issues as they arise
- Validate results against success criteria
- Report on completion status and any issues encountered

Your focus is on reliable implementation and effective problem solving to turn plans into reality.
"""


class ExecutorAgent(BaseAgent):
    """
    Specialized agent template for execution tasks.
    
    Focuses on implementing plans, problem-solving,
    and taking reliable action to achieve goals.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str = "Executor Agent",
        agent_description: str = "Specialized in implementing plans and solving problems.",
        system_message: Optional[str] = None,
        execution_mode: str = "standard",
        include_system_tools: bool = True,
        **kwargs
    ):
        """
        Initialize an executor agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent (uses default if None)
            execution_mode: Execution approach ("standard", "detailed", "expedited")
            include_system_tools: Whether to include default system tools
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Use default system message if none provided
        base_system_message = system_message or DEFAULT_EXECUTOR_SYSTEM_MESSAGE
        
        # Augment system message with execution mode specifics
        system_message = self._add_mode_to_system_message(base_system_message, execution_mode)
        
        # Initialize base agent
        super().__init__(
            agent_id=agent_id,
            agent_type="executor",
            agent_name=agent_name,
            agent_role="Execution specialist",
            agent_description=agent_description,
            system_message=system_message,
            **kwargs
        )
        
        # Store execution mode
        self.execution_mode = execution_mode
        
        # Add execution tools
        self._add_execution_tools()
        
        # Add system tools if requested
        if include_system_tools:
            self._add_system_tools()
    
    def _add_mode_to_system_message(self, base_message: str, mode: str) -> str:
        """
        Augment the system message with mode-specific instructions.
        
        Args:
            base_message: Base system message
            mode: Execution mode to use
            
        Returns:
            Augmented system message
        """
        if mode == "detailed":
            additional_guidance = """
As a Detailed Execution specialist:
- Document every step taken in detail
- Validate results at each milestone
- Double-check inputs and outputs
- Maintain comprehensive logs
- Focus on quality and correctness over speed
"""
        elif mode == "expedited":
            additional_guidance = """
As an Expedited Execution specialist:
- Prioritize speed and efficiency
- Focus on critical path activities
- Use shortcuts where appropriate
- Report essential outcomes only
- Balance speed with acceptable quality
"""
        else:  # standard mode
            additional_guidance = """
As a Standard Execution specialist:
- Balance thoroughness with efficiency
- Maintain clear documentation of key steps
- Validate critical outcomes
- Provide concise, structured reports
- Adapt based on context and priorities
"""
        
        return f"{base_message}\n{additional_guidance}"
    
    def _add_execution_tools(self) -> None:
        """Add execution-specific tools to the agent."""
        # Add task execution tool
        task_execution_tool = Tool(
            name="ExecuteTask",
            description="Execute a specific task and report results.",
            func=self._execute_task
        )
        self.add_tool(task_execution_tool)
        
        # Add issue troubleshooting tool
        troubleshooting_tool = Tool(
            name="TroubleshootIssue",
            description="Analyze and resolve issues encountered during execution.",
            func=self._troubleshoot_issue
        )
        self.add_tool(troubleshooting_tool)
        
        # Add progress tracking tool
        progress_tool = Tool(
            name="TrackProgress",
            description="Track progress against the plan and identify next steps.",
            func=self._track_progress
        )
        self.add_tool(progress_tool)
        
        logger.debug(f"Added execution tools to executor agent {self.agent_id}")
    
    def _add_system_tools(self) -> None:
        """Add system-related tools to the agent."""
        # Try to add file operation tools if available
        try:
            from langchain.tools.file_management import (
                ReadFileTool,
                WriteFileTool,
                ListDirectoryTool
            )
            
            read_tool = ReadFileTool()
            write_tool = WriteFileTool()
            list_tool = ListDirectoryTool()
            
            self.add_tools([read_tool, write_tool, list_tool])
            logger.debug(f"Added file operation tools to executor agent {self.agent_id}")
        except ImportError:
            logger.warning("File operation tools not available. Install required dependencies to enable them.")
        
        # Try to add shell tool if available
        try:
            from langchain.tools import ShellTool
            
            shell_tool = ShellTool()
            self.add_tool(shell_tool)
            logger.debug(f"Added shell tool to executor agent {self.agent_id}")
        except ImportError:
            logger.warning("Shell tool not available. Install required dependencies to enable it.")
    
    def _execute_task(self, task_description: str) -> str:
        """
        Execute a specific task and report results.
        
        Args:
            task_description: Description of the task to execute
            
        Returns:
            String containing the execution results
        """
        # Create a prompt for task execution
        prompt = f"""
You are an execution specialist focusing on implementing tasks.
Execute the following task and report on the results:

TASK: {task_description}

Follow these steps:
1. Break down the task into specific executable actions
2. Execute each action in sequence
3. Document what you did and the outcome
4. Note any issues encountered and how they were resolved
5. Validate that the task was completed successfully

FORMAT YOUR RESPONSE AS:
# Task Execution Report

## Actions Taken
- [List each action taken]

## Outcomes
- [Document the outcomes of each action]

## Issues and Resolutions
- [Note any issues encountered and how they were addressed]

## Validation
- [Describe how you confirmed the task was completed successfully]

## Summary
[Brief summary of the execution and results]
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _troubleshoot_issue(self, issue_description: str) -> str:
        """
        Analyze and resolve issues encountered during execution.
        
        Args:
            issue_description: Description of the issue to troubleshoot
            
        Returns:
            String containing the troubleshooting results
        """
        # Create a prompt for issue troubleshooting
        prompt = f"""
You are an execution specialist focusing on troubleshooting issues.
Analyze and resolve the following issue:

ISSUE: {issue_description}

Follow these steps:
1. Analyze the issue to identify potential root causes
2. Generate hypotheses about what might be causing the issue
3. Develop an action plan to address each potential cause
4. Prioritize actions based on likelihood and impact
5. Suggest specific steps to resolve the issue

FORMAT YOUR RESPONSE AS:
# Issue Analysis

## Potential Root Causes
- [List potential causes from most to least likely]

## Diagnostic Actions
- [List actions to confirm or rule out each cause]

## Resolution Plan
- [Step-by-step plan to resolve the issue]

## Prevention
- [Recommendations to prevent similar issues in the future]

## Summary
[Brief summary of the analysis and recommended approach]
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _track_progress(self, plan_and_status: str) -> str:
        """
        Track progress against the plan and identify next steps.
        
        Args:
            plan_and_status: The plan and current status
            
        Returns:
            String containing the progress tracking results
        """
        # Create a prompt for progress tracking
        prompt = f"""
You are an execution specialist focusing on progress tracking.
Analyze the following plan and current status to track progress and identify next steps:

{plan_and_status}

Follow these steps:
1. Assess which plan items have been completed, are in progress, or not started
2. Identify any delays or deviations from the plan
3. Determine the current completion percentage
4. Identify the next critical actions needed
5. Assess any risks to completing the plan

FORMAT YOUR RESPONSE AS:
# Progress Report

## Completion Status
- Completed: [List completed items]
- In Progress: [List in-progress items]
- Not Started: [List not-started items]

## Plan Adherence
- On Track: [Yes/No, with explanation]
- Deviations: [Note any deviations from plan]
- Completion: [Estimated percentage complete]

## Next Actions
- [List the next 3-5 critical actions]

## Risk Assessment
- [Identify risks to completing the plan]

## Recommendations
[Specific recommendations to keep the plan on track]
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
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
        
        # Create prompt template with system message
        system_message_prompt = SystemMessagePromptTemplate.from_template(self.system_message)
        human_message_prompt = HumanMessagePromptTemplate.from_template("{input}")
        
        chat_prompt = ChatPromptTemplate.from_messages([
            system_message_prompt,
            MessagesPlaceholder(variable_name="chat_history"),
            human_message_prompt
        ])
        
        # Create OpenAI functions agent for better tool handling
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=chat_prompt
        )
        
        return agent 