"""
Core data model for agent DAG visualization.

This module defines the data structures and operations for representing
agents as nodes and their relationships as edges in a directed acyclic graph.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set, Callable, Awaitable, TypeVar, Generic

import networkx as nx

from .dag.metrics import PerformanceMetricsCollector

# Set up logging
logger = logging.getLogger(__name__)

# Import agent status if available, or define our own
try:
    from src.agents.orchestrator.engine import AgentStatus
except ImportError:
    class AgentStatus(str, Enum):
        """Status of an agent."""
        PENDING = "pending"
        INITIALIZING = "initializing"
        RUNNING = "running"
        PAUSED = "paused"
        STOPPED = "stopped"
        FAILED = "failed"

# Type variables for the observer pattern
T = TypeVar('T')
EventData = TypeVar('EventData')


@dataclass(frozen=True)
class NodeData:
    """
    Immutable data for a node in the graph.
    
    Using a frozen dataclass ensures that the data cannot be modified
    after creation, which helps prevent race conditions in async operations.
    """
    id: str
    name: str
    node_type: str
    status: AgentStatus
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling non-serializable fields."""
        data = asdict(self)
        # Convert enum to string if needed
        if isinstance(data['status'], Enum):
            data['status'] = data['status'].value
        # Convert datetime objects to ISO format strings
        for key in ['created_at', 'updated_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        return data


@dataclass(frozen=True)
class EdgeData:
    """
    Immutable data for an edge in the graph.
    
    Represents a connection between two nodes, with optional metadata and logs.
    """
    source_id: str
    target_id: str
    edge_type: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling non-serializable fields."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        for key in ['created_at', 'updated_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        return data


@dataclass
class LogEntry:
    """A log entry for an edge."""
    timestamp: float
    message: str
    level: str = "INFO"  # Added level field with default "INFO"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'formatted_time': datetime.fromtimestamp(self.timestamp).isoformat(),
            'level': self.level,
            'message': self.message,
            'metadata': self.metadata
        }
    
    def get_formatted_message(self) -> str:
        """Return a formatted message with Rich markup."""
        level_colors = {
            "INFO": "[cyan]INFO[/]",
            "WARNING": "[yellow]WARNING[/]",
            "ERROR": "[red]ERROR[/]",
            "DEBUG": "[dim cyan]DEBUG[/]"
        }
        formatted_level = level_colors.get(self.level, f"[blue]{self.level}[/]")
        time_str = datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")
        return f"[dim]{time_str}[/] {formatted_level} {self.message}"


class Observable(Generic[EventData]):
    """Generic Observable implementation for the observer pattern."""
    
    def __init__(self):
        """Initialize the observable with empty observer lists."""
        self._observers: Dict[str, List[Callable[[EventData], Any]]] = {}
    
    def add_observer(self, event_type: str, observer: Callable[[EventData], Any]) -> None:
        """
        Add an observer for a specific event type.
        
        Args:
            event_type: The type of event to observe.
            observer: The callable to invoke when the event occurs.
        """
        if event_type not in self._observers:
            self._observers[event_type] = []
        self._observers[event_type].append(observer)
    
    def remove_observer(self, event_type: str, observer: Callable[[EventData], Any]) -> None:
        """
        Remove an observer for a specific event type.
        
        Args:
            event_type: The type of event.
            observer: The observer to remove.
        """
        if event_type in self._observers and observer in self._observers[event_type]:
            self._observers[event_type].remove(observer)
    
    def notify_observers(self, event_type: str, data: EventData) -> None:
        """
        Notify all observers of an event.
        
        Args:
            event_type: The type of event.
            data: The event data.
        """
        if event_type in self._observers:
            for observer in self._observers[event_type]:
                try:
                    observer(data)
                except Exception as e:
                    logger.error(f"Error in observer for {event_type}: {str(e)}")


class DAGModel(Observable[Any]):
    """
    Data model for the agent DAG visualization.
    
    This class provides methods to manage nodes and edges in the graph,
    and notifies observers of changes.
    """
    
    def __init__(self):
        """Initialize the DAG model with a networkx graph."""
        super().__init__()
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, NodeData] = {}
        self.edges: Dict[Tuple[str, str], EdgeData] = {}
        self.edge_logs: Dict[Tuple[str, str], List[LogEntry]] = {}
        self.last_layout_time = 0
        self.layout_cache: Dict[str, Tuple[float, float]] = {}
        
        # Initialize metrics collector for performance monitoring
        self.metrics_collector = PerformanceMetricsCollector()
        
        # For incremental rendering
        self.changed_regions = set()
        
    def add_node(self, node: NodeData) -> None:
        """
        Add a node to the graph.
        
        Args:
            node: The node data to add.
        """
        self.nodes[node.id] = node
        self.graph.add_node(node.id, data=node)
        self.notify_observers("node_added", node)
        # Invalidate layout cache when adding nodes
        self.last_layout_time = 0
    
    def remove_node(self, node_id: str) -> None:
        """
        Remove a node from the graph.
        
        Args:
            node_id: The ID of the node to remove.
        """
        if node_id in self.nodes:
            node = self.nodes.pop(node_id)
            self.graph.remove_node(node_id)
            
            # Clean up any edges connected to this node
            edges_to_remove = []
            for (source, target) in self.edges.keys():
                if source == node_id or target == node_id:
                    edges_to_remove.append((source, target))
            
            for edge_key in edges_to_remove:
                edge = self.edges.pop(edge_key)
                if edge_key in self.edge_logs:
                    del self.edge_logs[edge_key]
                self.notify_observers("edge_removed", edge)
            
            self.notify_observers("node_removed", node)
            # Invalidate layout cache when removing nodes
            self.last_layout_time = 0
            
    def update_performance_metrics(self, force: bool = False) -> None:
        """
        Update performance metrics for all nodes from the health monitor.
        
        Args:
            force: Whether to force refresh regardless of cache interval
        """
        # Refresh metrics in the collector
        metrics_updated = self.metrics_collector.refresh_metrics(force=force)
        
        if not metrics_updated:
            return
            
        # Update each node with its metrics
        for node_id, node in self.nodes.items():
            metrics = self.metrics_collector.get_agent_metrics(node_id)
            health_score = self.metrics_collector.get_health_score(node_id)
            
            if metrics or health_score > 0:
                # Create updated node with new metrics
                updated_values = node.to_dict()
                
                # Update performance metrics
                if metrics:
                    updated_values['performance_metrics'] = metrics
                
                # Add health score to metrics
                if not 'performance_metrics' in updated_values:
                    updated_values['performance_metrics'] = {}
                updated_values['performance_metrics']['health_score'] = health_score
                
                # Get a simplified health status based on the score
                health_status = "normal"
                if health_score < 0.3:
                    health_status = "critical"
                elif health_score < 0.6:
                    health_status = "warning"
                updated_values['performance_metrics']['health_status'] = health_status
                
                updated_values['updated_at'] = datetime.now()
                
                # Create new node data (frozen dataclass requires recreation)
                new_node = NodeData(**updated_values)
                
                # Update our records
                self.nodes[node_id] = new_node
                self.graph.nodes[node_id]['data'] = new_node
                
                # Notify observers
                self.notify_observers("node_updated", (node, new_node))
                
        # Record the update time
        render_time = time.time() - self.metrics_collector.last_refresh_time
        self.metrics_collector.update_adaptive_interval(render_time, len(self.nodes))
                
    def update_node(self, node_id: str, **kwargs) -> None:
        """
        Update a node's attributes.
        
        Args:
            node_id: The ID of the node to update.
            **kwargs: Attributes to update.
        """
        if node_id in self.nodes:
            old_node = self.nodes[node_id]
            # Create a fresh NodeData with updated values
            updated_values = {**old_node.to_dict(), **kwargs, 'updated_at': datetime.now()}
            
            # Handle special cases like enum conversion
            if 'status' in kwargs and isinstance(kwargs['status'], str):
                try:
                    updated_values['status'] = AgentStatus(kwargs['status'])
                except ValueError:
                    logger.warning(f"Invalid status value: {kwargs['status']}")
            
            # Create new node data (frozen dataclass requires recreation)
            new_node = NodeData(**updated_values)
            
            # Update our records
            self.nodes[node_id] = new_node
            self.graph.nodes[node_id]['data'] = new_node
            
            self.notify_observers("node_updated", (old_node, new_node))
    
    def mark_region_changed(self, row_start: int, row_end: int, col_start: int, col_end: int) -> None:
        """
        Mark a region as changed for incremental rendering.
        
        Args:
            row_start: Starting row of the region
            row_end: Ending row of the region
            col_start: Starting column of the region
            col_end: Ending column of the region
        """
        # Ensure the region has valid dimensions
        if row_end < row_start or col_end < col_start:
            logger.warning(f"Invalid region dimensions: ({row_start},{col_start}) to ({row_end},{col_end})")
            return
            
        # Add the region to the set of changed regions
        self.changed_regions.add((row_start, row_end, col_start, col_end))
        logger.debug(f"Marked region as changed: ({row_start},{col_start}) to ({row_end},{col_end})")
    
    def get_changed_regions(self) -> Set[Tuple[int, int, int, int]]:
        """
        Get the set of changed regions.
        
        Returns:
            Set of (row_start, row_end, col_start, col_end) tuples
        """
        return self.changed_regions
    
    def clear_changed_regions(self) -> None:
        """Clear the set of changed regions."""
        self.changed_regions.clear()
    
    def add_edge(self, edge: EdgeData) -> None:
        """
        Add an edge between nodes.
        
        Args:
            edge: The edge data to add.
        """
        # Ensure the source and target nodes exist
        if edge.source_id not in self.nodes:
            logger.warning(f"Source node {edge.source_id} does not exist")
            return
        
        if edge.target_id not in self.nodes:
            logger.warning(f"Target node {edge.target_id} does not exist")
            return
        
        edge_key = (edge.source_id, edge.target_id)
        self.edges[edge_key] = edge
        self.graph.add_edge(edge.source_id, edge.target_id, data=edge)
        
        # Initialize empty log list for the edge
        if edge_key not in self.edge_logs:
            self.edge_logs[edge_key] = []
        
        self.notify_observers("edge_added", edge)
    
    def remove_edge(self, source_id: str, target_id: str) -> None:
        """
        Remove an edge from the graph.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
        """
        edge_key = (source_id, target_id)
        if edge_key in self.edges:
            edge = self.edges.pop(edge_key)
            if edge_key in self.edge_logs:
                del self.edge_logs[edge_key]
            self.graph.remove_edge(source_id, target_id)
            self.notify_observers("edge_removed", edge)
    
    def add_log_to_edge(self, source_id: str, target_id: str, message: str, 
                       level: str = "INFO", 
                       metadata: Optional[Dict[str, Any]] = None,
                       max_logs: int = 100) -> None:
        """
        Add a log entry to an edge.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
            message: The log message.
            level: Log level (INFO, WARNING, ERROR, DEBUG)
            metadata: Optional metadata.
            max_logs: Maximum number of logs to keep per edge.
        """
        if metadata is None:
            metadata = {}
        
        edge_key = (source_id, target_id)
        
        # Check if the edge exists
        if edge_key not in self.edges:
            logger.warning(f"Cannot add log to non-existent edge: {source_id} -> {target_id}")
            return
        
        # Create log entry
        log_entry = LogEntry(
            timestamp=time.time(),
            message=message,
            level=level,
            metadata=metadata
        )
        
        # Initialize log list if needed
        if edge_key not in self.edge_logs:
            self.edge_logs[edge_key] = []
        
        # Add the log entry
        self.edge_logs[edge_key].append(log_entry)
        
        # Truncate if needed
        if len(self.edge_logs[edge_key]) > max_logs:
            self.edge_logs[edge_key] = self.edge_logs[edge_key][-max_logs:]
        
        # Notify observers
        self.notify_observers("edge_log_added", (edge_key, log_entry))
    
    def get_logs_for_edge(self, source_id: str, target_id: str, limit: int = 10, 
                         filter_level: Optional[str] = None,
                         filter_time: Optional[float] = None) -> List[LogEntry]:
        """
        Get logs for an edge, with optional filtering.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
            limit: The maximum number of logs to return.
            filter_level: If provided, only return logs of this level.
            filter_time: If provided, only return logs newer than this timestamp.
        
        Returns:
            The logs for the edge.
        """
        edge_key = (source_id, target_id)
        
        if edge_key not in self.edge_logs:
            return []
        
        logs = self.edge_logs[edge_key]
        
        # Apply filters if specified
        if filter_level is not None:
            logs = [log for log in logs if log.level == filter_level]
        
        if filter_time is not None:
            current_time = time.time()
            logs = [log for log in logs if current_time - log.timestamp <= filter_time]
        
        # Return the most recent logs up to the limit
        return logs[-limit:]
    
    def compute_layout(self, force: bool = False) -> Dict[str, Tuple[float, float]]:
        """
        Compute the layout of the graph for visualization.
        
        Args:
            force: Whether to force recomputation of the layout.
            
        Returns:
            Dictionary mapping node IDs to (x, y) positions.
        """
        current_time = time.time()
        
        # Only recompute if needed (cache expired or forced)
        if force or current_time - self.last_layout_time > 5 or not self.layout_cache:
            if not self.nodes:
                return {}
            
            # Use networkx's spring layout for force-directed layout
            positions = nx.spring_layout(self.graph, k=0.3, iterations=50)
            
            # Normalize positions to [0, 1] range
            min_x = min(pos[0] for pos in positions.values())
            max_x = max(pos[0] for pos in positions.values())
            min_y = min(pos[1] for pos in positions.values())
            max_y = max(pos[1] for pos in positions.values())
            
            x_range = max_x - min_x
            y_range = max_y - min_y
            
            if x_range > 0 and y_range > 0:
                normalized_positions = {}
                for node_id, (x, y) in positions.items():
                    normalized_x = (x - min_x) / x_range
                    normalized_y = (y - min_y) / y_range
                    normalized_positions[node_id] = (normalized_x, normalized_y)
                
                self.layout_cache = normalized_positions
            else:
                # If all nodes are at the same position, spread them in a grid
                self.layout_cache = self._fallback_layout()
            
            self.last_layout_time = current_time
        
        return self.layout_cache
    
    def _fallback_layout(self) -> Dict[str, Tuple[float, float]]:
        """
        Generate a grid layout as a fallback when spring layout fails.
        
        Returns:
            Dictionary mapping node IDs to (x, y) positions.
        """
        positions = {}
        n = len(self.nodes)
        if n == 0:
            return positions
        
        # Determine grid dimensions
        cols = int(n**0.5) + 1
        row, col = 0, 0
        
        for i, node_id in enumerate(self.nodes.keys()):
            # Calculate position in [0, 1] range
            x = (col + 0.5) / cols
            y = (row + 0.5) / cols
            positions[node_id] = (x, y)
            
            # Move to next cell
            col += 1
            if col >= cols:
                col = 0
                row += 1
        
        return positions
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the DAG model to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the DAG model.
        """
        nodes_dict = {node_id: node.to_dict() for node_id, node in self.nodes.items()}
        edges_dict = {}
        for (source, target), edge in self.edges.items():
            edge_key = f"{source}:{target}"
            edges_dict[edge_key] = edge.to_dict()
        
        logs_dict = {}
        for (source, target), logs in self.edge_logs.items():
            edge_key = f"{source}:{target}"
            logs_dict[edge_key] = [log.to_dict() for log in logs]
        
        return {
            "nodes": nodes_dict,
            "edges": edges_dict,
            "logs": logs_dict
        } 