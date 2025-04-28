"""
Coordinator Agent Template

This module provides a specialized agent template for task coordination,
focusing on task allocation, agent orchestration, and workflow management.
"""

from typing import Any, Dict, List, Optional, Union, Tuple

from langchain.agents import AgentType, initialize_agent, Tool
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
from .factory import AgentFactory
from .orchestration import WorkflowBuilder, GraphState
from ...llm.client import get_llm_model
from ...utils.logging.logger import get_logger

logger = get_logger()

# Default system message for Coordinator agent
DEFAULT_COORDINATOR_SYSTEM_MESSAGE = """You are a Coordinator Agent, specialized in task allocation, agent orchestration, and workflow management.

Your key capabilities include:
1. Analyzing complex tasks and breaking them down into subtasks
2. Determining which specialized agents are needed for different subtasks
3. Allocating tasks to appropriate agents based on their capabilities
4. Creating and managing workflows that connect multiple agents
5. Monitoring progress and ensuring successful task completion
6. Integrating results from different agents into cohesive outputs
7. Handling errors and adapting workflows as needed

Approach each coordination task methodically:
- Understand the overall goal and requirements clearly
- Break down complex tasks into manageable subtasks
- Identify the agent types required for each subtask (researcher, planner, executor, etc.)
- Allocate tasks to appropriate agents based on their specializations
- Monitor agent progress and output quality
- Intervene and reallocate tasks when necessary
- Integrate results from multiple agents into a cohesive solution
- Ensure the overall goal is achieved effectively and efficiently

As a coordinator, you're responsible for orchestrating the efforts of specialized agents to achieve complex goals that require multiple capabilities and perspectives.
"""


class CoordinatorAgent(BaseAgent):
    """
    Specialized agent template for task coordination.
    
    Focuses on task allocation, agent orchestration, 
    and workflow management across multiple agents.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str = "Coordinator Agent",
        agent_description: str = "Specialized in task allocation and agent orchestration.",
        system_message: Optional[str] = None,
        coordination_strategy: str = "adaptive",
        agent_factory: Optional[AgentFactory] = None,
        **kwargs
    ):
        """
        Initialize a coordinator agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            agent_description: Detailed description of the agent's capabilities
            system_message: System message for the agent (uses default if None)
            coordination_strategy: Strategy for coordination ("adaptive", "sequential", "parallel")
            agent_factory: Factory for creating other agents (creates a default if None)
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Use default system message if none provided
        system_message = system_message or DEFAULT_COORDINATOR_SYSTEM_MESSAGE
        
        # Initialize base agent
        super().__init__(
            agent_id=agent_id,
            agent_type="coordinator",
            agent_name=agent_name,
            agent_role="Coordination specialist",
            agent_description=agent_description,
            system_message=system_message,
            **kwargs
        )
        
        # Store coordination strategy
        self.coordination_strategy = coordination_strategy
        
        # Initialize agent factory
        self.agent_factory = agent_factory or AgentFactory()
        
        # Track created agents and workflows
        self.managed_agents = {}
        self.active_workflows = {}
        
        # Add coordination tools
        self._add_coordination_tools()
    
    def _add_coordination_tools(self) -> None:
        """Add coordination-specific tools to the agent."""
        # Add task analysis tool
        task_analysis_tool = Tool(
            name="TaskAnalysis",
            description="Analyze a complex task and break it down into subtasks with required agent types.",
            func=self._analyze_task
        )
        self.add_tool(task_analysis_tool)
        
        # Add agent selection tool
        agent_selection_tool = Tool(
            name="AgentSelection",
            description="Select the appropriate agent type for a specific subtask.",
            func=self._select_agent_for_task
        )
        self.add_tool(agent_selection_tool)
        
        # Add workflow creation tool
        workflow_creation_tool = Tool(
            name="WorkflowCreation",
            description="Create a workflow connecting multiple agents to complete a complex task.",
            func=self._create_workflow
        )
        self.add_tool(workflow_creation_tool)
        
        # Add task allocation tool
        task_allocation_tool = Tool(
            name="TaskAllocation",
            description="Allocate a specific subtask to an appropriate agent.",
            func=self._allocate_task
        )
        self.add_tool(task_allocation_tool)
        
        logger.debug(f"Added coordination tools to coordinator agent {self.agent_id}")
    
    def _analyze_task(self, task_description: str) -> str:
        """
        Analyze a complex task and break it down into subtasks.
        
        Args:
            task_description: Description of the complex task
            
        Returns:
            JSON string containing subtasks and required agent types
        """
        # Create a prompt for task analysis
        prompt = f"""
You are a coordination specialist focusing on breaking down complex tasks.
Analyze the following task and break it down into logical subtasks:

Task: {task_description}

For each subtask, identify:
1. A clear subtask description
2. The type of agent best suited for this subtask (researcher, planner, executor, etc.)
3. Any dependencies on other subtasks
4. Estimated complexity (low, medium, high)

FORMAT YOUR RESPONSE AS A JSON OBJECT:
{{
  "overall_goal": "Brief restatement of the main goal",
  "subtasks": [
    {{
      "id": "subtask-1",
      "description": "Detailed description of the first subtask",
      "agent_type": "The most appropriate agent type (researcher, planner, executor, etc.)",
      "dependencies": [], // List of subtask IDs this depends on, or empty array
      "complexity": "low/medium/high",
      "estimated_time": "Rough time estimate"
    }},
    // Additional subtasks...
  ],
  "workflow_suggestion": "Brief description of suggested workflow approach",
  "potential_challenges": "Identification of potential issues or bottlenecks"
}}

Ensure your breakdown is comprehensive and covers all aspects of the task.
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _select_agent_for_task(self, task_details: str) -> str:
        """
        Select the appropriate agent type for a specific subtask.
        
        Args:
            task_details: Description and requirements of the subtask
            
        Returns:
            String containing the recommended agent type and justification
        """
        # Create a prompt for agent selection
        prompt = f"""
You are a coordination specialist focusing on agent selection.
Based on the following subtask details, determine the most appropriate type of agent:

Subtask: {task_details}

Consider the following agent types:
1. Researcher - Specialized in information gathering, analysis, and synthesis
2. Planner - Specialized in strategic planning and goal decomposition
3. Executor - Specialized in implementing plans and problem-solving
4. Any other specialized agent type that would be appropriate

FORMAT YOUR RESPONSE AS:
{{
  "recommended_agent_type": "The recommended agent type",
  "confidence": 0-100, // Confidence score
  "justification": "Explanation of why this agent type is appropriate",
  "alternative_agents": [
    {{
      "agent_type": "Alternative agent type",
      "suitability": 0-100 // Suitability score
    }},
    // Additional alternatives...
  ],
  "capabilities_needed": [
    "Specific capability required for this task",
    // Additional capabilities...
  ]
}}

Base your recommendation on the specific skills and capabilities required for the subtask.
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _create_workflow(self, workflow_requirements: str) -> str:
        """
        Create a workflow connecting multiple agents to complete a complex task.
        
        Args:
            workflow_requirements: Description of the workflow requirements
            
        Returns:
            String containing the workflow design
        """
        # Create a prompt for workflow creation
        prompt = f"""
You are a coordination specialist focusing on workflow design.
Design a workflow to address the following requirements:

Requirements: {workflow_requirements}

Your workflow should specify:
1. The agents involved and their roles
2. The sequence or graph of connections between agents
3. Decision points and conditional branches
4. Input/output relationships
5. Error handling approaches

FORMAT YOUR RESPONSE AS:
{{
  "workflow_name": "Descriptive name for the workflow",
  "entry_point": "The first agent/node in the workflow",
  "agents": [
    {{
      "name": "Descriptive name",
      "agent_type": "Type of agent",
      "role": "Specific role in this workflow",
      "inputs": ["Source of inputs for this agent"],
      "outputs": ["Destinations for outputs from this agent"]
    }},
    // Additional agents...
  ],
  "connections": [
    {{
      "from": "Source agent/node name",
      "to": "Destination agent/node name",
      "condition": "Optional condition for this connection",
      "data_passed": "Description of what data is passed"
    }},
    // Additional connections...
  ],
  "decision_points": [
    {{
      "description": "Description of the decision point",
      "options": [
        {{
          "condition": "Condition for this option",
          "next_step": "Next agent/node if condition is met"
        }},
        // Additional options...
      ]
    }},
    // Additional decision points...
  ],
  "error_handling": [
    {{
      "error_type": "Type of error to handle",
      "mitigation": "How to handle this error",
      "fallback": "Fallback approach if mitigation fails"
    }},
    // Additional error handlers...
  ]
}}

Design a workflow that efficiently achieves the overall goal while handling potential issues.
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def _allocate_task(self, task_and_agent_details: str) -> str:
        """
        Allocate a specific subtask to an appropriate agent.
        
        Args:
            task_and_agent_details: Details of the task and potential agents
            
        Returns:
            String containing the allocation decision and instructions
        """
        # Create a prompt for task allocation
        prompt = f"""
You are a coordination specialist focusing on task allocation.
Determine the best allocation for the following task and available agents:

{task_and_agent_details}

FORMAT YOUR RESPONSE AS:
{{
  "task_id": "Identifier for the task",
  "allocated_agent": "The agent to allocate this task to",
  "instructions": "Specific instructions for the agent",
  "inputs_required": [
    "Specific input needed by the agent",
    // Additional inputs...
  ],
  "expected_outputs": [
    "Expected output from the agent",
    // Additional outputs...
  ],
  "success_criteria": [
    "Criterion to determine if the task was completed successfully",
    // Additional criteria...
  ],
  "allocation_justification": "Explanation of why this agent was selected"
}}

Ensure your allocation matches the task requirements with agent capabilities.
"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        
        return response
    
    def create_agent_for_task(self, 
                             agent_type: str, 
                             task_description: str, 
                             agent_id: Optional[str] = None,
                             **kwargs) -> BaseAgent:
        """
        Create a specialized agent for a specific task.
        
        Args:
            agent_type: Type of agent to create
            task_description: Description of the task for this agent
            agent_id: Optional ID for the new agent
            **kwargs: Additional parameters for agent creation
            
        Returns:
            Created agent instance
        """
        # Generate a name based on the agent type and task
        agent_name = f"{agent_type.capitalize()} Agent for {task_description[:30]}..."
        
        # Create the agent using the factory
        if agent_type.lower() == "researcher":
            agent = self.agent_factory.create_researcher(
                agent_id=agent_id,
                agent_name=agent_name,
                **kwargs
            )
        elif agent_type.lower() == "planner":
            agent = self.agent_factory.create_planner(
                agent_id=agent_id,
                agent_name=agent_name,
                **kwargs
            )
        elif agent_type.lower() == "executor":
            agent = self.agent_factory.create_executor(
                agent_id=agent_id,
                agent_name=agent_name,
                **kwargs
            )
        else:
            # For other types, use the generic method
            agent = self.agent_factory.create_agent(
                agent_type=agent_type,
                agent_id=agent_id,
                agent_name=agent_name,
                **kwargs
            )
        
        # Track the created agent
        self.managed_agents[agent.agent_id] = agent
        
        logger.info(f"Created {agent_type} agent: {agent.agent_name} ({agent.agent_id})")
        return agent
    
    def create_workflow_for_task(self, 
                                task_description: str, 
                                workflow_name: Optional[str] = None) -> Tuple[str, WorkflowBuilder]:
        """
        Create a workflow for a complex task.
        
        Args:
            task_description: Description of the task to create a workflow for
            workflow_name: Optional name for the workflow
            
        Returns:
            Tuple of (workflow_id, workflow_builder)
        """
        # Generate a workflow ID and name
        workflow_id = f"workflow-{len(self.active_workflows) + 1}"
        if not workflow_name:
            workflow_name = f"Workflow for {task_description[:30]}..."
        
        # Create a new workflow builder
        builder = WorkflowBuilder(name=workflow_name)
        
        # Store the builder
        self.active_workflows[workflow_id] = builder
        
        logger.info(f"Created workflow: {workflow_name} ({workflow_id})")
        return workflow_id, builder
    
    def execute_workflow(self, workflow_id: str, initial_input: str) -> Dict[str, Any]:
        """
        Execute a workflow with the given input.
        
        Args:
            workflow_id: ID of the workflow to execute
            initial_input: Initial input to the workflow
            
        Returns:
            Execution results
        """
        if workflow_id not in self.active_workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        # Get the workflow builder
        builder = self.active_workflows[workflow_id]
        
        # Build the workflow
        workflow = builder.build()
        
        # Create initial state
        initial_state = GraphState(
            messages=[{"role": "user", "content": initial_input}],
            context={"task": initial_input},
            workflow_id=workflow_id,
            status="running",
            is_complete=False
        )
        
        # Execute the workflow
        logger.info(f"Executing workflow: {workflow_id}")
        result = workflow.invoke(initial_state)
        
        return result
    
    def run_with_coordination(self, task_description: str) -> str:
        """
        Run a task with full coordination capabilities.
        
        This high-level method analyzes the task, creates appropriate agents,
        builds a workflow, and executes it to completion.
        
        Args:
            task_description: Description of the complex task
            
        Returns:
            Final result from executing the coordinated workflow
        """
        # Step 1: Analyze the task
        analysis_result = self._analyze_task(task_description)
        
        # Process analysis result (assuming JSON response from LLM)
        try:
            import json
            analysis = json.loads(analysis_result)
        except:
            # Fallback in case the LLM doesn't return proper JSON
            logger.warning("Could not parse task analysis as JSON, using raw response")
            return f"Task coordination failed: {analysis_result}"
        
        # Step 2: Create a workflow
        workflow_id, builder = self.create_workflow_for_task(task_description)
        
        # Step 3: Create and add agents based on the analysis
        entry_point = None
        for i, subtask in enumerate(analysis.get("subtasks", [])):
            # Create an agent for this subtask
            agent_type = subtask.get("agent_type", "executor")
            agent = self.create_agent_for_task(
                agent_type=agent_type,
                task_description=subtask.get("description", f"Subtask {i+1}"),
                agent_id=subtask.get("id")
            )
            
            # Add the agent to the workflow
            node_name = subtask.get("id") or f"agent-{i+1}"
            builder.add_agent_node(node_name, agent)
            
            # Set as entry point if this is the first agent without dependencies
            if entry_point is None and not subtask.get("dependencies"):
                entry_point = node_name
        
        # Step 4: Connect agents based on dependencies
        for i, subtask in enumerate(analysis.get("subtasks", [])):
            subtask_id = subtask.get("id") or f"agent-{i+1}"
            
            # Get dependencies
            dependencies = subtask.get("dependencies", [])
            
            # Connect based on dependencies
            if dependencies:
                for dep_id in dependencies:
                    # Find the node name for this dependency
                    dep_node = dep_id
                    for j, other_task in enumerate(analysis.get("subtasks", [])):
                        if other_task.get("id") == dep_id:
                            dep_node = dep_id
                            break
                        elif j == dep_id:  # Handle numeric IDs
                            dep_node = f"agent-{j+1}"
                    
                    # Add the edge
                    builder.add_edge(dep_node, subtask_id)
            
            # Connect to entry point if no explicit dependencies and not the entry point
            elif subtask_id != entry_point:
                builder.add_edge(entry_point, subtask_id)
        
        # Add a final processing node
        builder.add_processing_node("finalize", lambda state: {
            **state,
            "status": "completed",
            "is_complete": True
        })
        
        # Connect the last agent to the finalize node
        for i, subtask in enumerate(analysis.get("subtasks", [])):
            subtask_id = subtask.get("id") or f"agent-{i+1}"
            has_outgoing = False
            
            # Check if this has outgoing connections
            for other_subtask in analysis.get("subtasks", []):
                if subtask_id in other_subtask.get("dependencies", []):
                    has_outgoing = True
                    break
            
            # If no outgoing connections, connect to finalize
            if not has_outgoing:
                builder.add_edge(subtask_id, "finalize")
        
        # Set the entry point
        builder.set_entry_point(entry_point)
        
        # Step 5: Execute the workflow
        result = self.execute_workflow(workflow_id, task_description)
        
        # Extract the final result
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            if messages and len(messages) > 0:
                return messages[-1].get("content", str(result))
        
        return str(result) 