"""
Base Orchestrator for Market Analysis

This module provides the base orchestrator class for managing market analysis agents
and coordinating the signal validation and filtering pipeline.
"""

import uuid
import time
import logging
from typing import Dict, List, Any, Optional, Union, Tuple, Set, Callable
from datetime import datetime
import json

from ...utils.logging.logger import get_logger
from .base_agent import BaseAgent

logger = get_logger()


class BaseOrchestrator:
    """
    Base class for orchestrating market analysis agents and signal processing.
    
    This class provides the foundation for managing agent lifecycle, signal collection,
    validation, filtering, and publishing across multiple trading pairs.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the base orchestrator.
        
        Args:
            config: Configuration dictionary for the orchestrator
        """
        self.config = config or {}
        self.orchestrator_id = str(uuid.uuid4())
        
        # Initialize agent registry
        self.agents: Dict[str, Dict[str, Any]] = {}
        
        # Initialize performance tracking
        self.performance_metrics: Dict[str, Any] = {
            'signal_counts': {
                'total': 0,
                'valid': 0,
                'invalid': 0,
                'filtered': 0,
                'published': 0
            },
            'latency': {
                'validation': [],
                'filtering': [],
                'total': []
            },
            'accuracy': {
                'true_positives': 0,
                'false_positives': 0,
                'true_negatives': 0,
                'false_negatives': 0
            }
        }
        
        # Initialize trading pairs registry
        self.trading_pairs: Set[str] = set()
        
        # Initialize event listeners
        self.event_listeners: Dict[str, List[Callable]] = {
            'signal_collected': [],
            'signal_validated': [],
            'signal_filtered': [],
            'signal_published': [],
            'error': []
        }
        
        # Configure logging based on config
        self._configure_logging()
        
        logger.info(f"BaseOrchestrator initialized with ID: {self.orchestrator_id}")
    
    def _configure_logging(self):
        """Configure logging based on orchestrator config."""
        log_level = self.config.get('log_level', 'INFO')
        log_levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        logger.setLevel(log_levels.get(log_level, logging.INFO))
    
    def register_agent(self, agent: BaseAgent, agent_type: str, config: Optional[Dict[str, Any]] = None) -> str:
        """
        Register an agent with the orchestrator.
        
        Args:
            agent: The agent instance to register
            agent_type: Type of agent (e.g., 'technical', 'fundamental', 'anomaly')
            config: Agent-specific configuration
            
        Returns:
            Agent ID for future reference
        """
        # Generate agent ID if not present
        agent_id = getattr(agent, 'id', str(uuid.uuid4()))
        
        # Register agent with metadata
        self.agents[agent_id] = {
            'agent': agent,
            'type': agent_type,
            'config': config or {},
            'status': 'registered',
            'registered_at': datetime.utcnow().isoformat(),
            'last_active': None,
            'performance': {
                'signals_generated': 0,
                'signals_validated': 0,
                'accuracy': 0.0,
                'latency': 0.0
            }
        }
        
        logger.info(f"Registered {agent_type} agent with ID: {agent_id}")
        return agent_id
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the orchestrator.
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if successful, False otherwise
        """
        if agent_id in self.agents:
            # Perform cleanup if needed
            agent_data = self.agents.pop(agent_id)
            logger.info(f"Unregistered agent with ID: {agent_id}")
            return True
        
        logger.warning(f"Cannot unregister agent with ID: {agent_id} - not found")
        return False
    
    def register_trading_pair(self, trading_pair: str) -> None:
        """
        Register a trading pair for analysis.
        
        Args:
            trading_pair: Trading pair to register (e.g., 'BTC/USDT')
        """
        self.trading_pairs.add(trading_pair)
        logger.info(f"Registered trading pair: {trading_pair}")
    
    def unregister_trading_pair(self, trading_pair: str) -> bool:
        """
        Unregister a trading pair from analysis.
        
        Args:
            trading_pair: Trading pair to unregister
            
        Returns:
            True if successful, False otherwise
        """
        if trading_pair in self.trading_pairs:
            self.trading_pairs.remove(trading_pair)
            logger.info(f"Unregistered trading pair: {trading_pair}")
            return True
        
        logger.warning(f"Cannot unregister trading pair: {trading_pair} - not found")
        return False
    
    def add_event_listener(self, event_type: str, callback: Callable) -> None:
        """
        Add an event listener for orchestrator events.
        
        Args:
            event_type: Type of event to listen for
            callback: Callback function to invoke when the event occurs
        """
        if event_type in self.event_listeners:
            self.event_listeners[event_type].append(callback)
            logger.debug(f"Added event listener for {event_type}")
        else:
            valid_events = list(self.event_listeners.keys())
            logger.warning(f"Unknown event type: {event_type}. Valid events: {valid_events}")
    
    def emit_event(self, event_type: str, data: Any) -> None:
        """
        Emit an event to registered listeners.
        
        Args:
            event_type: Type of event to emit
            data: Event data to pass to listeners
        """
        if event_type in self.event_listeners:
            for callback in self.event_listeners[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in event listener for {event_type}: {str(e)}")
        else:
            logger.warning(f"Cannot emit event of unknown type: {event_type}")
    
    def get_agent_performance(self, agent_id: str) -> Dict[str, Any]:
        """
        Get performance metrics for a specific agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Dictionary of performance metrics for the agent
        """
        if agent_id in self.agents:
            return self.agents[agent_id]['performance']
        
        logger.warning(f"Cannot get performance for unknown agent: {agent_id}")
        return {}
    
    def get_overall_performance(self) -> Dict[str, Any]:
        """
        Get overall performance metrics for the orchestrator.
        
        Returns:
            Dictionary of overall performance metrics
        """
        return self.performance_metrics
    
    def update_performance_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Update performance metrics with new data.
        
        Args:
            metrics: Dictionary of metrics to update
        """
        # Update signal counts
        if 'signal_counts' in metrics:
            for key, value in metrics['signal_counts'].items():
                if key in self.performance_metrics['signal_counts']:
                    self.performance_metrics['signal_counts'][key] += value
        
        # Update latency metrics
        if 'latency' in metrics:
            for key, value in metrics['latency'].items():
                if key in self.performance_metrics['latency'] and isinstance(value, (int, float)):
                    self.performance_metrics['latency'][key].append(value)
                    # Keep only the last 1000 measurements to avoid unbounded growth
                    if len(self.performance_metrics['latency'][key]) > 1000:
                        self.performance_metrics['latency'][key] = self.performance_metrics['latency'][key][-1000:]
        
        # Update accuracy metrics
        if 'accuracy' in metrics:
            for key, value in metrics['accuracy'].items():
                if key in self.performance_metrics['accuracy']:
                    self.performance_metrics['accuracy'][key] += value
    
    def log_performance_snapshot(self) -> None:
        """Log a snapshot of current performance metrics."""
        # Calculate derived metrics
        signal_counts = self.performance_metrics['signal_counts']
        accuracy = self.performance_metrics['accuracy']
        
        # Calculate average latencies
        avg_latencies = {}
        for key, values in self.performance_metrics['latency'].items():
            if values:
                avg_latencies[key] = sum(values) / len(values)
            else:
                avg_latencies[key] = 0
        
        # Calculate accuracy metrics if we have enough data
        if (accuracy['true_positives'] + accuracy['false_positives']) > 0:
            precision = accuracy['true_positives'] / (accuracy['true_positives'] + accuracy['false_positives'])
        else:
            precision = 0
            
        if (accuracy['true_positives'] + accuracy['false_negatives']) > 0:
            recall = accuracy['true_positives'] / (accuracy['true_positives'] + accuracy['false_negatives'])
        else:
            recall = 0
            
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)
        else:
            f1_score = 0
        
        # Log the snapshot
        logger.info(f"Performance snapshot:")
        logger.info(f"  Signal counts: total={signal_counts['total']}, valid={signal_counts['valid']}, published={signal_counts['published']}")
        logger.info(f"  Avg latency (ms): validation={avg_latencies['validation']:.2f}, filtering={avg_latencies['filtering']:.2f}, total={avg_latencies['total']:.2f}")
        logger.info(f"  Accuracy: precision={precision:.2f}, recall={recall:.2f}, F1={f1_score:.2f}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert orchestrator state to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the orchestrator
        """
        return {
            'orchestrator_id': self.orchestrator_id,
            'agents': {
                agent_id: {
                    'type': data['type'],
                    'status': data['status'],
                    'registered_at': data['registered_at'],
                    'last_active': data['last_active'],
                    'performance': data['performance']
                } for agent_id, data in self.agents.items()
            },
            'trading_pairs': list(self.trading_pairs),
            'performance_metrics': self.performance_metrics
        }
    
    def to_json(self) -> str:
        """
        Convert orchestrator state to a JSON string.
        
        Returns:
            JSON string representation of the orchestrator
        """
        return json.dumps(self.to_dict(), indent=2) 