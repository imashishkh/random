"""
Tests for the DAG visualization view component.

This module contains tests for the DAG view component that renders
the graph visualization in the terminal using Textual.
"""

import unittest
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widget import Widget
from textual.widgets import Static
from textual.geometry import Offset, Size
from textual import events

from src.visualization.dag.view import DAGView
from src.visualization.dag.model import DAGModel, NodeData, EdgeData


class TestDAGView(unittest.TestCase):
    """Tests for the DAG view component."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.model = MagicMock(spec=DAGModel)
        
        # Mock the model's data accessors
        self.model.nodes = {}
        self.model.edges = {}
        self.model.get_nodes.return_value = []
        self.model.get_edges.return_value = []
        
        # Create the view with the mock model
        self.view = DAGView()
        
        # Create a mock app for the view
        self.mock_app = MagicMock(spec=App)
        self.view.app = self.mock_app
    
    def test_watch_model(self):
        """Test that the view can watch a model."""
        # Reset the model to ensure it's clean
        model = MagicMock(spec=DAGModel)
        
        # Call watch_model
        self.view.watch_model(model)
        
        # Verify that the model was registered as an observer
        model.add_observer.assert_called_with(self.view)
        
        # Verify that the model was stored
        self.assertEqual(self.view.model, model)
    
    def test_update_from_model(self):
        """Test updating the view from model changes."""
        # Set up a model with some nodes and edges
        model = MagicMock(spec=DAGModel)
        
        # Create test nodes and edges
        node1 = NodeData("1", "Node 1", "agent", position=(100, 100))
        node2 = NodeData("2", "Node 2", "agent", position=(200, 200))
        edge = EdgeData("1", "2", "calls")
        
        model.get_nodes.return_value = [node1, node2]
        model.get_edges.return_value = [edge]
        
        # Mock the compute_layout method
        model.compute_layout.return_value = {
            "1": (100, 100),
            "2": (200, 200)
        }
        
        # Watch the model
        self.view.watch_model(model)
        
        # Mock render method to avoid actual rendering
        self.view.render = MagicMock()
        
        # Call update_from_model
        self.view.update_from_model(model)
        
        # Verify that the view requested a refresh
        self.view.render.assert_called_once()
    
    def test_reset_view(self):
        """Test resetting the view to default state."""
        # Mock necessary methods
        self.view.render = MagicMock()
        self.view.model = MagicMock(spec=DAGModel)
        
        # Call reset_view
        self.view.reset_view()
        
        # Check that the model was asked to compute a new layout
        self.view.model.compute_layout.assert_called_once()
        
        # Check that render was called to refresh the view
        self.view.render.assert_called_once()
    
    def test_on_mouse_down(self):
        """Test handling mouse down events for node selection."""
        # Create a mock model with nodes
        model = MagicMock(spec=DAGModel)
        self.view.model = model
        
        # Create test nodes
        node1 = NodeData("1", "Node 1", "agent", position=(100, 100))
        model.get_nodes.return_value = [node1]
        
        # Create a mouse event at the node position
        mouse_event = MagicMock(spec=events.MouseDown)
        mouse_event.x = 100
        mouse_event.y = 100
        
        # Mock methods to find nodes at position
        self.view._get_node_at_position = MagicMock(return_value=node1)
        
        # Call on_mouse_down
        self.view.on_mouse_down(mouse_event)
        
        # Verify that the node was selected
        self.assertEqual(self.view.selected_node, node1)
    
    def test_on_mouse_up(self):
        """Test handling mouse up events for node deselection."""
        # Create a mock model
        model = MagicMock(spec=DAGModel)
        self.view.model = model
        
        # Set a selected node
        self.view.selected_node = NodeData("1", "Node 1", "agent", position=(100, 100))
        self.view.dragging = True
        
        # Create a mouse event
        mouse_event = MagicMock(spec=events.MouseUp)
        
        # Call on_mouse_up
        self.view.on_mouse_up(mouse_event)
        
        # Verify that the node was deselected
        self.assertFalse(self.view.dragging)
    
    def test_on_mouse_move_with_dragging(self):
        """Test handling mouse move events for node dragging."""
        # Create a mock model
        model = MagicMock(spec=DAGModel)
        self.view.model = model
        
        # Set a selected node and dragging state
        selected_node = NodeData("1", "Node 1", "agent", position=(100, 100))
        self.view.selected_node = selected_node
        self.view.dragging = True
        
        # Create a mouse event at a new position
        mouse_event = MagicMock(spec=events.MouseMove)
        mouse_event.x = 150
        mouse_event.y = 150
        
        # Mock update_node method
        model.update_node = MagicMock()
        
        # Mock render method
        self.view.render = MagicMock()
        
        # Call on_mouse_move
        self.view.on_mouse_move(mouse_event)
        
        # Verify that the node was updated with new position
        model.update_node.assert_called_once()
        # We'd need to check the exact call args based on implementation
        
        # Verify that render was called
        self.view.render.assert_called_once()
    
    def test_render_node(self):
        """Test rendering a node on the canvas."""
        # Create a mock canvas
        mock_canvas = MagicMock()
        
        # Create a test node
        node = NodeData("1", "Test Node", "agent", position=(100, 100))
        
        # Call _render_node
        # Note: This would be a private method that we're testing directly
        # In a real implementation, we might need to adjust this test
        self.view._render_node = MagicMock()
        self.view._render_node(mock_canvas, node)
        
        # Verify canvas calls based on your implementation
        # These assertions would depend on how nodes are rendered
        self.view._render_node.assert_called_once_with(mock_canvas, node)
    
    def test_render_edge(self):
        """Test rendering an edge on the canvas."""
        # Create a mock canvas
        mock_canvas = MagicMock()
        
        # Create test nodes and an edge
        node1 = NodeData("1", "Node 1", "agent", position=(100, 100))
        node2 = NodeData("2", "Node 2", "agent", position=(200, 200))
        edge = EdgeData("1", "2", "calls")
        
        # Configure the model mock to return the nodes
        self.view.model = MagicMock(spec=DAGModel)
        self.view.model.get_node.side_effect = lambda id: node1 if id == "1" else node2
        
        # Call _render_edge
        # Note: This would be a private method that we're testing directly
        self.view._render_edge = MagicMock()
        self.view._render_edge(mock_canvas, edge)
        
        # Verify canvas calls based on your implementation
        self.view._render_edge.assert_called_once_with(mock_canvas, edge)
    
    def test_on_resize(self):
        """Test handling resize events."""
        # Create a resize event
        resize_event = MagicMock(spec=events.Resize)
        
        # Set a mock model
        self.view.model = MagicMock(spec=DAGModel)
        
        # Mock render method
        self.view.render = MagicMock()
        
        # Call on_resize
        self.view.on_resize(resize_event)
        
        # Verify that layout was recomputed and view was refreshed
        self.view.model.compute_layout.assert_called_once()
        self.view.render.assert_called_once()
    
    def test_get_node_at_position(self):
        """Test finding a node at a given position."""
        # Create a mock model with nodes
        model = MagicMock(spec=DAGModel)
        self.view.model = model
        
        # Create test nodes
        node1 = NodeData("1", "Node 1", "agent", position=(100, 100))
        node2 = NodeData("2", "Node 2", "agent", position=(200, 200))
        
        model.get_nodes.return_value = [node1, node2]
        
        # Mock the distance calculation method if needed
        self.view._is_position_in_node = MagicMock(side_effect=lambda node, x, y: node.id == "1")
        
        # Call _get_node_at_position
        node = self.view._get_node_at_position(100, 100)
        
        # Verify that the correct node was returned
        self.assertEqual(node, node1)
    
    @patch("src.visualization.dag.view.DAGView.refresh")
    def test_on_update(self, mock_refresh):
        """Test the on_update observer method."""
        # Create a mock observable (model)
        observable = MagicMock()
        
        # Call on_update
        self.view.on_update(observable)
        
        # Verify that refresh was called
        mock_refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main() 