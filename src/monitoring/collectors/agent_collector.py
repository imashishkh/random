"""
Agent metrics collector for Prometheus.

This module collects metrics related to the agent swarm orchestrator,
including active agents, agent operations, initialization time, and
failure rates.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from prometheus_client import Counter, Gauge, Histogram

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)


class AgentCollector(BaseCollector):
    """
    Collector for agent-related metrics.
    
    Collects the following metrics:
    - Active agents count by type
    - Agent operations count by type
    - Agent initialization time
    - Failed agent operations by error type
    """
    
    def __init__(
        self,
        agent_service=None,
        registry=None,
        collection_interval: int = 15,
        cache_ttl: int = 30,
    ):
        """
        Initialize the agent metrics collector.
        
        Args:
            agent_service: The agent orchestration service to monitor
            registry: Prometheus registry to use
            collection_interval: How often to collect metrics, in seconds
            cache_ttl: How long to cache expensive operations, in seconds
        """
        self.agent_service = agent_service
        self._last_operation_counts = {}
        
        super().__init__(
            registry=registry,
            collection_interval=collection_interval,
            cache_ttl=cache_ttl,
            name="AgentCollector"
        )
    
    def _initialize_metrics(self) -> None:
        """Initialize all agent-related metrics."""
        # Gauge for active agents count by type
        self._metrics['active_agents'] = Gauge(
            'forex_agent_active_total',
            'Number of active agents by type',
            ['agent_type'],
            registry=self.registry
        )
        
        # Counter for agent operations by type
        self._metrics['agent_operations'] = Counter(
            'forex_agent_operations_total',
            'Number of agent operations by operation type',
            ['agent_type', 'operation_type'],
            registry=self.registry
        )
        
        # Histogram for agent initialization time
        self._metrics['init_time'] = Histogram(
            'forex_agent_initialization_seconds',
            'Time taken to initialize an agent',
            ['agent_type', 'initialization_mode'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry
        )
        
        # Counter for failed agent operations
        self._metrics['failures'] = Counter(
            'forex_agent_failures_total',
            'Number of failed agent operations by type and error',
            ['agent_type', 'operation_type', 'error_type'],
            registry=self.registry
        )
        
        # Gauge for agent memory usage
        self._metrics['memory_usage'] = Gauge(
            'forex_agent_memory_bytes',
            'Memory usage by agent in bytes',
            ['agent_type', 'agent_id'],
            registry=self.registry
        )
        
        # Gauge for agent message queue depth
        self._metrics['message_queue'] = Gauge(
            'forex_agent_message_queue_size',
            'Number of messages in agent queue',
            ['agent_type', 'agent_id', 'queue_name'],
            registry=self.registry
        )
    
    def _collect_metrics(self) -> None:
        """Collect current agent metrics."""
        if not self.agent_service:
            logger.warning("Agent service not available, skipping collection")
            return
        
        try:
            # Get active agents
            active_agents = self._cached_operation(
                'active_agents',
                self._get_active_agents
            )
            
            # Update active agent gauge
            self._update_active_agents(active_agents)
            
            # Get agent operations
            operations = self._cached_operation(
                'agent_operations',
                self._get_agent_operations
            )
            
            # Update operation counters
            self._update_operation_counters(operations)
            
            # Get agent memory usage
            memory_usage = self._cached_operation(
                'agent_memory',
                self._get_agent_memory_usage
            )
            
            # Update memory gauges
            self._update_memory_gauges(memory_usage)
            
            # Get agent message queues
            queues = self._cached_operation(
                'agent_queues',
                self._get_agent_message_queues
            )
            
            # Update queue gauges
            self._update_queue_gauges(queues)
            
        except Exception as e:
            logger.error(f"Error collecting agent metrics: {e}")
    
    def _get_active_agents(self) -> Dict[str, int]:
        """
        Get the current count of active agents by type.
        
        Returns:
            Dictionary mapping agent types to counts
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the agent orchestration service.
            # For now, we'll return dummy data.
            return {
                'technical_analysis': 5,
                'fundamental_analysis': 3,
                'risk_management': 2,
                'execution': 4,
                'coordination': 1,
            }
        except Exception as e:
            logger.error(f"Error getting active agents: {e}")
            return {}
    
    def _update_active_agents(self, active_agents: Dict[str, int]) -> None:
        """
        Update the active agents gauge with current counts.
        
        Args:
            active_agents: Dictionary mapping agent types to counts
        """
        for agent_type, count in active_agents.items():
            self._metrics['active_agents'].labels(agent_type=agent_type).set(count)
    
    def _get_agent_operations(self) -> Dict[str, Dict[str, int]]:
        """
        Get the current agent operation counts.
        
        Returns:
            Nested dictionary mapping agent types to operation types to counts
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the agent orchestration service.
            return {
                'technical_analysis': {
                    'create': 10,
                    'analyze': 150,
                    'update': 45,
                    'shutdown': 5
                },
                'fundamental_analysis': {
                    'create': 6,
                    'analyze': 80,
                    'update': 20,
                    'shutdown': 3
                },
                'risk_management': {
                    'create': 4,
                    'evaluate': 200,
                    'update': 30,
                    'shutdown': 2
                },
                'execution': {
                    'create': 8,
                    'order': 100,
                    'cancel': 20,
                    'update': 40,
                    'shutdown': 4
                },
                'coordination': {
                    'create': 2,
                    'coordinate': 300,
                    'update': 10,
                    'shutdown': 1
                }
            }
        except Exception as e:
            logger.error(f"Error getting agent operations: {e}")
            return {}
    
    def _update_operation_counters(self, operations: Dict[str, Dict[str, int]]) -> None:
        """
        Update the operation counters with current counts.
        
        This uses differential counting - only increment the counter by the
        difference since the last collection.
        
        Args:
            operations: Nested dictionary mapping agent types to operation types to counts
        """
        for agent_type, type_ops in operations.items():
            for op_type, count in type_ops.items():
                # Get the previous count for this operation
                last_count = self._last_operation_counts.get(
                    (agent_type, op_type), 0
                )
                
                # Calculate the increment
                increment = max(0, count - last_count)
                
                if increment > 0:
                    # Increment the counter
                    self._metrics['agent_operations'].labels(
                        agent_type=agent_type,
                        operation_type=op_type
                    ).inc(increment)
                
                # Update the last count
                self._last_operation_counts[(agent_type, op_type)] = count
    
    def _get_agent_memory_usage(self) -> Dict[str, Dict[str, int]]:
        """
        Get the current memory usage for each agent.
        
        Returns:
            Nested dictionary mapping agent types to agent IDs to memory usage in bytes
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the agent service for memory usage.
            return {
                'technical_analysis': {
                    'agent-ta-1': 15000000,
                    'agent-ta-2': 12000000,
                    'agent-ta-3': 14000000,
                    'agent-ta-4': 13000000,
                    'agent-ta-5': 16000000
                },
                'fundamental_analysis': {
                    'agent-fa-1': 25000000,
                    'agent-fa-2': 24000000,
                    'agent-fa-3': 26000000
                },
                'risk_management': {
                    'agent-rm-1': 18000000,
                    'agent-rm-2': 17000000
                },
                'execution': {
                    'agent-ex-1': 10000000,
                    'agent-ex-2': 11000000,
                    'agent-ex-3': 9000000,
                    'agent-ex-4': 10500000
                },
                'coordination': {
                    'agent-co-1': 30000000
                }
            }
        except Exception as e:
            logger.error(f"Error getting agent memory usage: {e}")
            return {}
    
    def _update_memory_gauges(self, memory_usage: Dict[str, Dict[str, int]]) -> None:
        """
        Update the memory usage gauges with current values.
        
        Args:
            memory_usage: Nested dictionary mapping agent types to agent IDs to memory usage
        """
        for agent_type, agents in memory_usage.items():
            for agent_id, memory in agents.items():
                self._metrics['memory_usage'].labels(
                    agent_type=agent_type,
                    agent_id=agent_id
                ).set(memory)
    
    def _get_agent_message_queues(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """
        Get the current message queue depths for each agent.
        
        Returns:
            Dictionary mapping agent types to agent IDs to queue names to depths
        """
        try:
            # This is a placeholder. In a real implementation,
            # this would query the agent service for queue depths.
            return {
                'technical_analysis': {
                    'agent-ta-1': {'input': 5, 'output': 2},
                    'agent-ta-2': {'input': 3, 'output': 1},
                    'agent-ta-3': {'input': 7, 'output': 3},
                    'agent-ta-4': {'input': 2, 'output': 0},
                    'agent-ta-5': {'input': 4, 'output': 2}
                },
                'fundamental_analysis': {
                    'agent-fa-1': {'input': 8, 'output': 4},
                    'agent-fa-2': {'input': 6, 'output': 3},
                    'agent-fa-3': {'input': 10, 'output': 5}
                },
                'risk_management': {
                    'agent-rm-1': {'input': 15, 'output': 6},
                    'agent-rm-2': {'input': 12, 'output': 5}
                },
                'execution': {
                    'agent-ex-1': {'input': 20, 'output': 8},
                    'agent-ex-2': {'input': 18, 'output': 7},
                    'agent-ex-3': {'input': 15, 'output': 6},
                    'agent-ex-4': {'input': 22, 'output': 9}
                },
                'coordination': {
                    'agent-co-1': {'input': 30, 'output': 15}
                }
            }
        except Exception as e:
            logger.error(f"Error getting agent message queues: {e}")
            return {}
    
    def _update_queue_gauges(self, queues: Dict[str, Dict[str, Dict[str, int]]]) -> None:
        """
        Update the message queue gauges with current depths.
        
        Args:
            queues: Dictionary mapping agent types to agent IDs to queue names to depths
        """
        for agent_type, agents in queues.items():
            for agent_id, agent_queues in agents.items():
                for queue_name, depth in agent_queues.items():
                    self._metrics['message_queue'].labels(
                        agent_type=agent_type,
                        agent_id=agent_id,
                        queue_name=queue_name
                    ).set(depth)
    
    # Additional methods for recording agent initialization times and errors
    
    def record_initialization_time(
        self,
        agent_type: str,
        initialization_mode: str,
        seconds: float
    ) -> None:
        """
        Record the time taken to initialize an agent.
        
        Args:
            agent_type: Type of the agent
            initialization_mode: Mode of initialization (e.g., 'cold_start', 'warm_start')
            seconds: Time taken in seconds
        """
        self._metrics['init_time'].labels(
            agent_type=agent_type,
            initialization_mode=initialization_mode
        ).observe(seconds)
    
    def record_operation_failure(
        self,
        agent_type: str,
        operation_type: str,
        error_type: str
    ) -> None:
        """
        Record a failed agent operation.
        
        Args:
            agent_type: Type of the agent
            operation_type: Type of the operation
            error_type: Type of the error
        """
        self._metrics['failures'].labels(
            agent_type=agent_type,
            operation_type=operation_type,
            error_type=error_type
        ).inc() 