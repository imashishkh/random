"""
Planner Agent Template

This module provides a specialized agent template for planning tasks,
focusing on goal decomposition, step sequencing, and strategic thinking.
"""

from typing import Any, Dict, List, Optional

from langchain.agents import AgentType, initialize_agent, Tool, create_structured_chat_agent
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

# Default system message for Planner agent
DEFAULT_PLANNER_SYSTEM_MESSAGE = """You are a Planning Agent, specialized in strategic thinking, plan formulation, and goal decomposition.

Your key capabilities include:
1. Breaking down complex goals into manageable sub-goals
2. Creating detailed step-by-step plans
3. Anticipating potential issues and developing contingency plans
4. Analyzing resource requirements and constraints
5. Optimizing plans for efficiency and effectiveness
6. Adapting plans as circumstances change

Approach each planning task methodically:
- Understand the overall goal and constraints clearly
- Decompose complex goals into smaller, tractable sub-goals
- Identify dependencies between tasks
- Sequence steps in a logical order
- Estimate time and resource requirements
- Consider potential obstacles and develop contingency plans
- Present plans in a clear, actionable format

Your plans should be comprehensive yet adaptable, considering both the big picture and the detailed steps needed for implementation.
"""


class PlannerAgent(BaseAgent):
    """
    Specialized agent template for planning tasks.
    
    Focuses on goal decomposition, step sequencing,
    and strategic thinking to develop effective plans.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str = "Planning Agent",
        agent_description: str = "Specialized in strategic planning and goal decomposition.",
        system_message: Optional[str] = None,
        planning_framework: str = "standard",
        **kwargs
    ):
        """
        Initialize a planner agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent (uses default if None)
            planning_framework: Planning approach to use ("standard", "agile", "strategic")
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Use default system message if none provided
        base_system_message = system_message or DEFAULT_PLANNER_SYSTEM_MESSAGE
        
        # Augment system message with planning framework specifics
        system_message = self._add_framework_to_system_message(base_system_message, planning_framework)
        
        # Initialize base agent
        super().__init__(
            agent_id=agent_id,
            agent_type="planner",
            agent_name=agent_name,
            agent_role="Planning specialist",
            agent_description=agent_description,
            system_message=system_message,
            **kwargs
        )
        
        # Store planning framework
        self.planning_framework = planning_framework
        
        # Add planning tools
        self._add_planning_tools()
    
    def _add_framework_to_system_message(self, base_message: str, framework: str) -> str:
        """
        Augment the system message with framework-specific instructions.
        
        Args:
            base_message: Base system message
            framework: Planning framework to use
            
        Returns:
            Augmented system message
        """
        if framework == "agile":
            additional_guidance = """
As an Agile Planning specialist:
- Break work into short sprints (1-4 weeks)
- Prioritize based on business value and dependencies
- Plan for regular review and adaptation
- Focus on delivering working increments frequently
- Incorporate feedback loops into the plan
"""
        elif framework == "strategic":
            additional_guidance = """
As a Strategic Planning specialist:
- Consider long-term vision and mission
- Analyze strengths, weaknesses, opportunities, and threats (SWOT)
- Focus on high-level objectives and key results (OKRs)
- Create cascading goals from strategic to tactical levels
- Incorporate performance metrics and success criteria
"""
        else:  # standard framework
            additional_guidance = """
As a Standard Planning specialist:
- Balance detail with flexibility
- Focus on clear, actionable steps
- Consider both short-term and long-term goals
- Prioritize tasks based on importance and urgency
- Incorporate checkpoints to evaluate progress
"""
        
        return f"{base_message}\n{additional_guidance}"
    
    def _add_planning_tools(self) -> None:
        """Add planning tools to the agent."""
        # Add goal decomposition tool
        goal_decomposition_tool = Tool(
            name="GoalDecomposition",
            description="Break down a complex goal into smaller, manageable sub-goals.",
            func=self._decompose_goal
        )
        self.add_tool(goal_decomposition_tool)
        
        # Add plan creation tool
        plan_creation_tool = Tool(
            name="CreatePlan",
            description="Create a step-by-step plan to achieve a goal.",
            func=self._create_plan
        )
        self.add_tool(plan_creation_tool)
        
        # Add resource estimation tool
        resource_estimation_tool = Tool(
            name="EstimateResources",
            description="Estimate the resources needed to execute a plan.",
            func=self._estimate_resources
        )
        self.add_tool(resource_estimation_tool)
        
        logger.debug(f"Added planning tools to planner agent {self.agent_id}")
    
    def _decompose_goal(self, goal: str) -> str:
        """
        Decompose a complex goal into smaller, manageable sub-goals.
        
        Args:
            goal: The complex goal to decompose
            
        Returns:
            String containing the decomposed sub-goals
        """
        # Create a prompt for goal decomposition
        prompt = f"""
You are a planning specialist focusing on goal decomposition.
Break down the following complex goal into 3-7 smaller, manageable sub-goals:

GOAL: {goal}

For each sub-goal:
1. Provide a clear, concise title
2. Add a brief description
3. Note any dependencies on other sub-goals
4. Estimate the relative complexity (Low, Medium, High)

FORMAT YOUR RESPONSE AS:
# Sub-goal 1: [Title]
Description: [Brief description]
Dependencies: [List any dependencies, or "None"]
Complexity: [Low/Medium/High]

# Sub-goal 2: [Title]
...
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _create_plan(self, goal_with_subgoals: str) -> str:
        """
        Create a step-by-step plan to achieve a goal.
        
        Args:
            goal_with_subgoals: The goal and its sub-goals
            
        Returns:
            String containing the step-by-step plan
        """
        # Create a prompt for plan creation
        prompt = f"""
You are a planning specialist focusing on creating detailed plans.
Create a step-by-step plan for achieving the following goal and sub-goals:

{goal_with_subgoals}

Your plan should include:
1. A sequential list of actions to take
2. Estimated time for each step
3. Dependencies between steps
4. Any resources needed
5. Potential risks and mitigation strategies

FORMAT YOUR RESPONSE AS:
# Plan Overview
[Brief summary of the overall approach]

# Detailed Steps
## Step 1: [Step title]
Description: [What needs to be done]
Time Estimate: [Time required]
Dependencies: [List any dependencies, or "None"]
Resources: [List required resources]
Risks & Mitigation: [Identify risks and how to mitigate them]

## Step 2: [Step title]
...

# Timeline
[Provide an overall timeline with key milestones]

# Success Criteria
[List criteria to determine if the plan has been successfully executed]
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _estimate_resources(self, plan: str) -> str:
        """
        Estimate the resources needed to execute a plan.
        
        Args:
            plan: The plan to estimate resources for
            
        Returns:
            String containing the resource estimates
        """
        # Create a prompt for resource estimation
        prompt = f"""
You are a planning specialist focusing on resource estimation.
Analyze the following plan and provide detailed resource estimates:

{plan}

Your resource estimation should include:
1. Human resources (roles, skills, time commitments)
2. Budget requirements (costs broken down by category)
3. Tools and technologies needed
4. Timeline requirements
5. Any other critical resources

FORMAT YOUR RESPONSE AS:
# Resource Estimation Summary
[Brief overview of resource requirements]

# Human Resources
[Detailed breakdown of personnel needs]

# Budget Requirements
[Itemized cost estimates]

# Tools & Technologies
[List of required tools and technologies]

# Timeline Resources
[Time-based resource allocation]

# Additional Resources
[Any other resources needed]

# Optimization Opportunities
[Suggestions for resource optimization]
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
        
        # Create structured chat agent
        agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=chat_prompt
        )
        
        return agent 