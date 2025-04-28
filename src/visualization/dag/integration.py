"""
Integration layer between the DAG visualization and the agent orchestrator.

This module provides classes to connect the visualization to the agent orchestrator,
allowing the visualization to react to changes in the agent system.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .dag.model import DAGModel, NodeData, EdgeData, AgentStatus

# Set up logging
logger = logging.getLogger(__name__)


class AgentDAGIntegration:
    """
    Integration layer between the DAG visualization and the agent orchestrator.
    
    This class connects to the agent orchestrator's event system and updates
    the DAG model accordingly.
    """
    
    def __init__(self, dag_model: DAGModel):
        """
        Initialize the integration with a DAG model.
        
        Args:
            dag_model: The DAG model to update.
        """
        self.dag_model = dag_model
        self.orchestrator = None
        
    async def connect_to_orchestrator(self, orchestrator: Any) -> None:
        """
        Connect to the agent orchestrator's event system.
        
        This method registers callbacks for agent events and loads
        existing agents into the DAG model.
        
        Args:
            orchestrator: The agent orchestrator instance.
        """
        self.orchestrator = orchestrator
        
        # Register for agent events
        await orchestrator.on_event("agent_registered", self._on_agent_registered)
        await orchestrator.on_event("agent_deregistered", self._on_agent_deregistered)
        await orchestrator.on_event("agent_status_changed", self._on_agent_status_changed)
        await orchestrator.on_event("agent_heartbeat", self._on_agent_heartbeat)
        await orchestrator.on_event("agent_error", self._on_agent_error)
        
        # Load existing agents
        agents = await orchestrator.get_all_agents()
        for agent in agents:
            await self._on_agent_registered(agent.id, agent)
            
        logger.info(f"Connected to orchestrator with {len(agents)} existing agents")
    
    async def _on_agent_registered(self, agent_id: str, metadata: Any) -> None:
        """
        Handle agent registration events.
        
        Args:
            agent_id: The ID of the registered agent.
            metadata: The agent metadata.
        """
        try:
            # Create a node for the agent
            node = NodeData(
                id=agent_id,
                name=metadata.name,
                node_type=metadata.agent_type,
                status=metadata.status,
                metadata=metadata.to_dict() if hasattr(metadata, "to_dict") else {}
            )
            
            # Add the node to the DAG model
            self.dag_model.add_node(node)
            logger.debug(f"Added agent node: {agent_id}")
            
            # Look for relationships to add based on agent configuration
            # This is implementation specific and depends on how agents are related
            await self._discover_relationships(agent_id, metadata)
            
        except Exception as e:
            logger.error(f"Error handling agent registration for {agent_id}: {str(e)}")
    
    async def _on_agent_deregistered(self, agent_id: str, metadata: Any) -> None:
        """
        Handle agent deregistration events.
        
        Args:
            agent_id: The ID of the deregistered agent.
            metadata: The agent metadata.
        """
        try:
            # Remove the agent node from the DAG model
            self.dag_model.remove_node(agent_id)
            logger.debug(f"Removed agent node: {agent_id}")
            
        except Exception as e:
            logger.error(f"Error handling agent deregistration for {agent_id}: {str(e)}")
    
    async def _on_agent_status_changed(self, agent_id: str, metadata: Any) -> None:
        """
        Handle agent status change events.
        
        Args:
            agent_id: The ID of the agent.
            metadata: The updated agent metadata.
        """
        try:
            # Update the agent node in the DAG model
            self.dag_model.update_node(
                agent_id,
                status=metadata.status
            )
            logger.debug(f"Updated agent node status: {agent_id} -> {metadata.status.value}")
            
        except Exception as e:
            logger.error(f"Error handling agent status change for {agent_id}: {str(e)}")
    
    async def _on_agent_heartbeat(self, agent_id: str, metadata: Any) -> None:
        """
        Handle agent heartbeat events.
        
        Args:
            agent_id: The ID of the agent.
            metadata: The agent metadata.
        """
        # Heartbeats don't necessarily change any visual attributes,
        # but we could use them to update a "last seen" timestamp or similar
        try:
            # If the agent already has an updated timestamp in the model,
            # we don't need to do anything here
            pass
            
        except Exception as e:
            logger.error(f"Error handling agent heartbeat for {agent_id}: {str(e)}")
    
    async def _on_agent_error(self, agent_id: str, error_data: Dict[str, Any]) -> None:
        """
        Handle agent error events.
        
        Args:
            agent_id: The ID of the agent.
            error_data: Information about the error.
        """
        try:
            # We could update the node to reflect the error (e.g., change color)
            # or we could add a log entry to an edge if relevant
            error_msg = error_data.get('error', 'Unknown error')
            logger.warning(f"Agent error: {agent_id} - {error_msg}")
            
            # Update the agent node to reflect the error
            self.dag_model.update_node(
                agent_id,
                metadata={"last_error": error_msg, "error_time": asyncio.get_event_loop().time()}
            )
            
        except Exception as e:
            logger.error(f"Error handling agent error for {agent_id}: {str(e)}")
    
    async def _discover_relationships(self, agent_id: str, metadata: Any) -> None:
        """
        Discover and add relationships for a new agent.
        
        This method examines the agent metadata to determine how it relates
        to other agents in the system, and adds appropriate edges.
        
        Args:
            agent_id: The ID of the agent.
            metadata: The agent metadata.
        """
        try:
            # This is implementation specific and depends on how agents are related
            # For example, if agents have dependencies defined in their config:
            config = metadata.config if hasattr(metadata, "config") else {}
            
            # Example: Check for upstream and downstream dependencies
            upstream_agents = config.get('upstream_agents', [])
            downstream_agents = config.get('downstream_agents', [])
            
            # Add edges for upstream dependencies (agents that this agent consumes data from)
            for upstream_id in upstream_agents:
                if upstream_id in self.dag_model.nodes:
                    edge = EdgeData(
                        source_id=upstream_id,
                        target_id=agent_id,
                        edge_type="data_flow"
                    )
                    self.dag_model.add_edge(edge)
                    logger.debug(f"Added edge: {upstream_id} -> {agent_id}")
            
            # Add edges for downstream dependencies (agents that consume data from this agent)
            for downstream_id in downstream_agents:
                if downstream_id in self.dag_model.nodes:
                    edge = EdgeData(
                        source_id=agent_id,
                        target_id=downstream_id,
                        edge_type="data_flow"
                    )
                    self.dag_model.add_edge(edge)
                    logger.debug(f"Added edge: {agent_id} -> {downstream_id}")
                    
        except Exception as e:
            logger.error(f"Error discovering relationships for {agent_id}: {str(e)}")
    
    async def simulate_message(self, source_id: str, target_id: str, message: Any, level: str = "INFO") -> None:
        """
        Simulate a message passing between agents.
        
        This method adds a log entry to the edge between the source and target agents,
        which can be used to visualize data flow.
        
        Args:
            source_id: The ID of the source agent.
            target_id: The ID of the target agent.
            message: The message content.
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        # Format the message for display
        try:
            if isinstance(message, dict):
                message_str = str(message)
            elif hasattr(message, "__str__"):
                message_str = str(message)
            else:
                message_str = f"Message: {type(message)}"
                
            # Add the log entry to the edge
            self.dag_model.add_log_to_edge(source_id, target_id, message_str, level=level)
            logger.debug(f"Added log to edge: {source_id} -> {target_id}")
            
        except Exception as e:
            logger.error(f"Error simulating message from {source_id} to {target_id}: {str(e)}")
            
    async def monitor_redis_for_messages(self, redis_client: Any, channel_pattern: str) -> None:
        """
        Monitor Redis pubsub for messages between agents.
        
        This method sets up a subscription to Redis channels matching the pattern,
        and adds log entries to the appropriate edges when messages are detected.
        
        Args:
            redis_client: The Redis client.
            channel_pattern: The pattern to subscribe to (e.g., "agent:*:message").
        """
        try:
            # Set up subscription
            channels = await redis_client.psubscribe(channel_pattern)
            logger.info(f"Subscribed to Redis channels: {channel_pattern}")
            
            async for channel, message in channels.iter():
                try:
                    # Parse channel name to get source and target
                    # This is an example pattern, adjust based on actual naming convention
                    # For example: "agent:source_id:target_id:message"
                    parts = channel.decode().split(":")
                    if len(parts) >= 4:
                        source_id = parts[1]
                        target_id = parts[2]
                        
                        # Try to parse the message
                        if isinstance(message, bytes):
                            message = message.decode()
                        
                        # Try to parse JSON
                        log_level = "INFO"  # Default level
                        try:
                            if isinstance(message, str) and message.startswith("{"):
                                import json
                                data = json.loads(message)
                                if isinstance(data, dict) and "level" in data:
                                    log_level = data["level"]
                                    
                                    # If the message has a 'message' field, use that
                                    if "message" in data:
                                        message = data["message"]
                        except (json.JSONDecodeError, ImportError):
                            pass
                        
                        # Determine log level based on message content if not found in JSON
                        if log_level == "INFO":
                            # Check for common indicators of different log levels
                            message_lower = message.lower() if isinstance(message, str) else ""
                            if "error" in message_lower or "exception" in message_lower or "failed" in message_lower:
                                log_level = "ERROR"
                            elif "warn" in message_lower or "caution" in message_lower:
                                log_level = "WARNING"
                            elif "debug" in message_lower:
                                log_level = "DEBUG"
                        
                        # Add log to the edge
                        self.dag_model.add_log_to_edge(source_id, target_id, message, level=log_level)
                        logger.debug(f"Added Redis message to edge: {source_id} -> {target_id}")
                except Exception as e:
                    logger.error(f"Error processing Redis message: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error monitoring Redis for messages: {str(e)}")
        
        finally:
            # Close the subscription if possible
            try:
                await channels.unsubscribe()
                logger.info("Unsubscribed from Redis channels")
            except Exception:
                pass 