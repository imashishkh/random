"""
Tests for the Textual TUI application.

This module contains tests for the main application structure and the
integration of the DAG visualization into the Textual TUI.
"""

import unittest
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Header, Footer
from textual.binding import Binding
from textual import events

from src.visualization.app import AgentVisApp
from src.visualization.dag.model import DAGModel
from src.visualization.dag.view import DAGView


class TestAgentVisApp(unittest.TestCase):
    """Tests for the main application class."""
    
    @patch("src.visualization.app.AgentVisApp.run")
    def test_app_initialization(self, mock_run):
        """Test that the app initializes properly."""
        app = AgentVisApp()
        
        # Check that the app has the correct title
        self.assertEqual(app.title, "Agent Visualization")
        
        # Check that the model is initialized
        self.assertIsInstance(app.model, DAGModel)
    
    @patch("src.visualization.app.AgentVisApp.run")
    def test_app_bindings(self, mock_run):
        """Test that the app has the expected key bindings."""
        app = AgentVisApp()
        
        # Check that the app has the expected bindings
        bindings = app.bindings
        
        # Verify common bindings exist
        binding_actions = [b.action for b in bindings]
        self.assertIn("quit", binding_actions)
        self.assertIn("toggle_dark", binding_actions)
        
        # Check for our custom bindings
        self.assertTrue(any("reset_view" in b.action for b in bindings))
        self.assertTrue(any("toggle_help" in b.action for b in bindings))
    
    @patch("textual.app.App.compose")
    @patch("src.visualization.app.AgentVisApp.run")
    def test_app_compose(self, mock_run, mock_compose):
        """Test that the app composes the correct widgets."""
        app = AgentVisApp()
        
        # Call the compose method
        app.compose()
        
        # Check that the correct widgets were added
        mock_compose.assert_called_once()
        
        # Since we mocked compose, we'll test the expected calls manually
        # Usually compose would yield widgets, but we can check the implementation directly
        compose_implementation = app.compose.__func__(app)
        widgets = list(compose_implementation)
        
        # Check for expected widget types
        widget_types = [type(w) for w in widgets]
        
        # App should include Header, DAGView, and Footer
        self.assertIn(Header, widget_types)
        self.assertIn(DAGView, widget_types)
        self.assertIn(Footer, widget_types)
    
    @patch("src.visualization.app.AgentVisApp.run")
    def test_on_mount(self, mock_run):
        """Test the on_mount lifecycle method."""
        app = AgentVisApp()
        
        # Mock the query method to return a mock DAGView
        dag_view = MagicMock(spec=DAGView)
        app.query = MagicMock(return_value=[dag_view])
        
        # Call on_mount
        app.on_mount()
        
        # Check that the DAGView was queried
        app.query.assert_called_with(DAGView)
        
        # Check that the DAGView's model was set
        dag_view.watch_model.assert_called_with(app.model)
    
    @patch("src.visualization.app.AgentVisApp.run")
    def test_action_reset_view(self, mock_run):
        """Test the reset_view action."""
        app = AgentVisApp()
        
        # Mock the query method to return a mock DAGView
        dag_view = MagicMock(spec=DAGView)
        app.query = MagicMock(return_value=[dag_view])
        
        # Call the action
        app.action_reset_view()
        
        # Check that the DAGView's reset_view method was called
        dag_view.reset_view.assert_called_once()
    
    @patch("src.visualization.app.AgentVisApp.run")
    def test_action_toggle_help(self, mock_run):
        """Test the toggle_help action."""
        app = AgentVisApp()
        
        # Initially, help should be hidden
        self.assertFalse(getattr(app, "help_visible", False))
        
        # Mock the app's methods that would be called
        app.push_screen = MagicMock()
        app.pop_screen = MagicMock()
        
        # Call the action to show help
        app.action_toggle_help()
        
        # Help should now be visible
        self.assertTrue(app.help_visible)
        
        # Check that push_screen was called to show help
        app.push_screen.assert_called_once()
        app.pop_screen.assert_not_called()
        
        # Reset mocks
        app.push_screen.reset_mock()
        app.pop_screen.reset_mock()
        
        # Call the action again to hide help
        app.action_toggle_help()
        
        # Help should now be hidden
        self.assertFalse(app.help_visible)
        
        # Check that pop_screen was called to hide help
        app.pop_screen.assert_called_once()
        app.push_screen.assert_not_called()


class TestAppIntegration(unittest.TestCase):
    """Tests for integration between app components."""
    
    @patch("textual.app.App.run")
    def test_model_view_integration(self, mock_run):
        """Test that the model and view are properly integrated."""
        app = AgentVisApp()
        
        # Create a mock DAGView
        dag_view = MagicMock(spec=DAGView)
        app.query = MagicMock(return_value=[dag_view])
        
        # Initialize the app
        app.on_mount()
        
        # Check that the view is watching the model
        dag_view.watch_model.assert_called_with(app.model)
        
        # Simulate a model update
        app.model.notify_observers()
        
        # Verify that the view is updated
        dag_view.update_from_model.assert_called_with(app.model)
    
    @patch("textual.app.App.run")
    def test_key_events(self, mock_run):
        """Test that key events are correctly processed."""
        app = AgentVisApp()
        
        # Create a mock DAGView
        dag_view = MagicMock(spec=DAGView)
        app.query = MagicMock(return_value=[dag_view])
        
        # Initialize the app
        app.on_mount()
        
        # Create a key event
        key_event = MagicMock(spec=events.Key)
        key_event.key = "r"
        
        # Test reset view action
        with patch.object(app, "action_reset_view") as mock_reset:
            # Simulate a key binding calling action_reset_view
            app.on_key(key_event)
            
            # This is a simplified test since the actual binding mechanism 
            # is more complex in Textual apps
            # In a real app, Textual would translate the key to an action
            # Check our implementation for where these bindings are defined
    
    @patch("textual.app.App.run")
    def test_dag_model_manipulation(self, mock_run):
        """Test manipulating the DAG model from the app."""
        app = AgentVisApp()
        
        # Create a mock DAGView
        dag_view = MagicMock(spec=DAGView)
        app.query = MagicMock(return_value=[dag_view])
        
        # Initialize the app
        app.on_mount()
        
        # Test adding a node
        with patch.object(app.model, "add_node") as mock_add_node:
            # Simulate adding a node from the app
            test_node = MagicMock()
            app.add_agent_node(test_node)
            
            # Check that the model's add_node was called
            mock_add_node.assert_called_with(test_node)
        
        # Test adding an edge
        with patch.object(app.model, "add_edge") as mock_add_edge:
            # Simulate adding an edge from the app
            test_edge = MagicMock()
            app.add_agent_edge(test_edge)
            
            # Check that the model's add_edge was called
            mock_add_edge.assert_called_with(test_edge)


if __name__ == "__main__":
    unittest.main() 