"""
Agent Workflow Examples

This module provides concrete examples of agent workflows using the LangGraph
orchestration framework for common agent use cases.
"""

import os
from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool
from langchain.tools.base import StructuredTool
from langchain.pydantic_v1 import BaseModel, Field

from .orchestration import (
    WorkflowBuilder,
    create_research_planning_execution_workflow,
    create_question_answering_workflow
)
from .factory import AgentFactory
from ..llm.client import get_llm_model
from ..utils.logging.logger import get_logger

logger = get_logger()


def run_trading_strategy_workflow(
    query: str,
    openai_api_key: Optional[str] = None,
    model_name: str = "gpt-3.5-turbo",
    with_visualization: bool = False
) -> Dict[str, Any]:
    """
    Run a workflow for developing and backtesting trading strategies.
    
    Args:
        query: User query about trading strategy
        openai_api_key: OpenAI API key
        model_name: LLM model name
        with_visualization: Whether to generate a visualization
        
    Returns:
        Final state of the workflow
    """
    # Define trading-specific tools
    class HistoricalDataInput(BaseModel):
        """Input for retrieving historical market data."""
        symbol: str = Field(..., description="Trading symbol (e.g., 'EURUSD', 'BTCUSD')")
        start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
        end_date: str = Field(..., description="End date in YYYY-MM-DD format")
        interval: str = Field("1d", description="Data interval (1m, 5m, 15m, 1h, 1d)")

    def get_historical_data(inputs: HistoricalDataInput) -> str:
        """
        Retrieve historical market data for analysis.
        
        Args:
            inputs: Data retrieval parameters
            
        Returns:
            Mock data summary
        """
        # In a real implementation, this would query a market data API
        return f"Retrieved {inputs.interval} data for {inputs.symbol} from {inputs.start_date} to {inputs.end_date}. " \
               f"[Mock data summary: 500 candles with OHLCV values]"

    class BacktestInput(BaseModel):
        """Input for backtesting a trading strategy."""
        strategy: str = Field(..., description="Trading strategy description")
        symbol: str = Field(..., description="Trading symbol")
        start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
        end_date: str = Field(..., description="End date in YYYY-MM-DD format")
        position_size: float = Field(1.0, description="Position size per trade")

    def backtest_strategy(inputs: BacktestInput) -> str:
        """
        Backtest a trading strategy on historical data.
        
        Args:
            inputs: Backtest parameters
            
        Returns:
            Mock backtest results
        """
        # In a real implementation, this would execute a backtest
        return f"Backtested strategy on {inputs.symbol} from {inputs.start_date} to {inputs.end_date}. " \
               f"[Mock results: 45 trades, 60% win rate, 1.8 profit factor, 15% max drawdown]"

    # Create structured tools
    historical_data_tool = StructuredTool.from_function(
        func=get_historical_data,
        name="get_historical_data",
        description="Retrieve historical market data for analysis",
        args_schema=HistoricalDataInput
    )

    backtest_tool = StructuredTool.from_function(
        func=backtest_strategy,
        name="backtest_strategy",
        description="Backtest a trading strategy on historical data",
        args_schema=BacktestInput
    )

    tools = [historical_data_tool, backtest_tool]

    # Create a custom workflow
    builder = WorkflowBuilder(
        name="trading_strategy_workflow",
        checkpoint_dir="./checkpoints/trading" if os.path.exists("./checkpoints") else None
    )
    
    # Create specialized agents
    market_analyst = AgentFactory.create_agent(
        agent_type="researcher",
        agent_name="Market Analyst",
        agent_description="Specialized in analyzing market data and identifying patterns.",
        system_message="You are a Market Analyst specialized in analyzing financial markets. "
                      "Use the available tools to gather and analyze market data.",
        tools=[historical_data_tool],
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    strategy_developer = AgentFactory.create_agent(
        agent_type="planner",
        agent_name="Strategy Developer",
        agent_description="Specialized in developing trading strategies based on market analysis.",
        system_message="You are a Strategy Developer specialized in creating trading strategies. "
                      "Your goal is to develop detailed, rule-based trading strategies based on market analysis.",
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    backtest_engineer = AgentFactory.create_agent(
        agent_type="executor",
        agent_name="Backtest Engineer",
        agent_description="Specialized in testing trading strategies using historical data.",
        system_message="You are a Backtest Engineer specialized in testing trading strategies. "
                      "Use the backtest tool to evaluate strategy performance on historical data.",
        tools=[backtest_tool],
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    # Add agents as nodes
    builder.add_agent_node("market_analyst", market_analyst)
    builder.add_agent_node("strategy_developer", strategy_developer)
    builder.add_agent_node("backtest_engineer", backtest_engineer)
    
    # Add tool nodes
    builder.add_tool_node("trading_tools", tools)
    
    # Add human intervention for critical decisions
    builder.add_human_intervention_node("human_review")
    
    # Add processing nodes
    def prepare_strategy_request(state):
        """Prepare the state for strategy development."""
        state["context"] = state.get("context", {})
        state["context"]["analysis_complete"] = True
        return state
    
    def prepare_backtest_request(state):
        """Prepare the state for backtesting."""
        state["context"] = state.get("context", {})
        state["context"]["strategy_complete"] = True
        return state
    
    def finalize_workflow(state):
        """Finalize the workflow results."""
        state["status"] = "completed"
        state["is_complete"] = True
        
        # Extract final strategy and backtest results
        strategy_info = None
        backtest_results = None
        
        for msg in state.get("messages", []):
            if isinstance(msg, dict):
                content = msg.get("content", "")
                agent = msg.get("agent", "")
                
                if agent == "strategy_developer" and "strategy" in content.lower():
                    strategy_info = content
                
                if agent == "backtest_engineer" and "backtest" in content.lower():
                    backtest_results = content
        
        # Add to artifacts
        if strategy_info:
            state["artifacts"] = state.get("artifacts", []) + [{
                "type": "strategy",
                "content": strategy_info
            }]
            
        if backtest_results:
            state["artifacts"] = state.get("artifacts", []) + [{
                "type": "backtest_results",
                "content": backtest_results
            }]
        
        return state
    
    builder.add_processing_node("prepare_strategy", prepare_strategy_request)
    builder.add_processing_node("prepare_backtest", prepare_backtest_request)
    builder.add_processing_node("finalize", finalize_workflow)
    
    # Add conditional routing
    def needs_market_analysis(state):
        """Check if market analysis is needed."""
        if not state.get("context", {}).get("analysis_complete", False):
            return True
        
        # Check message content for analysis requests
        if state.get("messages", []):
            last_msg = state["messages"][-1]
            if isinstance(last_msg, dict):
                content = last_msg.get("content", "").lower()
                analysis_indicators = ["need analysis", "analyze market", "market data"]
                return any(indicator in content for indicator in analysis_indicators)
        
        return False
    
    def needs_strategy_development(state):
        """Check if strategy development is needed."""
        # If we already have a strategy but need to refine it based on backtest
        if state.get("context", {}).get("strategy_complete", False):
            if state.get("context", {}).get("backtest_complete", False):
                # Look for backtest feedback
                if state.get("messages", []):
                    last_msg = state["messages"][-1]
                    if isinstance(last_msg, dict):
                        content = last_msg.get("content", "").lower()
                        refine_indicators = ["refine strategy", "improve strategy", "adjust parameters"]
                        return any(indicator in content for indicator in refine_indicators)
            return False
        
        # If analysis is complete, proceed to strategy development
        return state.get("context", {}).get("analysis_complete", False)
    
    def needs_backtesting(state):
        """Check if backtesting is needed."""
        return state.get("context", {}).get("strategy_complete", False)
    
    def needs_human_review(state):
        """Check if human review is needed."""
        # Check message content for review requests
        if state.get("messages", []):
            last_msg = state["messages"][-1]
            if isinstance(last_msg, dict):
                content = last_msg.get("content", "").lower()
                review_indicators = ["human review", "need confirmation", "please verify"]
                return any(indicator in content for indicator in review_indicators)
        
        return False
    
    def is_workflow_complete(state):
        """Check if the workflow is complete."""
        if state.get("context", {}).get("strategy_complete", False) and \
           state.get("context", {}).get("backtest_complete", False):
            return True
        return False
    
    # Add edges
    builder.add_edge("market_analyst", "prepare_strategy")
    builder.add_edge("strategy_developer", "prepare_backtest")
    
    builder.add_conditional_edge("prepare_strategy", "strategy_developer", lambda s: True)
    builder.add_conditional_edge("prepare_backtest", "backtest_engineer", lambda s: True)
    
    builder.add_conditional_edge("backtest_engineer", "market_analyst", needs_market_analysis)
    builder.add_conditional_edge("backtest_engineer", "strategy_developer", needs_strategy_development)
    builder.add_conditional_edge("backtest_engineer", "human_review", needs_human_review)
    builder.add_conditional_edge("backtest_engineer", "finalize", is_workflow_complete)
    
    builder.add_edge("human_review", "backtest_engineer")
    builder.add_edge("finalize", "END")
    
    # Set entry point
    builder.set_entry_point("market_analyst")
    
    # Build the graph
    workflow = builder.build()
    
    # Generate visualization if requested
    if with_visualization:
        builder.visualize("trading_strategy_workflow")
    
    # Initialize state with query
    inputs = {
        "messages": [{"role": "user", "content": query}],
        "context": {"task": query}
    }
    
    # Run the workflow
    logger.info(f"Running trading strategy workflow with query: {query}")
    result = workflow.invoke(inputs)
    
    return result


def run_code_generation_workflow(
    query: str,
    openai_api_key: Optional[str] = None,
    model_name: str = "gpt-3.5-turbo",
    with_visualization: bool = False
) -> Dict[str, Any]:
    """
    Run a workflow for generating and refining code.
    
    Args:
        query: User query about code generation
        openai_api_key: OpenAI API key
        model_name: LLM model name
        with_visualization: Whether to generate a visualization
        
    Returns:
        Final state of the workflow
    """
    # Create a custom workflow
    builder = WorkflowBuilder(
        name="code_generation_workflow",
        checkpoint_dir="./checkpoints/code" if os.path.exists("./checkpoints") else None
    )
    
    # Create specialized agents
    requirements_analyst = AgentFactory.create_agent(
        agent_type="researcher",
        agent_name="Requirements Analyst",
        agent_description="Specialized in analyzing requirements and planning software implementations.",
        system_message="You are a Requirements Analyst specialized in software development. "
                      "Your goal is to analyze user requirements and create a detailed implementation plan.",
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    code_generator = AgentFactory.create_agent(
        agent_type="executor",
        agent_name="Code Generator",
        agent_description="Specialized in writing high-quality, well-documented code.",
        system_message="You are a Code Generator specialized in writing clean, efficient code. "
                     "Generate code that meets the specified requirements with proper documentation.",
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    code_reviewer = AgentFactory.create_agent(
        agent_type="planner",
        agent_name="Code Reviewer",
        agent_description="Specialized in reviewing code for bugs, performance issues, and best practices.",
        system_message="You are a Code Reviewer specialized in identifying issues and suggesting improvements. "
                     "Focus on code quality, performance, security, and adherence to best practices.",
        openai_api_key=openai_api_key,
        model_name=model_name
    )
    
    # Add agents as nodes
    builder.add_agent_node("requirements_analyst", requirements_analyst)
    builder.add_agent_node("code_generator", code_generator)
    builder.add_agent_node("code_reviewer", code_reviewer)
    
    # Add human intervention for code approval
    builder.add_human_intervention_node("human_review")
    
    # Add processing nodes
    def prepare_for_coding(state):
        """Prepare the state for code generation."""
        state["context"] = state.get("context", {})
        state["context"]["requirements_analyzed"] = True
        return state
    
    def prepare_for_review(state):
        """Prepare the state for code review."""
        state["context"] = state.get("context", {})
        state["context"]["code_generated"] = True
        return state
    
    def finalize_workflow(state):
        """Finalize the workflow results."""
        state["status"] = "completed"
        state["is_complete"] = True
        
        # Extract requirements, code, and review feedback
        requirements = None
        code = None
        review = None
        
        for msg in state.get("messages", []):
            if isinstance(msg, dict):
                content = msg.get("content", "")
                agent = msg.get("agent", "")
                
                if agent == "requirements_analyst":
                    requirements = content
                
                if agent == "code_generator" and "```" in content:
                    code = content
                
                if agent == "code_reviewer":
                    review = content
        
        # Add to artifacts
        if requirements:
            state["artifacts"] = state.get("artifacts", []) + [{
                "type": "requirements",
                "content": requirements
            }]
            
        if code:
            state["artifacts"] = state.get("artifacts", []) + [{
                "type": "code",
                "content": code
            }]
            
        if review:
            state["artifacts"] = state.get("artifacts", []) + [{
                "type": "review",
                "content": review
            }]
        
        return state
    
    builder.add_processing_node("prepare_for_coding", prepare_for_coding)
    builder.add_processing_node("prepare_for_review", prepare_for_review)
    builder.add_processing_node("finalize", finalize_workflow)
    
    # Add conditional routing
    def needs_requirements_analysis(state):
        """Check if requirements analysis is needed."""
        if state.get("messages", []):
            last_msg = state["messages"][-1]
            if isinstance(last_msg, dict):
                content = last_msg.get("content", "").lower()
                analysis_indicators = ["clarify requirements", "need more details", "requirements unclear"]
                return any(indicator in content for indicator in analysis_indicators)
        return False
    
    def needs_code_generation(state):
        """Check if code generation is needed."""
        # If we're coming from requirements analysis
        if state.get("context", {}).get("requirements_analyzed", False):
            return True
        
        # If we need to regenerate code based on review feedback
        if state.get("context", {}).get("code_reviewed", False):
            if state.get("messages", []):
                last_msg = state["messages"][-1]
                if isinstance(last_msg, dict):
                    content = last_msg.get("content", "").lower()
                    regenerate_indicators = ["regenerate", "fix issues", "implement feedback"]
                    return any(indicator in content for indicator in regenerate_indicators)
        
        return False
    
    def needs_code_review(state):
        """Check if code review is needed."""
        return state.get("context", {}).get("code_generated", False)
    
    def needs_human_review(state):
        """Check if human review is needed."""
        # If code has been reviewed, get human approval
        if state.get("context", {}).get("code_reviewed", True):
            return True
        
        # Check message content for review requests
        if state.get("messages", []):
            last_msg = state["messages"][-1]
            if isinstance(last_msg, dict):
                content = last_msg.get("content", "").lower()
                review_indicators = ["human review", "need approval", "please verify"]
                return any(indicator in content for indicator in review_indicators)
        
        return False
    
    def is_code_approved(state):
        """Check if the code is approved and workflow can complete."""
        # Check human feedback for approval
        human_feedback = state.get("human_feedback", "")
        if human_feedback and "approved" in human_feedback.lower():
            return True
        
        # Check reviewer feedback
        if state.get("messages", []):
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, dict) and msg.get("agent") == "code_reviewer":
                    content = msg.get("content", "").lower()
                    approval_indicators = ["code looks good", "no issues found", "approved"]
                    issues_indicators = ["found issues", "needs fixing", "problems identified"]
                    
                    if any(indicator in content for indicator in approval_indicators) and \
                       not any(indicator in content for indicator in issues_indicators):
                        return True
        
        return False
    
    # Add edges
    builder.add_edge("requirements_analyst", "prepare_for_coding")
    builder.add_edge("code_generator", "prepare_for_review")
    
    builder.add_conditional_edge("prepare_for_coding", "code_generator", lambda s: True)
    builder.add_conditional_edge("prepare_for_review", "code_reviewer", lambda s: True)
    
    builder.add_conditional_edge("code_reviewer", "requirements_analyst", needs_requirements_analysis)
    builder.add_conditional_edge("code_reviewer", "code_generator", needs_code_generation)
    builder.add_conditional_edge("code_reviewer", "human_review", needs_human_review)
    
    builder.add_conditional_edge("human_review", "finalize", is_code_approved)
    builder.add_conditional_edge("human_review", "code_generator", lambda s: not is_code_approved(s))
    
    builder.add_edge("finalize", "END")
    
    # Set entry point
    builder.set_entry_point("requirements_analyst")
    
    # Build the graph
    workflow = builder.build()
    
    # Generate visualization if requested
    if with_visualization:
        builder.visualize("code_generation_workflow")
    
    # Initialize state with query
    inputs = {
        "messages": [{"role": "user", "content": query}],
        "context": {"task": query}
    }
    
    # Run the workflow
    logger.info(f"Running code generation workflow with query: {query}")
    result = workflow.invoke(inputs)
    
    return result


# Example usage
if __name__ == "__main__":
    # Get API key from environment
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    
    # Example trading strategy query
    trading_query = "Develop a mean reversion trading strategy for EURUSD that uses Bollinger Bands"
    trading_result = run_trading_strategy_workflow(
        trading_query,
        openai_api_key=openai_api_key,
        with_visualization=True
    )
    
    print("\n=== Trading Strategy Workflow Results ===")
    for artifact in trading_result.get("artifacts", []):
        print(f"\n{artifact['type'].upper()}:")
        print(artifact['content'])
    
    # Example code generation query
    code_query = "Create a Python function that implements the Fibonacci sequence using memoization"
    code_result = run_code_generation_workflow(
        code_query,
        openai_api_key=openai_api_key,
        with_visualization=True
    )
    
    print("\n=== Code Generation Workflow Results ===")
    for artifact in code_result.get("artifacts", []):
        print(f"\n{artifact['type'].upper()}:")
        print(artifact['content']) 