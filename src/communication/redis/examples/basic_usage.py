"""
Redis Communication Module - Basic Usage Example

This example demonstrates how to use the Redis communication module
for sending/receiving messages between components.
"""

import asyncio
import sys
import os
import time
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from .redis import (
    create_communication_facade,
    MessageType,
    MessagePriority
)

async def orchestrator_example():
    """Example of using the communication module as an orchestrator."""
    print("Starting orchestrator example...")
    
    # Create the facade for the orchestrator
    orchestrator = await create_communication_facade(
        component_id="orchestrator-1",
        component_type="orchestrator"
    )
    
    # Register message handlers
    await orchestrator.register_message_handler(
        MessageType.STATUS,
        handle_status_message
    )
    
    await orchestrator.register_message_handler(
        MessageType.RESULT,
        handle_result_message
    )
    
    # Start the facade
    await orchestrator.start()
    
    try:
        # Send some commands to agents
        for i in range(3):
            agent_id = f"agent-{i+1}"
            command_id = await orchestrator.send_command(
                command="collect_data",
                recipient_id=agent_id,
                parameters={
                    "symbols": ["EUR/USD", "GBP/USD"],
                    "timeframe": "1h",
                    "start_time": datetime.now().isoformat()
                },
                priority=MessagePriority.HIGH
            )
            print(f"Sent command to {agent_id}, message ID: {command_id}")
        
        # Wait for responses
        print("Waiting for responses...")
        await asyncio.sleep(60)
    
    finally:
        # Stop the facade
        await orchestrator.stop()
        print("Orchestrator example finished")

async def agent_example(agent_id: str):
    """Example of using the communication module as an agent."""
    print(f"Starting agent example for {agent_id}...")
    
    # Create the facade for the agent
    agent = await create_communication_facade(
        component_id=agent_id,
        component_type="agent"
    )
    
    # Register message handlers
    await agent.register_message_handler(
        MessageType.COMMAND,
        handle_command_message
    )
    
    # Start the facade
    await agent.start()
    
    try:
        # Send a status update
        await agent.send_status(
            status="online",
            recipient_id="orchestrator-1",
            details={
                "uptime": 0,
                "memory_usage": 20.5,
                "cpu_usage": 5.2
            }
        )
        
        # Run for a while, handling commands
        print(f"Agent {agent_id} running, waiting for commands...")
        await asyncio.sleep(120)
    
    finally:
        # Stop the facade
        await agent.stop()
        print(f"Agent {agent_id} finished")

async def handle_status_message(message):
    """Handle a status message."""
    print(f"Received status from {message.sender_id}: {message.status}")
    print(f"Details: {json.dumps(message.details, indent=2)}")
    return True

async def handle_result_message(message):
    """Handle a result message."""
    print(f"Received result from {message.sender_id} for command {message.command_id}")
    print(f"Success: {message.success}")
    if message.success:
        print(f"Data: {json.dumps(message.data, indent=2)}")
    else:
        print(f"Error: {message.error}")
    return True

async def handle_command_message(message):
    """Handle a command message."""
    print(f"Received command from {message.sender_id}: {message.command}")
    print(f"Parameters: {json.dumps(message.parameters, indent=2)}")
    
    # Simulate processing
    print(f"Processing command...")
    await asyncio.sleep(2)
    
    # Send result
    await agent.send_result(
        command_id=message.message_id,
        recipient_id=message.sender_id,
        success=True,
        data={
            "result": "Command executed successfully",
            "timestamp": datetime.now().isoformat()
        }
    )
    
    return True

if __name__ == "__main__":
    # Choose which example to run based on command-line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        agent_id = sys.argv[2] if len(sys.argv) > 2 else "agent-1"
        asyncio.run(agent_example(agent_id))
    else:
        asyncio.run(orchestrator_example()) 