"""
Textual application for the agent DAG visualization.

This module defines the main application class and UI components for
visualizing the agent DAG.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple, Set, Callable, Awaitable

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import Reactive, reactive
from textual.widgets import Header, Footer, Static, Label, Button, Log
from textual.widget import Widget
from textual.message import Message

from rich.panel import Panel
from rich.text import Text
from rich.console import Console, ConsoleOptions, RenderResult
from rich.style import Style
from rich.table import Table
from rich.box import Box, ROUNDED

from .dag.model import DAGModel, NodeData, EdgeData, AgentStatus, LogEntry
import networkx as nx

# Set up logging
logger = logging.getLogger(__name__)


class DAGWidget(Static):
    """
    Widget for rendering the DAG visualization.
    
    This widget renders nodes and edges in ASCII art, with
    color coding to indicate node status and recent activity.
    """
    
    # Reactive attributes for automatic re-rendering
    needs_refresh = reactive(True)
    selected_node = reactive(None)
    selected_edge = reactive(None)
    show_details = reactive(True)
    show_logs = reactive(True)
    incremental_render = reactive(True)  # New attribute for incremental rendering
    
    # Status colors for nodes
    STATUS_COLORS = {
        AgentStatus.PENDING: "yellow",
        AgentStatus.INITIALIZING: "cyan",
        AgentStatus.RUNNING: "green",
        AgentStatus.PAUSED: "blue",
        AgentStatus.STOPPED: "grey50",
        AgentStatus.FAILED: "red"
    }
    
    # Health status colors
    HEALTH_COLORS = {
        "critical": "red",
        "warning": "yellow",
        "normal": "green"
    }
    
    def __init__(self, dag_model: DAGModel, *args, **kwargs):
        """
        Initialize the DAG widget.
        
        Args:
            dag_model: The DAG model to visualize.
            *args: Additional positional arguments for the parent class.
            **kwargs: Additional keyword arguments for the parent class.
        """
        super().__init__(*args, **kwargs)
        self.dag_model = dag_model
        self.node_layout: Dict[str, Tuple[int, int]] = {}
        self.recent_logs = {}  # Dictionary to track edges with recent logs
        self.recent_log_timeout = 5.0  # Seconds to highlight edges with recent logs
        
        # For incremental rendering
        self.last_grid = None
        self.last_render_time = 0
        self.render_metrics = {"full_renders": 0, "incremental_renders": 0, "avg_time": 0}
        
        # Register for model events
        self._register_observers()
    
    def _register_observers(self) -> None:
        """Register observers for model events."""
        for event_type in ["node_added", "node_removed", "node_updated", 
                          "edge_added", "edge_removed", "edge_log_added"]:
            self.dag_model.add_observer(event_type, self._on_model_change)
        
        # Add specific observer for log events
        self.dag_model.add_observer("edge_log_added", self._on_log_added)
    
    def _on_model_change(self, _: Any) -> None:
        """Handle model change events."""
        self.needs_refresh = True
    
    def _on_log_added(self, data: Tuple[Tuple[str, str], LogEntry]) -> None:
        """
        Handle a new log entry.
        
        Args:
            data: Tuple of (edge_key, log_entry).
        """
        edge_key, _ = data
        
        # Mark the edge as having recent logs
        self.recent_logs[edge_key] = time.time()
        
        # Schedule a refresh
        self.needs_refresh = True
        
        # Schedule a timer to clear the recent log indicator
        def _clear_recent_log():
            if edge_key in self.recent_logs:
                del self.recent_logs[edge_key]
                self.needs_refresh = True
        
        self.set_timer(self.recent_log_timeout, _clear_recent_log)
    
    def on_mount(self) -> None:
        """Set up the widget when mounted."""
        # Set up a periodic refresh timer
        self.set_interval(0.5, self.check_refresh)
        
        # Set up a timer to update performance metrics
        self.set_interval(2.0, self.update_metrics)
    
    def update_metrics(self) -> None:
        """Update performance metrics from the health monitor."""
        # Update metrics in the model
        self.dag_model.update_performance_metrics()
    
    def check_refresh(self) -> None:
        """Check if the widget needs to be refreshed."""
        if self.needs_refresh:
            self.needs_refresh = False
            # Force a refresh by calling refresh()
            self.refresh()
    
    def compute_layout(self) -> Dict[str, Tuple[int, int]]:
        """
        Compute the layout for the visualization with improved node positioning.
        
        Returns:
            Dictionary mapping node IDs to (row, col) positions.
        """
        # Get the normalized layout from the model
        normalized = self.dag_model.compute_layout(force=False)
        
        # Get the dimensions of the terminal
        rows, cols = self.size
        
        # Adjust for borders, padding, and legend space
        # Reserve more space at the top for the legend (3 lines)
        legend_space = 4
        usable_rows = max(rows - legend_space - 4, 10)  # -4 for top/bottom padding and status line
        usable_cols = max(cols - 6, 20)  # -6 for left/right padding
        
        # Determine if the graph is primarily vertical or horizontal
        # This helps adjust the layout for better display
        vertical_graph = False
        if len(normalized) > 0:
            # Check for any long vertical paths
            G = self.dag_model.graph
            longest_path = 0
            for node in G.nodes():
                # Find longest path from this node
                for target in G.nodes():
                    if node != target:
                        try:
                            paths = list(nx.all_simple_paths(G, node, target))
                            if paths:
                                path_length = max(len(path) for path in paths)
                                longest_path = max(longest_path, path_length)
                        except (nx.NetworkXNoPath, nx.NodeNotFound):
                            pass
            
            # If we have a long path, adjust the layout to be more vertical
            vertical_graph = longest_path > 3
        
        # If the graph is very vertical, we adjust the spacing
        if vertical_graph:
            # Stretch vertically
            vertical_stretch = 1.5
            for node_id, (x, y) in normalized.items():
                normalized[node_id] = (x, y * vertical_stretch)
            
            # Renormalize to [0,1] range if needed
            max_y = max(y for _, y in normalized.values())
            if max_y > 1.0:
                for node_id, (x, y) in normalized.items():
                    normalized[node_id] = (x, y / max_y)
        
        # Adjust edge weights for high-degree nodes
        # Nodes with many connections need more space around them
        for node_id in normalized:
            degree = len(list(self.dag_model.graph.neighbors(node_id)))
            if degree > 2:
                # Find neighbors in the layout
                neighbors = list(self.dag_model.graph.neighbors(node_id))
                node_x, node_y = normalized[node_id]
                
                # Push neighbors outward slightly based on degree
                push_factor = min(0.15, 0.05 * degree)
                for neighbor_id in neighbors:
                    if neighbor_id in normalized:
                        neighbor_x, neighbor_y = normalized[neighbor_id]
                        dx = neighbor_x - node_x
                        dy = neighbor_y - node_y
                        # Normalize the direction vector
                        length = max(0.01, (dx**2 + dy**2)**0.5)
                        norm_dx, norm_dy = dx/length, dy/length
                        
                        # Push neighbor outward
                        new_x = neighbor_x + norm_dx * push_factor
                        new_y = neighbor_y + norm_dy * push_factor
                        
                        # Keep within [0,1] bounds
                        new_x = max(0.0, min(1.0, new_x))
                        new_y = max(0.0, min(1.0, new_y))
                        
                        normalized[neighbor_id] = (new_x, new_y)
        
        # Convert normalized coordinates to terminal coordinates
        terminal_layout = {}
        for node_id, (x, y) in normalized.items():
            # Add padding at the top for legend and at the sides
            row = int(y * usable_rows) + legend_space
            col = int(x * usable_cols) + 3  # +3 for left padding
            
            # Ensure minimum distances between nodes
            # Check existing positions and adjust if too close
            min_distance = 6  # Minimum distance between nodes
            
            # Avoid overlaps by checking proximity to other nodes
            for existing_id, (existing_row, existing_col) in terminal_layout.items():
                distance = ((row - existing_row) ** 2 + (col - existing_col) ** 2) ** 0.5
                if distance < min_distance:
                    # Nodes are too close, adjust position
                    dx = col - existing_col
                    dy = row - existing_row
                    
                    # Normalize direction
                    length = max(0.01, (dx**2 + dy**2)**0.5)
                    norm_dx, norm_dy = dx/length, dy/length
                    
                    # Move new node away to maintain minimum distance
                    offset = min_distance - distance
                    row += int(norm_dy * offset)
                    col += int(norm_dx * offset)
                    
                    # Ensure positions stay within bounds
                    row = max(legend_space, min(rows - 2, row))
                    col = max(3, min(cols - 3, col))
            
            terminal_layout[node_id] = (row, col)
        
        return terminal_layout
    
    def select_node_at(self, row: int, col: int) -> None:
        """
        Select the node at the given position.
        
        Args:
            row: The row coordinate.
            col: The column coordinate.
        """
        # Find the closest node to the given position
        closest_node = None
        closest_distance = float('inf')
        
        for node_id, (node_row, node_col) in self.node_layout.items():
            distance = ((node_row - row) ** 2 + (node_col - col) ** 2) ** 0.5
            if distance < closest_distance:
                closest_distance = distance
                closest_node = node_id
        
        # Only select if within a reasonable distance
        if closest_distance <= 3:
            self.selected_node = closest_node
            self.selected_edge = None
            self.needs_refresh = True
    
    def select_edge_between(self, source_id: str, target_id: str) -> None:
        """
        Select the edge between two nodes.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
        """
        edge_key = (source_id, target_id)
        if edge_key in self.dag_model.edges:
            self.selected_edge = edge_key
            self.selected_node = None
            self.needs_refresh = True
    
    def on_key(self, event: Any) -> None:
        """
        Handle key events with enhanced navigation.
        
        Args:
            event: The key event.
        """
        key = event.key
        
        if key == "escape":
            # Clear selection
            self.selected_node = None
            self.selected_edge = None
            self.needs_refresh = True
        elif key == "d":
            # Toggle details
            self.show_details = not self.show_details
            self.needs_refresh = True
        elif key == "l":
            # Toggle logs
            self.show_logs = not self.show_logs
            self.needs_refresh = True
        elif key == "r":
            # Force refresh
            self.dag_model.compute_layout(force=True)
            self.needs_refresh = True
        # New navigation handlers
        elif key == "up" or key == "down" or key == "left" or key == "right":
            self._navigate_nodes(key)
        elif key == "enter":
            # Toggle expanded view of selected node/edge or select edge
            self._toggle_expanded_view()
    
    def on_click(self, event: Any) -> None:
        """
        Handle mouse click events.
        
        Args:
            event: The click event.
        """
        # Try to select a node at the clicked position
        self.select_node_at(event.y, event.x)
    
    def render(self) -> RenderResult:
        """
        Render the DAG visualization with support for incremental rendering.
        
        Returns:
            Rich renderable for the visualization.
        """
        start_time = time.time()
        
        # Compute the layout if needed
        self.node_layout = self.compute_layout()
        
        # Create a table for the DAG visualization
        rows, cols = self.size
        
        # Determine if we can do incremental rendering
        do_incremental = (self.incremental_render and 
                         self.last_grid is not None and 
                         len(self.last_grid) == rows and
                         all(len(row) == cols for row in self.last_grid))
                         
        if do_incremental:
            # Use the last grid as a starting point
            grid = [row.copy() for row in self.last_grid]
            
            # Get changed regions from the model
            changed_regions = self.dag_model.get_changed_regions()
            
            # Clear the cells in changed regions
            for row_start, row_end, col_start, col_end in changed_regions:
                for r in range(max(0, row_start), min(rows, row_end + 1)):
                    for c in range(max(0, col_start), min(cols, col_end + 1)):
                        grid[r][c] = " "
                        
            # Also clear cells around nodes that need to be redrawn
            for node_id, node in self.dag_model.nodes.items():
                if node_id in self.node_layout:
                    row, col = self.node_layout[node_id]
                    # Clear a region around the node (adjust as needed)
                    for r in range(max(0, row - 2), min(rows, row + 3)):
                        for c in range(max(0, col - 4), min(cols, col + 20)):  # Extra space for name
                            grid[r][c] = " "
            
            # Track this as an incremental render
            self.render_metrics["incremental_renders"] += 1
        else:
            # Initialize the grid with empty cells
            grid = [[" " for _ in range(cols)] for _ in range(rows)]
            
            # Track this as a full render
            self.render_metrics["full_renders"] += 1
        
        node_positions = {}
        
        # Draw edges
        for (source_id, target_id), edge in self.dag_model.edges.items():
            if source_id in self.node_layout and target_id in self.node_layout:
                source_pos = self.node_layout[source_id]
                target_pos = self.node_layout[target_id]
                
                # Draw the edge
                self._draw_edge(grid, source_pos, target_pos, 
                               (source_id, target_id) == self.selected_edge,
                               (source_id, target_id) in self.recent_logs)
                
                # Store positions for node rendering
                node_positions[source_id] = source_pos
                node_positions[target_id] = target_pos
        
        # Draw nodes
        for node_id, node in self.dag_model.nodes.items():
            if node_id in self.node_layout:
                self._draw_node(grid, node, self.node_layout[node_id], node_id == self.selected_node)
        
        # Draw status indicator
        status_text = f"Agents: {len(self.dag_model.nodes)} | "
        status_text += f"Connections: {len(self.dag_model.edges)}"
        
        # Add rendering metrics
        render_time = time.time() - start_time
        self.last_render_time = render_time
        
        # Update average render time with exponential moving average
        if self.render_metrics["avg_time"] == 0:
            self.render_metrics["avg_time"] = render_time
        else:
            self.render_metrics["avg_time"] = (
                0.9 * self.render_metrics["avg_time"] + 0.1 * render_time
            )
        
        status_text += f" | Render: {self.render_metrics['avg_time']*1000:.1f}ms"
        
        if len(status_text) < cols:
            for i, char in enumerate(status_text):
                grid[rows - 1][i] = char
        
        # Add legend if there's enough space
        legend_text = []
        
        # Status legend
        status_legend = f"Status: [yellow]■[/] pending [cyan]■[/] initializing [green]■[/] running [blue]■[/] paused [red]■[/] failed"
        legend_text.append(status_legend)
        
        # Health legend (add this)
        health_legend = f"Health: [green]◆[/] good [yellow]◆[/] warning [red]◆[/] critical"
        legend_text.append(health_legend)
        
        # Node type legend
        type_legend = f"Node Types: [white](T)[/] Trader [white](A)[/] Analyzer [white](M)[/] Monitor [white](E)[/] Executor [white](R)[/] Risk Mgr [white](D)[/] Data Coll"
        legend_text.append(type_legend)
        
        # Add edge legend if there's space
        if cols > 80:
            edge_legend = f"Edges: [white]───[/] Data Flow [yellow]···[/] Control [cyan]- - -[/] Notification [white]→[/] Direction"
            legend_text.append(edge_legend)
        
        # Save the current grid for future incremental rendering
        self.last_grid = [row.copy() for row in grid]
        
        # Clear changed regions in the model now that we've rendered them
        self.dag_model.clear_changed_regions()
        
        # Create panel with appropriate title based on selection
        if self.selected_node:
            node = self.dag_model.nodes.get(self.selected_node)
            if node:
                # Try to get health score for the title
                health_info = ""
                if "performance_metrics" in node.metadata and "health_score" in node.metadata["performance_metrics"]:
                    health_score = node.metadata["performance_metrics"]["health_score"]
                    health_info = f" | Health: {health_score:.2f}"
                    
                return Panel(
                    self._grid_to_text(grid),
                    title=f"Agent: {node.name}{health_info}",
                    subtitle="\n".join(legend_text),
                    border_style="green"
                )
        elif self.selected_edge:
            edge = self.dag_model.edges.get(self.selected_edge)
            if edge:
                # Get the source and target node names
                source_name = self.dag_model.nodes.get(edge.source_id, NodeData(id=edge.source_id, name="Unknown", node_type="unknown", status=AgentStatus.PENDING)).name
                target_name = self.dag_model.nodes.get(edge.target_id, NodeData(id=edge.target_id, name="Unknown", node_type="unknown", status=AgentStatus.PENDING)).name
                
                return Panel(
                    self._grid_to_text(grid),
                    title=f"Connection: {source_name} → {target_name} ({edge.edge_type})",
                    subtitle="\n".join(legend_text),
                    border_style="yellow"
                )
        else:
            # Default view
            help_text = "[i]Arrow keys: Navigate  [i]Enter: Select  [i]H: Help  [i]Q: Exit"
            return Panel(
                self._grid_to_text(grid),
                title="Agent DAG Visualization",
                subtitle="\n".join(legend_text),
                border_style="green"
            )
    
    def _grid_to_text(self, grid: List[List[str]]) -> Text:
        """
        Convert a grid of characters to Rich Text.
        
        Args:
            grid: The grid of characters.
            
        Returns:
            Rich Text with the grid content.
        """
        text = Text()
        for row in grid:
            text.append("".join(row) + "\n")
        return text
    
    def _draw_node(self, grid: List[List[str]], node: NodeData, pos: Tuple[int, int], is_selected: bool) -> None:
        """
        Draw a node on the grid with improved visual representation including health status.
        
        Args:
            grid: The grid to draw on.
            node: The node to draw.
            pos: The position (row, col) to draw at.
            is_selected: Whether the node is selected.
        """
        row, col = pos
        rows, cols = len(grid), len(grid[0])
        
        # Skip if out of bounds
        if row < 0 or row >= rows or col < 0 or col >= cols:
            return
        
        # Define node type-specific characters and box styles
        node_chars = {
            "trader": "T",
            "analyzer": "A",
            "monitor": "M",
            "executor": "E",
            "risk_manager": "R",
            "data_collector": "D",
        }
        
        node_char = node_chars.get(node.node_type, "•")
        
        # Box drawing characters
        top_left = "┌"
        top_right = "┐"
        bottom_left = "└"
        bottom_right = "┘"
        horizontal = "─"
        vertical = "│"
        
        # Calculate box dimensions
        box_width = 3  # Fixed width for node box
        
        # Get health status if available
        health_status = "normal"
        health_indicator = " "
        
        if hasattr(node, 'performance_metrics') and node.performance_metrics:
            if 'health_status' in node.performance_metrics:
                health_status = node.performance_metrics['health_status']
                
                # Use a diamond character for health indicator
                health_indicator = "◆"
        
        # Ensure we have space for the box
        if (row <= 0 or row >= rows - 1 or 
            col <= 0 or col + box_width >= cols - 1):
            # Fallback to simple representation if near edges
            if is_selected:
                grid[row][col] = f"[bold white on blue]{node_char}[/]"
            else:
                color = self.STATUS_COLORS.get(node.status, "white")
                grid[row][col] = f"[{color}]{node_char}[/]"
            
            # Draw the node name next to it if space allows
            name = node.name[:15]  # Truncate long names
            if col + box_width + len(name) + 1 < cols:
                for i, char in enumerate(name):
                    grid[row][col + box_width + i] = char
            return
        
        # Select style based on node status and selection
        style_prefix = ""
        if is_selected:
            style_prefix = "[bold white on blue]"
            style_suffix = "[/]"
        else:
            color = self.STATUS_COLORS.get(node.status, "white")
            style_prefix = f"[{color}]"
            style_suffix = "[/]"
        
        # Health indicator style
        health_color = self.HEALTH_COLORS.get(health_status, "white")
        health_prefix = f"[{health_color}]"
        health_suffix = "[/]"
        
        # Draw the box
        # Top edge
        grid[row-1][col-1] = f"{style_prefix}{top_left}{style_suffix}"
        grid[row-1][col] = f"{style_prefix}{horizontal}{style_suffix}"
        grid[row-1][col+1] = f"{style_prefix}{horizontal}{style_suffix}"
        grid[row-1][col+2] = f"{style_prefix}{top_right}{style_suffix}"
        
        # Sides and content
        grid[row][col-1] = f"{style_prefix}{vertical}{style_suffix}"
        grid[row][col] = f"{style_prefix}{node_char}{style_suffix}"
        grid[row][col+1] = health_prefix + health_indicator + health_suffix
        grid[row][col+2] = f"{style_prefix}{vertical}{style_suffix}"
        
        # Bottom edge
        grid[row+1][col-1] = f"{style_prefix}{bottom_left}{style_suffix}"
        grid[row+1][col] = f"{style_prefix}{horizontal}{style_suffix}"
        grid[row+1][col+1] = f"{style_prefix}{horizontal}{style_suffix}"
        grid[row+1][col+2] = f"{style_prefix}{bottom_right}{style_suffix}"
        
        # Draw the node name next to box if space allows
        name = node.name[:15]  # Truncate long names
        if col + box_width + len(name) + 1 < cols:
            for i, char in enumerate(name):
                grid[row][col + box_width + i] = char
            
            # Draw simple metrics indicators if available and space allows
            metrics_str = ""
            if hasattr(node, 'performance_metrics') and node.performance_metrics:
                metrics = node.performance_metrics
                
                if 'health_score' in metrics:
                    # Add health score as a percentage
                    health_score = metrics['health_score']
                    metrics_str += f" H:{health_score*100:.0f}%"
                
                if 'response_time_ms' in metrics and 'average' in metrics['response_time_ms']:
                    # Add response time in ms
                    rt = metrics['response_time_ms']['average']
                    metrics_str += f" RT:{rt:.0f}ms"
                
                if 'error_rate' in metrics and 'average' in metrics['error_rate']:
                    # Add error rate as a percentage
                    err = metrics['error_rate']['average'] * 100
                    metrics_str += f" Err:{err:.1f}%"
            
            # Draw metrics after the name if space allows
            if metrics_str and col + box_width + len(name) + len(metrics_str) + 1 < cols:
                for i, char in enumerate(metrics_str):
                    grid[row][col + box_width + len(name) + i] = char
    
    def _draw_edge(self, grid: List[List[str]], source_pos: Tuple[int, int], target_pos: Tuple[int, int], is_selected: bool, has_recent_logs: bool = False) -> None:
        """
        Draw an edge between two nodes.
        
        Args:
            grid: The drawing grid.
            source_pos: The position of the source node.
            target_pos: The position of the target node.
            is_selected: Whether the edge is selected.
            has_recent_logs: Whether the edge has recent logs.
        """
        rows, cols = len(grid), len(grid[0])
        src_row, src_col = source_pos
        dst_row, dst_col = target_pos
        
        # Skip if either position is out of bounds
        if (src_row < 0 or src_row >= rows or src_col < 0 or src_col >= cols or
            dst_row < 0 or dst_row >= rows or dst_col < 0 or dst_col >= cols):
            return
        
        # Enhanced box drawing characters
        horizontal = "─"
        vertical = "│"
        
        # Better diagonal characters
        ne_diagonal = "/"  # North-east diagonal
        se_diagonal = "\\"  # South-east diagonal
        
        # Better corner characters
        top_left = "┌"
        top_right = "┐"
        bottom_left = "└"
        bottom_right = "┘"
        
        # Enhanced intersections
        cross = "┼"
        t_up = "┴"
        t_down = "┬"
        t_left = "┤"
        t_right = "├"
        
        # Direction indicators
        right_arrow = "→"
        left_arrow = "←"
        up_arrow = "↑"
        down_arrow = "↓"
        
        # Find the edge in the model to get its type
        edge_key = None
        edge_type = "data_flow"  # Default type
        
        # Find the corresponding edge in the model
        # We need to map screen positions back to node IDs
        source_id = None
        target_id = None
        
        # Map positions back to node IDs
        for node_id, pos in self.node_layout.items():
            if pos == source_pos:
                source_id = node_id
            elif pos == target_pos:
                target_id = node_id
        
        # Get edge type if IDs are found
        if source_id and target_id:
            edge_key = (source_id, target_id)
            if edge_key in self.dag_model.edges:
                edge_type = self.dag_model.edges[edge_key].edge_type
        
        # Simple line drawing algorithm with enhanced characters
        dx = dst_col - src_col
        dy = dst_row - src_row
        
        steps = max(abs(dx), abs(dy))
        if steps == 0:
            return
        
        x_inc = dx / steps
        y_inc = dy / steps
        
        # Determine edge style based on type and selection
        if is_selected:
            style_prefix = "[bold blue on white]"
            style_suffix = "[/]"
        else:
            # Customize style based on edge type
            if edge_type == "data_flow":
                style_prefix = "[dim white]"
                style_suffix = "[/]"
            elif edge_type == "control":
                style_prefix = "[yellow]"
                style_suffix = "[/]"
            elif edge_type == "notification":
                style_prefix = "[cyan]"
                style_suffix = "[/]"
            else:
                style_prefix = "[dim white]"
                style_suffix = "[/]"
        
        # Customize line style based on edge type
        if edge_type == "control":
            # Use dotted lines for control relationships
            horizontal = "·"
            vertical = "·"
        elif edge_type == "notification":
            # Use dashed lines for notifications
            horizontal = "╌"
            vertical = "╎"
        
        # Optimize straight lines for better looking paths
        if dx == 0 or dy == 0 or abs(dx) == abs(dy):
            # Draw straight lines with enhanced chars
            x, y = src_col, src_row
            for i in range(1, steps):  # Skip first and last points (nodes)
                x += x_inc
                y += y_inc
                
                row, col = int(y), int(x)
                if 0 <= row < rows and 0 <= col < cols:
                    # Choose character based on direction
                    if dx == 0:  # Vertical line
                        char = vertical
                    elif dy == 0:  # Horizontal line
                        char = horizontal
                    else:  # Diagonal line
                        char = se_diagonal if (dx > 0 and dy > 0) or (dx < 0 and dy < 0) else ne_diagonal
                    
                    # Check for line crossings
                    if grid[row][col] != " ":
                        # If there's already a character, use a crossing character
                        existing = grid[row][col]
                        if (char == horizontal and 
                            (existing == vertical or 
                             existing == f"{style_prefix}{vertical}{style_suffix}")):
                            char = cross
                        elif (char == vertical and 
                             (existing == horizontal or 
                              existing == f"{style_prefix}{horizontal}{style_suffix}")):
                            char = cross
                    
                    grid[row][col] = f"{style_prefix}{char}{style_suffix}"
        else:
            # For non-aligned paths, create a path with corners
            # Determine if we should go horizontal first or vertical first
            horiz_first = abs(dx) > abs(dy)
            
            if horiz_first:
                # Go horizontally most of the way, then vertically
                mid_col = dst_col
                mid_row = src_row
                
                # Draw first segment (horizontal)
                direction = 1 if dx > 0 else -1
                for col in range(src_col + direction, mid_col, direction):
                    if 0 <= src_row < rows and 0 <= col < cols:
                        grid[src_row][col] = f"{style_prefix}{horizontal}{style_suffix}"
                
                # Draw corner
                if 0 <= mid_row < rows and 0 <= mid_col < cols:
                    corner_char = bottom_left if dy > 0 else top_left
                    if dy < 0:
                        corner_char = top_left if dx > 0 else top_right
                    else:
                        corner_char = bottom_left if dx > 0 else bottom_right
                    grid[mid_row][mid_col] = f"{style_prefix}{corner_char}{style_suffix}"
                
                # Draw second segment (vertical)
                direction = 1 if dy > 0 else -1
                for row in range(mid_row + direction, dst_row, direction):
                    if 0 <= row < rows and 0 <= mid_col < cols:
                        grid[row][mid_col] = f"{style_prefix}{vertical}{style_suffix}"
            else:
                # Go vertically most of the way, then horizontally
                mid_col = src_col
                mid_row = dst_row
                
                # Draw first segment (vertical)
                direction = 1 if dy > 0 else -1
                for row in range(src_row + direction, mid_row, direction):
                    if 0 <= row < rows and 0 <= mid_col < cols:
                        grid[row][mid_col] = f"{style_prefix}{vertical}{style_suffix}"
                
                # Draw corner
                if 0 <= mid_row < rows and 0 <= mid_col < cols:
                    corner_char = top_right if dx > 0 else top_left
                    if dx < 0:
                        corner_char = top_left if dy > 0 else bottom_left
                    else:
                        corner_char = top_right if dy > 0 else bottom_right
                    grid[mid_row][mid_col] = f"{style_prefix}{corner_char}{style_suffix}"
                
                # Draw second segment (horizontal)
                direction = 1 if dx > 0 else -1
                for col in range(mid_col + direction, dst_col, direction):
                    if 0 <= mid_row < rows and 0 <= col < cols:
                        grid[mid_row][col] = f"{style_prefix}{horizontal}{style_suffix}"
        
        # Draw an arrow near the target
        arrow_offset = 2  # Distance from target node
        arrow_row, arrow_col = dst_row, dst_col
        
        # Position the arrow based on approach direction
        if abs(dx) > abs(dy):  # Approaching horizontally
            arrow_char = right_arrow if dx > 0 else left_arrow
            arrow_col = dst_col - (arrow_offset if dx > 0 else -arrow_offset)
        else:  # Approaching vertically
            arrow_char = down_arrow if dy > 0 else up_arrow
            arrow_row = dst_row - (arrow_offset if dy > 0 else -arrow_offset)
        
        # Draw the arrow if in bounds
        if (0 <= arrow_row < rows and 0 <= arrow_col < cols):
            grid[arrow_row][arrow_col] = f"{style_prefix}{arrow_char}{style_suffix}"
        
        # Add visual indicator for recent logs
        if has_recent_logs:
            # Calculate midpoint on the edge
            midpoint_row = (src_row + dst_row) // 2
            midpoint_col = (src_col + dst_col) // 2
            
            # Add visual indicator (e.g., a star or dot)
            if 0 <= midpoint_row < rows and 0 <= midpoint_col < cols:
                grid[midpoint_row][midpoint_col] = "*"
    
    def _navigate_nodes(self, direction: str) -> None:
        """
        Navigate between nodes using arrow keys.
        
        This implementation supports intelligent navigation based on graph structure.
        
        Args:
            direction: The direction to navigate ("up", "down", "left", "right").
        """
        # If no node is selected, select the first one
        if not self.selected_node:
            if self.node_layout:
                self.selected_node = next(iter(self.node_layout.keys()))
                self.needs_refresh = True
            return
        
        current_node = self.selected_node
        
        # Get current position
        if current_node not in self.node_layout:
            return
            
        current_row, current_col = self.node_layout[current_node]
        
        # First, try to navigate using graph structure
        if direction == "left" or direction == "up":
            # Try to navigate to a predecessor (incoming edge)
            predecessors = list(self.dag_model.graph.predecessors(current_node))
            if predecessors:
                # Find the closest predecessor in the requested direction
                closest = None
                min_distance = float('inf')
                
                for pred_id in predecessors:
                    if pred_id in self.node_layout:
                        pred_row, pred_col = self.node_layout[pred_id]
                        
                        # Check if it's in the right direction
                        if (direction == "left" and pred_col < current_col) or \
                           (direction == "up" and pred_row < current_row):
                            # Calculate distance (Manhattan distance)
                            distance = abs(pred_row - current_row) + abs(pred_col - current_col)
                            if distance < min_distance:
                                min_distance = distance
                                closest = pred_id
                
                if closest:
                    self.selected_node = closest
                    self.selected_edge = None
                    self.needs_refresh = True
                    return
                    
        elif direction == "right" or direction == "down":
            # Try to navigate to a successor (outgoing edge)
            successors = list(self.dag_model.graph.successors(current_node))
            if successors:
                # Find the closest successor in the requested direction
                closest = None
                min_distance = float('inf')
                
                for succ_id in successors:
                    if succ_id in self.node_layout:
                        succ_row, succ_col = self.node_layout[succ_id]
                        
                        # Check if it's in the right direction
                        if (direction == "right" and succ_col > current_col) or \
                           (direction == "down" and succ_row > current_row):
                            # Calculate distance (Manhattan distance)
                            distance = abs(succ_row - current_row) + abs(succ_col - current_col)
                            if distance < min_distance:
                                min_distance = distance
                                closest = succ_id
                
                if closest:
                    self.selected_node = closest
                    self.selected_edge = None
                    self.needs_refresh = True
                    return
        
        # If graph structure navigation failed, fall back to position-based navigation
        closest_node = None
        min_distance = float('inf')
        
        for node_id, (row, col) in self.node_layout.items():
            if node_id == current_node:
                continue
                
            # Check if the node is in the desired direction
            if (direction == "up" and row < current_row) or \
               (direction == "down" and row > current_row) or \
               (direction == "left" and col < current_col) or \
               (direction == "right" and col > current_col):
                
                # Calculate the distance (Manhattan distance)
                distance = abs(row - current_row) + abs(col - current_col)
                
                # Prioritize nodes that are more directly aligned with the direction
                alignment_penalty = 0
                if direction in ["up", "down"]:
                    alignment_penalty = abs(col - current_col) * 2
                else:
                    alignment_penalty = abs(row - current_row) * 2
                
                adjusted_distance = distance + alignment_penalty
                
                if adjusted_distance < min_distance:
                    min_distance = adjusted_distance
                    closest_node = node_id
        
        if closest_node:
            self.selected_node = closest_node
            self.selected_edge = None
            self.needs_refresh = True
    
    def _toggle_expanded_view(self) -> None:
        """Toggle expanded view for the selected node or edge."""
        # Handle node selection
        if self.selected_node:
            # Select edge between nodes if shift is pressed
            self._select_edges_for_node(self.selected_node)
        # Handle edge selection
        elif self.selected_edge:
            self._select_edge_details(*self.selected_edge)
    
    def _select_edges_for_node(self, node_id: str) -> None:
        """
        Cycle through edges connected to a node.
        
        Args:
            node_id: The ID of the node.
        """
        # Get all edges connected to this node
        connected_edges = []
        
        # Add outgoing edges
        for target_id in self.dag_model.graph.successors(node_id):
            edge_key = (node_id, target_id)
            if edge_key in self.dag_model.edges:
                connected_edges.append(edge_key)
        
        # Add incoming edges
        for source_id in self.dag_model.graph.predecessors(node_id):
            edge_key = (source_id, node_id)
            if edge_key in self.dag_model.edges:
                connected_edges.append(edge_key)
        
        if not connected_edges:
            return
            
        # If no edge is currently selected, select the first one
        if not self.selected_edge:
            self.selected_edge = connected_edges[0]
            self.selected_node = None
            self.needs_refresh = True
            return
            
        # If an edge is already selected, cycle to the next one
        try:
            current_index = connected_edges.index(self.selected_edge)
            next_index = (current_index + 1) % len(connected_edges)
            self.selected_edge = connected_edges[next_index]
            self.selected_node = None
            self.needs_refresh = True
        except ValueError:
            # Current edge not in the list, select the first one
            self.selected_edge = connected_edges[0]
            self.selected_node = None
            self.needs_refresh = True
    
    def _select_edge_details(self, source_id: str, target_id: str) -> None:
        """
        Select an edge for details view.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
        """
        self.notify("edge_selected", (source_id, target_id))
    
    def on_key(self, event: Any) -> None:
        """
        Handle keyboard input events.
        
        Args:
            event: The key event.
        """
        key = event.key
        
        # Navigation with arrow keys
        if key == "up" or key == "down" or key == "left" or key == "right":
            self._navigate_nodes(key)
        # Toggle details with Enter
        elif key == "enter":
            self._toggle_expanded_view()
        # Toggle details panel
        elif key == "d":
            self.show_details = not self.show_details
            self.needs_refresh = True
        # Toggle logs panel
        elif key == "l":
            self.show_logs = not self.show_logs
            self.needs_refresh = True
        # Toggle incremental rendering
        elif key == "i":
            self.incremental_render = not self.incremental_render
            self.needs_refresh = True
        # Force refresh layout
        elif key == "r":
            # Force refresh
            self.dag_model.compute_layout(force=True)
            self.needs_refresh = True
        # Search node by ID or name
        elif key == "f":
            self._show_search_dialog()
        # Cycle through nodes
        elif key == "tab":
            self._cycle_node_selection()
        # Filter by status
        elif key == "1" or key == "2" or key == "3" or key == "4" or key == "5":
            self._filter_by_status(key)
        # Filter by node type
        elif key == "t":
            self._show_type_filter_dialog()
        # Reset filters
        elif key == "escape":
            self._reset_filters()
    
    def _show_search_dialog(self) -> None:
        """Show a search dialog to find nodes by ID or name."""
        # This would be implemented using Textual's modal dialog
        # For now, just log that it's not implemented
        logger.info("Search dialog not implemented yet")
    
    def _cycle_node_selection(self) -> None:
        """Cycle through nodes in the layout."""
        if not self.node_layout:
            return
            
        node_ids = list(self.node_layout.keys())
        
        if not self.selected_node:
            # If no node is selected, select the first one
            self.selected_node = node_ids[0]
        else:
            # Get current index and move to the next
            try:
                current_index = node_ids.index(self.selected_node)
                next_index = (current_index + 1) % len(node_ids)
                self.selected_node = node_ids[next_index]
            except ValueError:
                # Current node not in the list, select the first one
                self.selected_node = node_ids[0]
        
        # Clear edge selection and refresh
        self.selected_edge = None
        self.needs_refresh = True
    
    def _filter_by_status(self, key: str) -> None:
        """
        Filter nodes by status based on numeric key.
        
        Args:
            key: The key pressed (1-5).
        """
        # Map numeric keys to statuses
        status_map = {
            "1": AgentStatus.PENDING,
            "2": AgentStatus.INITIALIZING,
            "3": AgentStatus.RUNNING,
            "4": AgentStatus.PAUSED,
            "5": AgentStatus.STOPPED
        }
        
        if key in status_map:
            # Notify about filter
            logger.info(f"Filtering by status: {status_map[key]}")
            
            # This is a placeholder for actual filtering implementation
            # In a real implementation, you'd highlight or only show nodes with this status
    
    def _show_type_filter_dialog(self) -> None:
        """Show a dialog to filter nodes by type."""
        # This would be implemented using Textual's modal dialog
        # For now, just log that it's not implemented
        logger.info("Type filter dialog not implemented yet")
    
    def _reset_filters(self) -> None:
        """Reset all filters."""
        # This is a placeholder for actual filter reset implementation
        logger.info("Filters reset")
        self.needs_refresh = True


class NodeDetailWidget(Static):
    """Widget for displaying detailed information about a selected node with expanded view support."""
    
    expanded = reactive(False)
    
    def __init__(self, dag_model: DAGModel, *args, **kwargs):
        """Initialize the node detail widget."""
        super().__init__(*args, **kwargs)
        self.dag_model = dag_model
        self.node_id = None
        self.node = None
        self.show_metrics = True
    
    def set_node(self, node_id: str) -> None:
        """
        Set the node to display.
        
        Args:
            node_id: The ID of the node to display.
        """
        self.node_id = node_id
        self.node = self.dag_model.nodes.get(node_id)
        self.refresh()
    
    def toggle_expanded(self) -> None:
        """Toggle expanded view."""
        self.expanded = not self.expanded
        self.refresh()
    
    def toggle_metrics(self) -> None:
        """Toggle metrics display."""
        self.show_metrics = not self.show_metrics
        self.refresh()
    
    def render(self) -> RenderResult:
        """
        Render the node details.
        
        Returns:
            Rich renderable.
        """
        if not self.node:
            return Panel("No node selected", title="Node Details")
        
        # Basic information table
        info_table = Table(show_header=False, box=ROUNDED)
        info_table.add_column("Property", style="bold cyan")
        info_table.add_column("Value")
        
        # Add basic info
        info_table.add_row("ID", self.node.id)
        info_table.add_row("Name", self.node.name)
        info_table.add_row("Type", self.node.node_type)
        
        # Status with color
        status_color = "green" if self.node.status == AgentStatus.RUNNING else (
            "yellow" if self.node.status in [AgentStatus.PENDING, AgentStatus.INITIALIZING] else "red"
        )
        info_table.add_row("Status", f"[{status_color}]{self.node.status}[/]")
        
        # Created/Updated timestamps
        created_at = self.node.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(self.node.created_at, "strftime") else str(self.node.created_at)
        updated_at = self.node.updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(self.node.updated_at, "strftime") else str(self.node.updated_at)
        info_table.add_row("Created", created_at)
        info_table.add_row("Updated", updated_at)
        
        # Performance metrics section
        metrics_panel = None
        if self.show_metrics and hasattr(self.node, 'performance_metrics') and self.node.performance_metrics:
            metrics = self.node.performance_metrics
            
            # Create a table for metrics
            metrics_table = Table(show_header=True, box=ROUNDED)
            metrics_table.add_column("Metric", style="bold cyan")
            metrics_table.add_column("Latest")
            metrics_table.add_column("Average")
            metrics_table.add_column("Min")
            metrics_table.add_column("Max")
            metrics_table.add_column("95th %")
            metrics_table.add_column("Trend")
            
            # Format metrics nicely with units and visual indicators
            metrics_map = {
                "response_time_ms": {
                    "name": "Response Time",
                    "unit": "ms",
                    "high_is_bad": True
                },
                "memory_usage_mb": {
                    "name": "Memory Usage",
                    "unit": "MB",
                    "high_is_bad": True
                },
                "cpu_usage_percent": {
                    "name": "CPU Usage",
                    "unit": "%",
                    "high_is_bad": True
                },
                "completion_rate": {
                    "name": "Completion Rate",
                    "unit": "%",
                    "high_is_bad": False,
                    "multiply": 100
                },
                "error_rate": {
                    "name": "Error Rate",
                    "unit": "%",
                    "high_is_bad": True,
                    "multiply": 100
                },
                "throughput": {
                    "name": "Throughput",
                    "unit": "req/s",
                    "high_is_bad": False
                },
                "task_queue_size": {
                    "name": "Queue Size",
                    "unit": "",
                    "high_is_bad": True
                }
            }
            
            # Health score row (if available)
            if "health_score" in metrics:
                health_score = metrics["health_score"]
                health_color = "green" if health_score >= 0.7 else (
                    "yellow" if health_score >= 0.4 else "red"
                )
                
                # Create health bar visualization
                bar_width = 20
                filled = int(health_score * bar_width)
                health_bar = f"[{health_color}]{'█' * filled}{'░' * (bar_width - filled)}[/]"
                
                metrics_table.add_row(
                    "Health Score", 
                    f"[{health_color}]{health_score*100:.1f}% {health_bar}[/]",
                    "", "", "", "", ""
                )
            
            # Add rows for each metric
            for metric_key, metric_info in metrics_map.items():
                if metric_key not in metrics:
                    continue
                    
                metric_data = metrics[metric_key]
                name = metric_info["name"]
                unit = metric_info["unit"]
                high_is_bad = metric_info.get("high_is_bad", True)
                multiply = metric_info.get("multiply", 1)
                
                # Function to format a value with optional color
                def format_value(value, color=None):
                    if value is None:
                        return "N/A"
                    
                    formatted = f"{value * multiply:.1f}{unit}" if value else "N/A"
                    return f"[{color}]{formatted}[/]" if color else formatted
                
                # Get values
                latest = metric_data.get("latest")
                avg = metric_data.get("average")
                min_val = metric_data.get("min")
                max_val = metric_data.get("max")
                p95 = metric_data.get("p95")
                
                # Determine colors based on whether high values are good or bad
                # and relative to the other values
                if latest is not None and avg is not None:
                    latest_color = None
                    ratio = latest / avg if avg else 1
                    
                    threshold = 1.5 if high_is_bad else 0.7
                    if (high_is_bad and ratio > threshold) or (not high_is_bad and ratio < threshold):
                        latest_color = "red"
                    elif (high_is_bad and ratio > 1.2) or (not high_is_bad and ratio < 0.9):
                        latest_color = "yellow"
                    else:
                        latest_color = "green"
                else:
                    latest_color = None
                
                # Add trend indicator based on metric trends
                trend = ""
                if "trends" in metrics and metric_key in metrics["trends"]:
                    trend_value = metrics["trends"][metric_key]
                    trend_color = None
                    
                    if (high_is_bad and trend_value > 0) or (not high_is_bad and trend_value < 0):
                        trend_char = "▲" if trend_value > 0 else "▼"
                        trend_color = "red"
                    elif (high_is_bad and trend_value < 0) or (not high_is_bad and trend_value > 0):
                        trend_char = "▲" if trend_value > 0 else "▼"
                        trend_color = "green"
                    else:
                        trend_char = "◆"
                        trend_color = "cyan"
                        
                    trend = f"[{trend_color}]{trend_char}[/]"
                
                # Add row for this metric
                metrics_table.add_row(
                    name,
                    format_value(latest, latest_color),
                    format_value(avg),
                    format_value(min_val),
                    format_value(max_val),
                    format_value(p95),
                    trend
                )
            
            metrics_panel = Panel(
                metrics_table,
                title="Performance Metrics",
                border_style="cyan"
            )
        
        # Metadata section
        metadata_panel = None
        if self.expanded and self.node.metadata:
            # Create a table for metadata
            metadata_table = Table(show_header=False, box=ROUNDED)
            metadata_table.add_column("Key", style="bold cyan")
            metadata_table.add_column("Value")
            
            # Add rows for each metadata item
            for key, value in self.node.metadata.items():
                # Skip performance metrics which we show separately
                if key == "performance_metrics":
                    continue
                    
                if isinstance(value, dict):
                    # For nested dictionaries, show as JSON
                    import json
                    value_str = json.dumps(value, indent=2)
                    metadata_table.add_row(key, value_str)
                else:
                    metadata_table.add_row(key, str(value))
            
            metadata_panel = Panel(
                metadata_table,
                title="Metadata",
                border_style="blue"
            )
        
        # Create a list of sections to display
        sections = []
        sections.append(Panel(info_table, title="Basic Information", border_style="green"))
        
        if metrics_panel:
            sections.append(metrics_panel)
            
        if metadata_panel:
            sections.append(metadata_panel)
        
        # Create toggle buttons
        buttons = Text()
        buttons.append("[E] ")
        if self.expanded:
            buttons.append("[Collapse]", style="bold blue")
        else:
            buttons.append("[Expand]", style="blue")
            
        buttons.append("   [M] ")
        if self.show_metrics:
            buttons.append("[Hide Metrics]", style="bold blue")
        else:
            buttons.append("[Show Metrics]", style="blue")
        
        # Create help text
        if not self.expanded:
            help_text = Text("Press 'E' to show more details", style="dim")
            sections.append(help_text)
        
        # Create the vertical container with all sections
        return Vertical(
            *sections,
            buttons,
            id="node_details"
        )


class EdgeDetailWidget(Static):
    """Widget for displaying detailed information about a selected edge."""
    
    def __init__(self, dag_model: DAGModel, *args, **kwargs):
        """
        Initialize the edge detail widget.
        
        Args:
            dag_model: The DAG model.
            *args: Additional positional arguments for the parent class.
            **kwargs: Additional keyword arguments for the parent class.
        """
        super().__init__(*args, **kwargs)
        self.dag_model = dag_model
        self.source_id = None
        self.target_id = None
    
    def set_edge(self, source_id: str, target_id: str) -> None:
        """
        Set the edge to display details for.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
        """
        self.source_id = source_id
        self.target_id = target_id
        self.refresh()
    
    def render(self) -> RenderResult:
        """
        Render the edge details.
        
        Returns:
            Rich renderable for the details.
        """
        if not self.source_id or not self.target_id:
            return Panel("No edge selected", title="Edge Details")
        
        edge_key = (self.source_id, self.target_id)
        if edge_key not in self.dag_model.edges:
            return Panel("Edge not found", title="Edge Details")
        
        edge = self.dag_model.edges[edge_key]
        
        # Create a table for the details
        table = Table(box=ROUNDED)
        table.add_column("Property")
        table.add_column("Value")
        
        # Add basic properties
        source_name = self.dag_model.nodes[edge.source_id].name if edge.source_id in self.dag_model.nodes else "Unknown"
        target_name = self.dag_model.nodes[edge.target_id].name if edge.target_id in self.dag_model.nodes else "Unknown"
        
        table.add_row("Source", f"{edge.source_id} ({source_name})")
        table.add_row("Target", f"{edge.target_id} ({target_name})")
        table.add_row("Type", edge.edge_type)
        
        # Add timestamps
        table.add_row("Created", edge.created_at.isoformat())
        table.add_row("Updated", edge.updated_at.isoformat())
        
        # Add metadata
        if edge.metadata:
            metadata_str = "\n".join([f"{k}: {v}" for k, v in edge.metadata.items()])
            table.add_row("Metadata", metadata_str)
        
        return Panel(table, title=f"Edge Details: {source_name} → {target_name}")


class EdgeLogWidget(Log):
    """Widget for displaying log entries for an edge with enhanced filtering."""
    
    def __init__(self, dag_model: DAGModel, *args, **kwargs):
        """
        Initialize the log widget.
        
        Args:
            dag_model: The DAG model.
            *args: Additional arguments for Log.
            **kwargs: Additional keyword arguments for Log.
        """
        super().__init__(*args, **kwargs)
        self.dag_model = dag_model
        self.edge_key = None
        self.highlight_time = 3.0  # Seconds to highlight new logs
        self.max_lines = 100  # Maximum number of log lines to display
        self.current_filter = None  # Current log filter
        
        # Register for log events
        self.dag_model.add_observer("edge_log_added", self._on_log_added)
    
    def on_mount(self) -> None:
        """Set up widget when mounted."""
        # Set up keyboard handlers when mounted
        self._setup_keyboard_handlers()
        
        # Display status message
        self.write_line("[dim]Log display ready. Use keyboard shortcuts to filter:[/]")
        self.write_line("[dim]  I: INFO only   W: WARNING only   E: ERROR only[/]")
        self.write_line("[dim]  A: All logs    T: Last 5 min     C: Clear logs[/]")
    
    def set_edge(self, source_id: str, target_id: str) -> None:
        """
        Set the edge to display logs for.
        
        Args:
            source_id: The ID of the source node.
            target_id: The ID of the target node.
        """
        self.edge_key = (source_id, target_id)
        self._refresh_logs()
    
    def _refresh_logs(self):
        """Refresh the log display with current filter settings."""
        self.clear()
        
        # Get logs for the edge
        if self.edge_key in self.dag_model.edges:
            # Apply filters if needed
            filter_level = None
            filter_time = None
            
            if self.current_filter:
                filter_type, filter_value = self.current_filter
                
                if filter_type == "level":
                    filter_level = filter_value
                elif filter_type == "time":
                    filter_time = filter_value
            
            logs = self.dag_model.get_logs_for_edge(
                self.edge_key[0], 
                self.edge_key[1], 
                limit=self.max_lines,
                filter_level=filter_level,
                filter_time=filter_time
            )
            
            # Display logs
            for log in logs:
                self.write_line(log.get_formatted_message())
                
            # Add a status line showing current filter
            filter_info = ""
            if self.current_filter:
                filter_type, filter_value = self.current_filter
                if filter_type == "level":
                    filter_info = f"[Filtered by level: {filter_value}]"
                elif filter_type == "time":
                    minutes = int(filter_value / 60)
                    filter_info = f"[Showing last {minutes} minutes]"
            
            if filter_info:
                self.write_line(f"\n{filter_info}")
    
    def _apply_filter(self, log: LogEntry) -> bool:
        """
        Apply the current filter to a log entry.
        
        Args:
            log: The log entry.
            
        Returns:
            True if the log passes the filter, False otherwise.
        """
        if not self.current_filter:
            return True
            
        filter_type, filter_value = self.current_filter
        
        if filter_type == "level":
            return log.level == filter_value
        elif filter_type == "time":
            # Filter by time (filter_value is seconds)
            current_time = time.time()
            return current_time - log.timestamp <= float(filter_value)
            
        return True
    
    def set_filter(self, filter_type: str, filter_value: Any) -> None:
        """
        Set a filter for the logs.
        
        Args:
            filter_type: The type of filter ("level", "time").
            filter_value: The filter value.
        """
        self.current_filter = (filter_type, filter_value)
        self._refresh_logs()
    
    def clear_filter(self) -> None:
        """Clear the current filter."""
        self.current_filter = None
        self._refresh_logs()
    
    def _on_log_added(self, data: Tuple[Tuple[str, str], LogEntry]) -> None:
        """
        Handle a new log entry.
        
        Args:
            data: Tuple of (edge_key, log_entry).
        """
        edge_key, log = data
        
        # Only update if this is for our edge
        if self.edge_key == edge_key:
            # Apply filter
            if self._apply_filter(log):
                # Add with highlighting
                line = self.write_line(log.get_formatted_message())
                
                # Add highlight
                if line is not None:
                    line.stylize("reverse")
                    
                    # Schedule removal of highlight
                    def _remove_highlight():
                        # We can't modify the existing line, so instead
                        # let's just refresh the entire view
                        self._refresh_logs()
                        
                    self.set_timer(self.highlight_time, _remove_highlight)
                    
    def _setup_keyboard_handlers(self) -> None:
        """Set up keyboard handlers for log filtering."""
        try:
            app = self.app
            app._register_shortcut("i", "filter_info", "Filter: INFO")
            app._register_shortcut("w", "filter_warning", "Filter: WARNING")
            app._register_shortcut("e", "filter_error", "Filter: ERROR")
            app._register_shortcut("a", "filter_all", "Filter: All")
            app._register_shortcut("t", "filter_time", "Filter: Recent")
            app._register_shortcut("c", "clear_logs", "Clear Logs")
        except Exception:
            # App might not be accessible yet
            pass
    
    def handle_shortcut(self, action: str) -> None:
        """
        Handle a keyboard shortcut action.
        
        Args:
            action: The action to perform.
        """
        if action == "filter_info":
            self.set_filter("level", "INFO")
        elif action == "filter_warning":
            self.set_filter("level", "WARNING")
        elif action == "filter_error":
            self.set_filter("level", "ERROR")
        elif action == "filter_all":
            self.clear_filter()
        elif action == "filter_time":
            # Filter last 5 minutes
            self.set_filter("time", 300)
        elif action == "clear_logs":
            self.clear()


class HelpPanel(Static):
    """Help panel with keyboard shortcuts and usage instructions."""
    
    def render(self) -> RenderResult:
        """
        Render the help panel.
        
        Returns:
            Rich renderable for the help panel.
        """
        table = Table(box=ROUNDED)
        table.add_column("Key", style="bold cyan")
        table.add_column("Action", style="green")
        table.add_column("Description")
        
        # Basic navigation
        table.add_row("↑ ↓ ← →", "Navigate", "Move between nodes")
        table.add_row("Tab", "Cycle Nodes", "Cycle through all nodes")
        table.add_row("Enter", "Select", "Select node or cycle connected edges")
        
        # Panel controls
        table.add_row("D", "Details Panel", "Toggle details panel")
        table.add_row("L", "Logs Panel", "Toggle logs panel")
        table.add_row("E", "Expand Details", "Expand/collapse details view")
        table.add_row("M", "Toggle Metrics", "Show/hide performance metrics")
        
        # Advanced features
        table.add_row("F", "Find", "Search for nodes by name/ID")
        table.add_row("1-5", "Filter Status", "Filter nodes by status")
        table.add_row("T", "Filter Type", "Filter nodes by type")
        table.add_row("Esc", "Reset Filters", "Clear all filters")
        
        # Performance features
        table.add_row("I", "Toggle Incremental", "Enable/disable incremental rendering")
        table.add_row("R", "Refresh Layout", "Force recalculate node layout")
        
        # Exit
        table.add_row("Q", "Quit", "Exit the visualization")
        
        # Tips section
        tips = [
            "• Click a node to select it",
            "• Use Enter to toggle between node and edge selection",
            "• Health status is indicated by colored diamond (◆) in nodes",
            "• Performance metrics show trends with ▲ (increasing) and ▼ (decreasing)",
        ]
        
        tips_text = Text("\n".join(tips))
        
        return Panel(
            Vertical(
                Panel(table, title="Keyboard Shortcuts"),
                Panel(tips_text, title="Tips"),
            ),
            title="Help"
        )


class AgentDAGApp(App):
    """
    Main application for visualizing agent DAG.
    
    This application provides an interactive terminal interface for
    viewing and interacting with the agent DAG.
    """
    
    TITLE = "Agent DAG Visualization"
    
    BINDINGS = [
        ("d", "toggle_details", "Toggle details panel"),
        ("l", "toggle_logs", "Toggle logs panel"),
        ("h", "toggle_help", "Toggle help panel"),
        ("r", "refresh_layout", "Refresh layout"),
        ("i", "toggle_incremental", "Toggle incremental rendering"),
        ("m", "toggle_metrics", "Toggle performance metrics"),
        ("f", "find_node", "Find node by name/ID"),
        ("t", "filter_by_type", "Filter by node type"),
        ("escape", "reset_filters", "Reset all filters"),
        ("q", "quit", "Quit"),
    ]
    
    CSS = """
    #dag-widget {
        width: 100%;
        height: 3fr;
        border: solid $primary;
    }
    
    #detail-container {
        height: 2fr;
        layout: horizontal;
    }
    
    #detail-widget {
        width: 1fr;
        height: 100%;
        border: solid $primary;
    }
    
    #log-widget {
        width: 2fr;
        height: 100%;
        border: solid $primary;
        background: $surface;
    }
    
    #log-controls {
        dock: bottom;
        height: auto;
        padding: 1;
        background: $panel;
        layout: horizontal;
        align: center middle;
    }
    
    #log-controls Button {
        margin: 0 1 0 1;
        width: auto;
    }
    
    #log-controls Label {
        margin: 0 1 0 0;
        padding: 1;
        color: $text;
    }
    
    Button#filter-info {
        background: $boost;
        color: $text;
    }
    
    Button#filter-warning {
        background: $warning;
        color: $text;
    }
    
    Button#filter-error {
        background: $error;
        color: $text;
    }
    
    Button#clear-logs {
        background: $primary-darken-2;
        color: $text;
    }
    
    #help-panel {
        dock: right;
        width: 40;
        height: 100%;
        border: solid $primary;
        background: $surface;
        display: none;
    }
    """
    
    def __init__(self, dag_model: DAGModel, *args, **kwargs):
        """
        Initialize the DAG application.
        
        Args:
            dag_model: The DAG model to visualize.
            *args: Additional positional arguments for the parent class.
            **kwargs: Additional keyword arguments for the parent class.
        """
        super().__init__(*args, **kwargs)
        self.dag_model = dag_model
        self.show_help = False
        self.selected_node = None
        self.selected_edge = None
        
        # Performance monitoring
        self.last_refresh_time = time.time()
        self.refresh_count = 0
        self.avg_refresh_time = 0
    
    def _register_shortcut(self, key: str, action: str, description: str) -> None:
        """
        Register a keyboard shortcut.
        
        Args:
            key: The key to register.
            action: The action name.
            description: Description of the action.
        """
        # This ensures shortcuts are properly registered with the app
        self.BINDINGS.append((key, action, description))
    
    def compose(self) -> ComposeResult:
        """
        Compose the UI layout.
        
        Returns:
            The composed UI elements.
        """
        # Main layout with header and footer
        header = Header()
        footer = Footer()
        
        # Main visualization widget
        dag_widget = DAGWidget(self.dag_model)
        
        # Details panel
        node_details = NodeDetailWidget(self.dag_model)
        
        # Edge details and logs
        edge_details = EdgeDetailWidget(self.dag_model)
        edge_logs = EdgeLogWidget(self.dag_model)
        
        # Help panel
        help_panel = HelpPanel()
        
        # Layout containers
        details_container = Container(
            node_details,
            edge_details,
            id="details_container"
        )
        
        main_container = Container(
            Horizontal(
                dag_widget,
                details_container,
                id="main_horizontal"
            ),
            edge_logs,
            id="main_container"
        )
        
        help_container = Container(
            help_panel,
            id="help_container",
            classes="hidden"
        )
        
        # Yield all components
        yield header
        yield main_container
        yield help_container
        yield footer
    
    def on_mount(self) -> None:
        """Set up the application when mounted."""
        # Initialize node list for arrow navigation
        self._initialize_node_list()
        
        # Set up refresh timer
        self.set_interval(1.0, self._periodic_refresh)
        
        # Register event handlers
        dag_widget = self.query_one(DAGWidget)
        dag_widget.register_watch(dag_widget.watch_selected_node, self._on_node_selected)
        dag_widget.register_watch(dag_widget.watch_selected_edge, self._on_edge_selected)
    
    def _periodic_refresh(self) -> None:
        """Periodically refresh the visualization and update metrics."""
        # Update performance metrics
        self.dag_model.update_performance_metrics()
        
        # Force a refresh every X seconds
        current_time = time.time()
        if current_time - self.last_refresh_time >= 5.0:
            self.last_refresh_time = current_time
            self.action_refresh_layout()
    
    def _initialize_node_list(self) -> None:
        """Initialize the list of nodes for navigation."""
        # This will be handled by the DAGWidget directly
        pass
    
    def _on_node_selected(self, node_id: str) -> None:
        """
        Handle node selection events.
        
        Args:
            node_id: The ID of the selected node.
        """
        if node_id is None:
            return
            
        self.selected_node = node_id
        self.selected_edge = None
        
        # Update node details
        node_details = self.query_one(NodeDetailWidget)
        node_details.set_node(node_id)
    
    def _on_edge_selected(self, edge_key: Tuple[str, str]) -> None:
        """
        Handle edge selection events.
        
        Args:
            edge_key: The key of the selected edge (source_id, target_id).
        """
        if edge_key is None:
            return
            
        source_id, target_id = edge_key
        self.selected_edge = edge_key
        self.selected_node = None
        
        # Update edge details and logs
        edge_details = self.query_one(EdgeDetailWidget)
        edge_logs = self.query_one(EdgeLogWidget)
        
        edge_details.set_edge(source_id, target_id)
        edge_logs.set_edge(source_id, target_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handle button press events.
        
        Args:
            event: The button press event.
        """
        button_id = event.button.id
        
        if button_id == "btn_refresh":
            self.action_refresh_layout()
        elif button_id == "btn_toggle_details":
            self.action_toggle_details()
        elif button_id == "btn_toggle_logs":
            self.action_toggle_logs()
        elif button_id == "btn_toggle_help":
            self.action_toggle_help()
        elif button_id == "btn_toggle_incremental":
            self.action_toggle_incremental()
        elif button_id == "btn_toggle_metrics":
            self.action_toggle_metrics()

    def action_toggle_details(self) -> None:
        """Toggle the details panel."""
        details_container = self.query_one("#details_container")
        details_container.toggle_class("hidden")
    
    def action_toggle_logs(self) -> None:
        """Toggle the logs panel."""
        edge_logs = self.query_one(EdgeLogWidget)
        edge_logs.toggle_class("hidden")
        
        # If showing logs and an edge is selected, update the logs
        if not edge_logs.has_class("hidden") and self.selected_edge:
            edge_logs.set_edge(*self.selected_edge)
    
    def action_toggle_help(self) -> None:
        """Toggle the help panel."""
        help_container = self.query_one("#help_container")
        main_container = self.query_one("#main_container")
        
        help_container.toggle_class("hidden")
        main_container.toggle_class("hidden")
        
        self.show_help = not self.show_help
    
    def action_refresh_layout(self) -> None:
        """Refresh the layout."""
        # Force recalculation of the layout
        self.dag_model.compute_layout(force=True)
        
        # Trigger a refresh of the DAG widget
        dag_widget = self.query_one(DAGWidget)
        dag_widget.needs_refresh = True
    
    def action_toggle_incremental(self) -> None:
        """Toggle incremental rendering."""
        dag_widget = self.query_one(DAGWidget)
        dag_widget.incremental_render = not dag_widget.incremental_render
        dag_widget.needs_refresh = True
    
    def action_toggle_metrics(self) -> None:
        """Toggle performance metrics display."""
        node_details = self.query_one(NodeDetailWidget)
        if hasattr(node_details, 'toggle_metrics'):
            node_details.toggle_metrics()
    
    def action_find_node(self) -> None:
        """Show node search dialog."""
        # Placeholder for future implementation
        self.notify("Implementation of search is pending", title="Search")
    
    def action_filter_by_type(self) -> None:
        """Show node type filter dialog."""
        # Placeholder for future implementation
        self.notify("Implementation of type filtering is pending", title="Filter")
    
    def action_reset_filters(self) -> None:
        """Reset all filters."""
        # Placeholder for future implementation
        self.notify("Filters reset", title="Reset Filters")
    
    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


# Run the application
def run_dag_visualization(dag_model: Optional[DAGModel] = None) -> None:
    """
    Run the DAG visualization application.
    
    Args:
        dag_model: Optional DAG model to visualize. If not provided,
            a new model will be created.
    """
    if dag_model is None:
        dag_model = DAGModel()
        
    app = AgentDAGApp(dag_model)
    app.run()


if __name__ == "__main__":
    # Example usage
    dag_model = DAGModel()
    
    # Add some example nodes and edges
    from src.visualization.dag.model import NodeData, EdgeData
    from datetime import datetime
    import random
    
    # Create nodes
    for i in range(5):
        node = NodeData(
            id=f"agent{i}",
            name=f"Agent {i}",
            node_type=random.choice(["trader", "analyzer", "monitor"]),
            status=random.choice(list(AgentStatus)),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        dag_model.add_node(node)
    
    # Create edges
    edges = [
        ("agent0", "agent1"),
        ("agent0", "agent2"),
        ("agent1", "agent3"),
        ("agent2", "agent4"),
        ("agent2", "agent3")
    ]
    
    for source, target in edges:
        edge = EdgeData(
            source_id=source,
            target_id=target,
            edge_type="data_flow",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        dag_model.add_edge(edge)
    
    # Add some logs
    for source, target in edges:
        for i in range(3):
            dag_model.add_log_to_edge(
                source,
                target,
                f"Example log message {i}",
                {"timestamp": datetime.now().isoformat()}
            )
    
    # Run the application
    run_dag_visualization(dag_model) 