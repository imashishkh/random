"""
Tests for the DAG model component.

This module contains unit tests for the DAG data model that manages the 
graph structure for agent visualization.
"""

import unittest
from unittest.mock import MagicMock

from src.visualization.dag.model import (
    DAGModel, 
    NodeData, 
    EdgeData, 
    AgentStatus, 
    Observable, 
    Observer
)


class TestObservable(unittest.TestCase):
    """Tests for the Observable base class."""
    
    def test_add_observer(self):
        """Test adding an observer."""
        observable = Observable()
        observer = MagicMock(spec=Observer)
        
        observable.add_observer(observer)
        
        self.assertIn(observer, observable.observers)
    
    def test_remove_observer(self):
        """Test removing an observer."""
        observable = Observable()
        observer = MagicMock(spec=Observer)
        
        observable.add_observer(observer)
        observable.remove_observer(observer)
        
        self.assertNotIn(observer, observable.observers)
    
    def test_notify_observers(self):
        """Test notifying observers."""
        observable = Observable()
        observer1 = MagicMock(spec=Observer)
        observer2 = MagicMock(spec=Observer)
        
        observable.add_observer(observer1)
        observable.add_observer(observer2)
        
        observable.notify_observers()
        
        observer1.update_from_model.assert_called_once_with(observable)
        observer2.update_from_model.assert_called_once_with(observable)


class TestDAGModel(unittest.TestCase):
    """Tests for the DAGModel class."""
    
    def setUp(self):
        """Set up the test environment."""
        self.model = DAGModel()
        
        # Create some test nodes
        self.node1 = NodeData(
            id="agent1", 
            name="Agent 1",
            node_type="agent",
            status=AgentStatus.RUNNING
        )
        self.node2 = NodeData(
            id="agent2",
            name="Agent 2",
            node_type="agent",
            status=AgentStatus.PENDING
        )
        self.node3 = NodeData(
            id="agent3",
            name="Agent 3",
            node_type="agent",
            status=AgentStatus.INITIALIZING
        )
        
        # Create some test edges
        self.edge1 = EdgeData(
            source_id="agent1",
            target_id="agent2",
            edge_type="dependency"
        )
        self.edge2 = EdgeData(
            source_id="agent2",
            target_id="agent3",
            edge_type="dependency"
        )
    
    def test_add_node(self):
        """Test adding a node to the model."""
        # Add a node
        self.model.add_node(self.node1)
        
        # Check that it was added correctly
        self.assertIn(self.node1.id, self.model.nodes)
        self.assertEqual(self.model.nodes[self.node1.id], self.node1)
        
        # Add a second node
        self.model.add_node(self.node2)
        
        # Check it was added and the first one is still there
        self.assertIn(self.node2.id, self.model.nodes)
        self.assertIn(self.node1.id, self.model.nodes)
        self.assertEqual(len(self.model.nodes), 2)
    
    def test_update_node(self):
        """Test updating a node in the model."""
        # Add a node
        self.model.add_node(self.node1)
        
        # Create an updated version with different status
        updated_node = NodeData(
            id="agent1",
            name="Agent 1",
            node_type="agent",
            status=AgentStatus.ERROR
        )
        
        # Update the node
        self.model.update_node(updated_node)
        
        # Check the update was applied
        self.assertEqual(self.model.nodes[self.node1.id].status, AgentStatus.ERROR)
    
    def test_remove_node(self):
        """Test removing a node from the model."""
        # Add nodes
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        
        # Remove one node
        self.model.remove_node(self.node1.id)
        
        # Check it was removed
        self.assertNotIn(self.node1.id, self.model.nodes)
        self.assertIn(self.node2.id, self.model.nodes)
        
        # Remove non-existent node (should not raise)
        self.model.remove_node("non_existent")
    
    def test_get_node(self):
        """Test getting a node from the model."""
        # Add a node
        self.model.add_node(self.node1)
        
        # Get the node
        node = self.model.get_node(self.node1.id)
        
        # Check it's the right node
        self.assertEqual(node, self.node1)
        
        # Get non-existent node
        node = self.model.get_node("non_existent")
        self.assertIsNone(node)
    
    def test_add_edge(self):
        """Test adding an edge to the model."""
        # Add nodes first
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        
        # Add edge
        self.model.add_edge(self.edge1)
        
        # Check it was added
        edge_key = (self.edge1.source_id, self.edge1.target_id)
        self.assertIn(edge_key, self.model.edges)
        self.assertEqual(self.model.edges[edge_key], self.edge1)
    
    def test_update_edge(self):
        """Test updating an edge in the model."""
        # Add nodes and edge
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_edge(self.edge1)
        
        # Create updated edge with different type
        updated_edge = EdgeData(
            source_id="agent1",
            target_id="agent2",
            edge_type="message"
        )
        
        # Update the edge
        self.model.update_edge(updated_edge)
        
        # Check the update was applied
        edge_key = (updated_edge.source_id, updated_edge.target_id)
        self.assertEqual(self.model.edges[edge_key].edge_type, "message")
    
    def test_remove_edge(self):
        """Test removing an edge from the model."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_node(self.node3)
        self.model.add_edge(self.edge1)
        self.model.add_edge(self.edge2)
        
        # Remove one edge
        self.model.remove_edge(self.edge1.source_id, self.edge1.target_id)
        
        # Check it was removed
        edge_key = (self.edge1.source_id, self.edge1.target_id)
        self.assertNotIn(edge_key, self.model.edges)
        
        # Other edge should still be present
        edge_key = (self.edge2.source_id, self.edge2.target_id)
        self.assertIn(edge_key, self.model.edges)
    
    def test_get_edge(self):
        """Test getting an edge from the model."""
        # Add nodes and edge
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_edge(self.edge1)
        
        # Get the edge
        edge = self.model.get_edge(self.edge1.source_id, self.edge1.target_id)
        
        # Check it's the right edge
        self.assertEqual(edge, self.edge1)
        
        # Get non-existent edge
        edge = self.model.get_edge("non_existent", "also_non_existent")
        self.assertIsNone(edge)
    
    def test_get_all_nodes(self):
        """Test getting all nodes from the model."""
        # Add nodes
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        
        # Get all nodes
        nodes = self.model.get_all_nodes()
        
        # Check we got the expected nodes
        self.assertEqual(len(nodes), 2)
        self.assertIn(self.node1, nodes)
        self.assertIn(self.node2, nodes)
    
    def test_get_all_edges(self):
        """Test getting all edges from the model."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_node(self.node3)
        self.model.add_edge(self.edge1)
        self.model.add_edge(self.edge2)
        
        # Get all edges
        edges = self.model.get_all_edges()
        
        # Check we got the expected edges
        self.assertEqual(len(edges), 2)
        self.assertIn(self.edge1, edges)
        self.assertIn(self.edge2, edges)
    
    def test_compute_layout(self):
        """Test computing the layout of the graph."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_node(self.node3)
        self.model.add_edge(self.edge1)
        self.model.add_edge(self.edge2)
        
        # Compute layout
        layout = self.model.compute_layout(width=800, height=600)
        
        # Check layout has entries for all nodes
        self.assertEqual(len(layout), 3)
        self.assertIn(self.node1.id, layout)
        self.assertIn(self.node2.id, layout)
        self.assertIn(self.node3.id, layout)
        
        # Check format of layout entries
        for node_id, position in layout.items():
            self.assertIn("x", position)
            self.assertIn("y", position)
            self.assertIsInstance(position["x"], (int, float))
            self.assertIsInstance(position["y"], (int, float))
            
            # Positions should be within the bounds
            self.assertGreaterEqual(position["x"], 0)
            self.assertLessEqual(position["x"], 800)
            self.assertGreaterEqual(position["y"], 0)
            self.assertLessEqual(position["y"], 600)
    
    def test_layout_empty_graph(self):
        """Test computing layout for an empty graph."""
        # Compute layout for empty graph
        layout = self.model.compute_layout(width=800, height=600)
        
        # Should be an empty dict
        self.assertEqual(layout, {})
    
    def test_get_outgoing_edges(self):
        """Test getting outgoing edges for a node."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_node(self.node3)
        self.model.add_edge(self.edge1)  # agent1 -> agent2
        self.model.add_edge(self.edge2)  # agent2 -> agent3
        
        # Get outgoing edges for node1
        edges = self.model.get_outgoing_edges(self.node1.id)
        
        # Should have one edge
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0], self.edge1)
        
        # Get outgoing edges for node2
        edges = self.model.get_outgoing_edges(self.node2.id)
        
        # Should have one edge
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0], self.edge2)
        
        # Get outgoing edges for node3
        edges = self.model.get_outgoing_edges(self.node3.id)
        
        # Should have no edges
        self.assertEqual(len(edges), 0)
    
    def test_get_incoming_edges(self):
        """Test getting incoming edges for a node."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_node(self.node3)
        self.model.add_edge(self.edge1)  # agent1 -> agent2
        self.model.add_edge(self.edge2)  # agent2 -> agent3
        
        # Get incoming edges for node1
        edges = self.model.get_incoming_edges(self.node1.id)
        
        # Should have no edges
        self.assertEqual(len(edges), 0)
        
        # Get incoming edges for node2
        edges = self.model.get_incoming_edges(self.node2.id)
        
        # Should have one edge
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0], self.edge1)
        
        # Get incoming edges for node3
        edges = self.model.get_incoming_edges(self.node3.id)
        
        # Should have one edge
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0], self.edge2)
    
    def test_edge_exists(self):
        """Test checking if an edge exists."""
        # Add nodes and edge
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_edge(self.edge1)
        
        # Check edge exists
        self.assertTrue(self.model.edge_exists(self.edge1.source_id, self.edge1.target_id))
        
        # Check non-existent edge
        self.assertFalse(self.model.edge_exists(self.node1.id, "non_existent"))
    
    def test_clear(self):
        """Test clearing the model."""
        # Add nodes and edges
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        self.model.add_edge(self.edge1)
        
        # Clear the model
        self.model.clear()
        
        # Check everything was cleared
        self.assertEqual(len(self.model.nodes), 0)
        self.assertEqual(len(self.model.edges), 0)
    
    def test_notification_on_change(self):
        """Test that observers are notified when the model changes."""
        # Create a mock observer
        observer = MagicMock(spec=Observer)
        self.model.add_observer(observer)
        
        # Add a node (should trigger notification)
        observer.update_from_model.reset_mock()
        self.model.add_node(self.node1)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Update a node (should trigger notification)
        observer.update_from_model.reset_mock()
        updated_node = NodeData(
            id="agent1",
            name="Updated Agent 1",
            node_type="agent",
            status=AgentStatus.ERROR
        )
        self.model.update_node(updated_node)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Remove a node (should trigger notification)
        observer.update_from_model.reset_mock()
        self.model.remove_node(self.node1.id)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Add an edge (should trigger notification)
        self.model.add_node(self.node1)
        self.model.add_node(self.node2)
        observer.update_from_model.reset_mock()
        self.model.add_edge(self.edge1)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Update an edge (should trigger notification)
        observer.update_from_model.reset_mock()
        updated_edge = EdgeData(
            source_id="agent1",
            target_id="agent2",
            edge_type="updated"
        )
        self.model.update_edge(updated_edge)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Remove an edge (should trigger notification)
        observer.update_from_model.reset_mock()
        self.model.remove_edge(self.edge1.source_id, self.edge1.target_id)
        observer.update_from_model.assert_called_once_with(self.model)
        
        # Clear the model (should trigger notification)
        observer.update_from_model.reset_mock()
        self.model.clear()
        observer.update_from_model.assert_called_once_with(self.model)


class TestNodeData(unittest.TestCase):
    """Tests for the NodeData class."""
    
    def test_create_node(self):
        """Test creating a node."""
        node = NodeData(
            id="test_id",
            name="Test Node",
            node_type="test",
            status=AgentStatus.RUNNING
        )
        
        self.assertEqual(node.id, "test_id")
        self.assertEqual(node.name, "Test Node")
        self.assertEqual(node.node_type, "test")
        self.assertEqual(node.status, AgentStatus.RUNNING)
    
    def test_node_equality(self):
        """Test node equality comparison."""
        node1 = NodeData(
            id="test_id",
            name="Test Node",
            node_type="test",
            status=AgentStatus.RUNNING
        )
        
        node2 = NodeData(
            id="test_id",
            name="Test Node",
            node_type="test",
            status=AgentStatus.RUNNING
        )
        
        node3 = NodeData(
            id="different_id",
            name="Different Node",
            node_type="different",
            status=AgentStatus.PENDING
        )
        
        self.assertEqual(node1, node2)
        self.assertNotEqual(node1, node3)
    
    def test_node_string_representation(self):
        """Test string representation of a node."""
        node = NodeData(
            id="test_id",
            name="Test Node",
            node_type="test",
            status=AgentStatus.RUNNING
        )
        
        string_repr = str(node)
        
        self.assertIn("test_id", string_repr)
        self.assertIn("Test Node", string_repr)
        self.assertIn("test", string_repr)
        self.assertIn("RUNNING", string_repr)


class TestEdgeData(unittest.TestCase):
    """Tests for the EdgeData class."""
    
    def test_create_edge(self):
        """Test creating an edge."""
        edge = EdgeData(
            source_id="source",
            target_id="target",
            edge_type="test"
        )
        
        self.assertEqual(edge.source_id, "source")
        self.assertEqual(edge.target_id, "target")
        self.assertEqual(edge.edge_type, "test")
    
    def test_edge_equality(self):
        """Test edge equality comparison."""
        edge1 = EdgeData(
            source_id="source",
            target_id="target",
            edge_type="test"
        )
        
        edge2 = EdgeData(
            source_id="source",
            target_id="target",
            edge_type="test"
        )
        
        edge3 = EdgeData(
            source_id="different",
            target_id="different_target",
            edge_type="different"
        )
        
        self.assertEqual(edge1, edge2)
        self.assertNotEqual(edge1, edge3)
    
    def test_edge_string_representation(self):
        """Test string representation of an edge."""
        edge = EdgeData(
            source_id="source",
            target_id="target",
            edge_type="test"
        )
        
        string_repr = str(edge)
        
        self.assertIn("source", string_repr)
        self.assertIn("target", string_repr)
        self.assertIn("test", string_repr)


class TestAgentStatus(unittest.TestCase):
    """Tests for the AgentStatus enum."""
    
    def test_agent_status_values(self):
        """Test that the AgentStatus enum has the expected values."""
        self.assertEqual(AgentStatus.INITIALIZING.value, "initializing")
        self.assertEqual(AgentStatus.PENDING.value, "pending")
        self.assertEqual(AgentStatus.RUNNING.value, "running")
        self.assertEqual(AgentStatus.PAUSED.value, "paused")
        self.assertEqual(AgentStatus.COMPLETED.value, "completed")
        self.assertEqual(AgentStatus.ERROR.value, "error")
        self.assertEqual(AgentStatus.TERMINATED.value, "terminated")


if __name__ == "__main__":
    unittest.main() 