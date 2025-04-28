"""
Example Workflow Using Process Manager and Task Groups

This module provides an example of how to use the ProcessManager and TaskGroup
classes together to create complex agent workflows.
"""

import asyncio
import os
from typing import Dict, List, Any, Optional

from ...utils.logging.logger import get_logger
from .factory import AgentFactory
from .orchestration.process_manager import ProcessManager
from .orchestration.task_group import TaskGroup, TaskGroupManager

logger = get_logger()


async def create_market_analysis_workflow(
    symbols: List[str],
    timeframes: List[str],
    analysis_types: List[str] = None
) -> TaskGroupManager:
    """
    Create and start a market analysis workflow with multiple agent groups.
    
    This workflow creates several task groups:
    1. Data Collection - Agents that fetch market data
    2. Technical Analysis - Agents that analyze price action
    3. Fundamental Analysis - Agents that analyze news and fundamentals
    4. Signal Generation - Agents that generate trading signals
    
    Args:
        symbols: List of forex symbols to analyze
        timeframes: List of timeframes to analyze
        analysis_types: List of analysis types to perform (defaults to all)
        
    Returns:
        TaskGroupManager with the configured workflow
    """
    # Default analysis types if not specified
    if analysis_types is None:
        analysis_types = ["trend", "momentum", "volatility", "sentiment"]
    
    # Create process manager
    process_manager = ProcessManager()
    await process_manager.start()
    
    # Create task group manager
    manager = TaskGroupManager(process_manager)
    
    # Create data collection group
    data_group = manager.create_task_group(
        group_id="data_collection",
        name="Market Data Collection",
        description="Agents responsible for collecting market data"
    )
    
    # Create technical analysis group (depends on data collection)
    tech_group = manager.create_task_group(
        group_id="technical_analysis",
        name="Technical Analysis",
        description="Agents performing technical analysis on market data",
        depends_on=["data_collection"]
    )
    
    # Create fundamental analysis group (depends on data collection)
    fund_group = manager.create_task_group(
        group_id="fundamental_analysis",
        name="Fundamental Analysis",
        description="Agents analyzing fundamental factors and news",
        depends_on=["data_collection"]
    )
    
    # Create signal generation group (depends on both analysis groups)
    signal_group = manager.create_task_group(
        group_id="signal_generation",
        name="Signal Generation",
        description="Agents that generate trading signals based on analysis",
        depends_on=["technical_analysis", "fundamental_analysis"]
    )
    
    # Configure data collection agents
    for symbol in symbols:
        for timeframe in timeframes:
            data_group.add_agent_config({
                "agent_type": "data_collector",
                "agent_id": f"data-{symbol}-{timeframe}",
                "agent_name": f"{symbol} {timeframe} Data Collector",
                "config": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "lookback_periods": 500
                }
            })
    
    # Configure technical analysis agents
    for symbol in symbols:
        for timeframe in timeframes:
            for analysis_type in [a for a in analysis_types if a in ["trend", "momentum", "volatility"]]:
                tech_group.add_agent_config({
                    "agent_type": "technical_analyzer",
                    "agent_id": f"tech-{analysis_type}-{symbol}-{timeframe}",
                    "agent_name": f"{symbol} {timeframe} {analysis_type.capitalize()} Analyzer",
                    "config": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "analysis_type": analysis_type
                    }
                })
    
    # Configure fundamental analysis agents
    for symbol in symbols:
        if "sentiment" in analysis_types:
            fund_group.add_agent_config({
                "agent_type": "news_analyzer",
                "agent_id": f"news-{symbol}",
                "agent_name": f"{symbol} News Analyzer",
                "config": {
                    "symbol": symbol,
                    "use_sentiment_analysis": True
                }
            })
    
    # Configure signal generation agents
    for symbol in symbols:
        signal_group.add_agent_config({
            "agent_type": "signal_generator",
            "agent_id": f"signal-{symbol}",
            "agent_name": f"{symbol} Signal Generator",
            "config": {
                "symbol": symbol,
                "timeframes": timeframes,
                "use_technical": True,
                "use_fundamental": True,
                "signal_threshold": 0.7
            }
        })
    
    return manager


async def run_workflow_example():
    """Run the example workflow with a typical forex analysis setup."""
    symbols = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    timeframes = ["1h", "4h", "1d"]
    
    try:
        # Create the workflow
        logger.info("Creating market analysis workflow...")
        workflow_manager = await create_market_analysis_workflow(
            symbols=symbols,
            timeframes=timeframes
        )
        
        # Start the workflow (starting with independent groups)
        logger.info("Starting workflow execution...")
        started_groups = await workflow_manager.start_all_independent_groups()
        logger.info(f"Started initial groups: {started_groups}")
        
        # Wait for all groups to complete
        logger.info("Waiting for workflow completion...")
        await workflow_manager.wait_for_all_groups()
        
        # Get workflow metrics
        metrics = workflow_manager.get_all_metrics()
        logger.info(f"Workflow completed with {len(metrics['groups'])} top-level groups")
        
        # Extract completion status for each group
        for group_id, group_metrics in metrics["groups"].items():
            logger.info(f"Group '{group_metrics['name']}' status: {group_metrics['status']}")
            if group_metrics['duration'] is not None:
                logger.info(f"  Duration: {group_metrics['duration']:.2f} seconds")
            logger.info(f"  Agents: {group_metrics['agent_count']}")
        
        # Graceful shutdown of the process manager
        logger.info("Shutting down process manager...")
        await workflow_manager.process_manager.shutdown()
        logger.info("Workflow example completed successfully")
        
    except Exception as e:
        logger.error(f"Error in workflow execution: {str(e)}")
        # Ensure the process manager is shut down
        try:
            await workflow_manager.process_manager.shutdown()
        except:
            pass
        raise


async def run_custom_workflow(
    symbols: List[str],
    timeframes: List[str],
    analysis_types: List[str],
    run_time_seconds: Optional[int] = None
):
    """
    Run a custom market analysis workflow with the specified parameters.
    
    Args:
        symbols: List of forex symbols to analyze
        timeframes: List of timeframes to analyze
        analysis_types: List of analysis types to perform
        run_time_seconds: Optional maximum runtime in seconds
    """
    workflow_manager = None
    
    try:
        # Create the workflow
        logger.info(f"Creating custom workflow for {len(symbols)} symbols...")
        workflow_manager = await create_market_analysis_workflow(
            symbols=symbols,
            timeframes=timeframes,
            analysis_types=analysis_types
        )
        
        # Start the workflow
        logger.info("Starting workflow execution...")
        started_groups = await workflow_manager.start_all_independent_groups()
        logger.info(f"Started initial groups: {started_groups}")
        
        # If run_time_seconds is specified, run for that duration
        if run_time_seconds:
            logger.info(f"Workflow will run for {run_time_seconds} seconds")
            try:
                # Wait for completion or timeout
                await asyncio.wait_for(
                    workflow_manager.wait_for_all_groups(),
                    timeout=run_time_seconds
                )
                logger.info("Workflow completed within specified time")
            except asyncio.TimeoutError:
                logger.info(f"Workflow reached maximum runtime of {run_time_seconds} seconds")
                # Cancel all groups
                await workflow_manager.cancel_all_groups(reason="Maximum runtime reached")
        else:
            # Wait indefinitely for completion
            await workflow_manager.wait_for_all_groups()
            logger.info("Workflow completed successfully")
        
        # Get and return metrics
        return workflow_manager.get_all_metrics()
    
    except Exception as e:
        logger.error(f"Error in custom workflow: {str(e)}")
        raise
    finally:
        # Ensure process manager is shut down
        if workflow_manager:
            await workflow_manager.process_manager.shutdown()


if __name__ == "__main__":
    # Run the example workflow
    asyncio.run(run_workflow_example()) 