"""
Basic example of using the shutdown module.

This example demonstrates:
1. Setting up the signal handlers
2. Registering positions, agents and resources
3. Manually initiating a shutdown
4. Monitoring shutdown progress

To run this example:
    python basic_usage.py
"""
import asyncio
import logging
import random
import signal
import sys
import time
import uuid
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import the shutdown module
from .shutdown import (
    get_shutdown_coordinator, 
    PositionCloseStrategy,
    Position,
    Agent,
    ResourceType,
    Resource,
    setup_signal_handlers
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("shutdown_example")

async def main():
    """Main example function."""
    logger.info("Starting shutdown module example")
    
    # Set up signal handlers for graceful shutdown
    setup_signal_handlers()
    
    # Get the shutdown coordinator singleton instance
    coordinator = get_shutdown_coordinator()
    
    # Configure timeouts
    coordinator.set_position_close_timeout(30.0)  # 30 seconds to close positions
    coordinator.set_agent_termination_timeout(20.0)  # 20 seconds to terminate agents
    coordinator.set_resource_cleanup_timeout(15.0)  # 15 seconds to clean resources
    
    # Register a progress callback
    coordinator.register_progress_callback(progress_callback)
    
    # Register some example positions, agents, and resources
    register_example_positions()
    register_example_agents()
    register_example_resources()
    
    logger.info("All example components registered")
    logger.info("Press Ctrl+C to trigger a signal-based shutdown")
    logger.info("Waiting 10 seconds before manual shutdown...")
    
    # Wait a bit to allow for manual testing via Ctrl+C
    for i in range(10, 0, -1):
        logger.info(f"Shutdown in {i} seconds...")
        await asyncio.sleep(1)
    
    # Initiate a manual shutdown
    logger.info("Initiating manual shutdown...")
    success = await coordinator.shutdown(reason="Example complete", 
                                        position_strategy=PositionCloseStrategy.GRADUAL.value,
                                        force_after_timeout=True)
    
    if success:
        logger.info("Shutdown completed successfully")
    else:
        logger.error("Shutdown completed with errors")
    
    # Final status
    status = coordinator.get_status()
    logger.info(f"Final status: {status}")


def progress_callback(status):
    """Callback function that's called when shutdown phase changes."""
    logger.info(f"Shutdown progress update: Phase={status['phase']}, "
                f"Elapsed={status['elapsed_time']:.2f}s")


def register_example_positions():
    """Register some example positions for demonstration."""
    position_closer = get_shutdown_coordinator().get_position_closer()
    
    # Create and register some example positions
    for i in range(5):
        # Create a mix of long and short positions
        size = random.uniform(0.1, 1.0)
        if i % 2 == 0:
            size = -size  # Make it a short position
            
        position = Position(
            position_id=f"pos-{uuid.uuid4()}",
            symbol=random.choice(["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]),
            size=size,
            entry_price=random.uniform(1.0, 1.5),
            agent_id=f"agent-{i % 3}"  # Assign to one of 3 agents
        )
        position_closer.register_position(position)
        logger.info(f"Registered position {position.position_id} ({position.symbol}): "
                   f"{position.size} @ {position.entry_price}")


def register_example_agents():
    """Register some example agents for demonstration."""
    agent_terminator = get_shutdown_coordinator().get_agent_terminator()
    
    # Create and register some example agents
    agent_types = ["Trend", "Scalping", "Arbitrage"]
    for i in range(3):
        agent = Agent(
            agent_id=f"agent-{i}",
            agent_type=agent_types[i],
            name=f"{agent_types[i]}-Agent-{i}"
        )
        # Higher priority for the first agent (will be terminated first)
        priority = 80 if i == 0 else (60 if i == 1 else 40)
        agent_terminator.register_agent(agent, priority=priority)
        logger.info(f"Registered agent {agent.agent_id} ({agent.name}) with priority {priority}")
    
    # Register a custom stop handler for the Trend agent type
    agent_terminator.register_stop_handler("Trend", custom_agent_stop_handler)


async def custom_agent_stop_handler(agent):
    """Custom handler for stopping a specific type of agent."""
    logger.info(f"Custom stop handler for {agent.name}...")
    # Simulate some custom shutdown logic
    await asyncio.sleep(0.5)
    logger.info(f"Custom stop handler completed for {agent.name}")
    return True


def register_example_resources():
    """Register some example resources for demonstration."""
    resource_cleaner = get_shutdown_coordinator().get_resource_cleaner()
    
    # Register a database connection
    db_conn = {"connection": "dummy_db_connection"}  # Simulate a DB connection
    resource_cleaner.register_database_connection(
        conn_id=f"db-{uuid.uuid4()}",
        connection_obj=db_conn,
        name="Main-Database",
        priority=90  # High priority, clean early
    )
    
    # Register a file handle
    file_obj = {"handle": "dummy_file_handle"}  # Simulate a file handle
    resource_cleaner.register_file_handle(
        file_id=f"file-{uuid.uuid4()}",
        file_obj=file_obj,
        name="Log-File",
        priority=60
    )
    
    # Register an API connection
    api_obj = {"connection": "dummy_api_connection"}  # Simulate an API connection
    resource_cleaner.register_api_connection(
        api_id=f"api-{uuid.uuid4()}",
        api_obj=api_obj,
        name="Trading-API",
        priority=85
    )
    
    # Register a custom resource with a custom handler
    custom_obj = {"resource": "dummy_custom_resource"}
    resource_cleaner.register_custom_resource(
        resource_id=f"custom-{uuid.uuid4()}",
        custom_type="CACHE",
        resource_obj=custom_obj,
        name="Memory-Cache",
        description="In-memory cache for market data",
        cleanup_handler=custom_resource_cleanup_handler,
        priority=75
    )


async def custom_resource_cleanup_handler(resource):
    """Custom handler for cleaning up a specific resource."""
    logger.info(f"Custom cleanup handler for {resource.name}...")
    # Simulate some custom cleanup logic
    await asyncio.sleep(0.3)
    logger.info(f"Custom cleanup handler completed for {resource.name}")
    return True


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExample terminated by keyboard interrupt")
    finally:
        print("Example completed.") 