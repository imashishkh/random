"""
Task Group Management for Agent Orchestration

This module provides the TaskGroup class for managing groups of related agents
that share a common lifecycle and dependencies.
"""

import asyncio
import logging
import time
from typing import Dict, List, Set, Optional, Any, Union, Callable
from enum import Enum

from .base_agent import BaseAgent
from ...utils.logging.logger import get_logger
from .process_manager import ProcessManager

logger = get_logger()


class TaskGroupStatus(Enum):
    """Status states for a TaskGroup."""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskGroup:
    """
    Manages a group of related agents that share a common lifecycle.
    
    TaskGroups provide a way to organize agents into logical groups,
    track their collective status, and manage dependencies between groups.
    """
    
    def __init__(
        self,
        group_id: str,
        name: str,
        description: str = "",
        process_manager: ProcessManager = None,
        parent_group: Optional['TaskGroup'] = None,
        depends_on: List[str] = None
    ):
        """
        Initialize a new TaskGroup.
        
        Args:
            group_id: Unique identifier for this task group
            name: Human-readable name for the group
            description: Detailed description of the group's purpose
            process_manager: ProcessManager instance to use for agent management
            parent_group: Parent TaskGroup if this is a subgroup
            depends_on: List of TaskGroup IDs this group depends on
        """
        self.group_id = group_id
        self.name = name
        self.description = description
        self.process_manager = process_manager
        self.parent_group = parent_group
        self.depends_on = depends_on or []
        
        # Agent tracking
        self.agent_ids: Set[str] = set()
        self.agent_configs: List[Dict[str, Any]] = []
        
        # Subgroups
        self.subgroups: Dict[str, 'TaskGroup'] = {}
        
        # Status
        self.status = TaskGroupStatus.PENDING
        self.status_history: List[Dict[str, Any]] = []
        self._record_status_change(TaskGroupStatus.PENDING, "Group initialized")
        
        # Lifecycle management
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._completion_callbacks: List[Callable[['TaskGroup'], None]] = []
        self._completion_event = asyncio.Event()
        
        logger.info(f"TaskGroup '{name}' (ID: {group_id}) created")
    
    def _record_status_change(self, status: TaskGroupStatus, reason: str) -> None:
        """
        Record a status change in the group's history.
        
        Args:
            status: New status
            reason: Reason for the status change
        """
        self.status = status
        timestamp = time.time()
        
        entry = {
            "timestamp": timestamp,
            "status": status.value,
            "reason": reason
        }
        
        self.status_history.append(entry)
        logger.info(f"TaskGroup '{self.name}' status changed to {status.value}: {reason}")
    
    def add_agent_config(self, agent_config: Dict[str, Any]) -> None:
        """
        Add an agent configuration to be spawned as part of this group.
        
        Args:
            agent_config: Agent configuration dictionary with 'agent_type'
                         and other parameters
        """
        if "agent_type" not in agent_config:
            raise ValueError("Agent configuration must include 'agent_type'")
        
        self.agent_configs.append(agent_config.copy())
        logger.debug(f"Added agent config of type {agent_config['agent_type']} to TaskGroup '{self.name}'")
    
    def add_multiple_agent_configs(self, agent_configs: List[Dict[str, Any]]) -> None:
        """
        Add multiple agent configurations to be spawned as part of this group.
        
        Args:
            agent_configs: List of agent configuration dictionaries
        """
        for config in agent_configs:
            self.add_agent_config(config)
    
    def register_agent(self, agent_id: str) -> None:
        """
        Register an already-spawned agent with this task group.
        
        Args:
            agent_id: ID of the agent to register
        """
        self.agent_ids.add(agent_id)
        logger.debug(f"Registered agent {agent_id} with TaskGroup '{self.name}'")
    
    def register_multiple_agents(self, agent_ids: List[str]) -> None:
        """
        Register multiple already-spawned agents with this task group.
        
        Args:
            agent_ids: List of agent IDs to register
        """
        for agent_id in agent_ids:
            self.register_agent(agent_id)
    
    def add_subgroup(self, group: 'TaskGroup') -> None:
        """
        Add a subgroup to this task group.
        
        Args:
            group: The TaskGroup to add as a subgroup
        """
        if group.group_id in self.subgroups:
            logger.warning(f"TaskGroup '{group.name}' already exists as a subgroup")
            return
        
        group.parent_group = self
        self.subgroups[group.group_id] = group
        logger.debug(f"Added TaskGroup '{group.name}' as subgroup to '{self.name}'")
    
    def add_completion_callback(self, callback: Callable[['TaskGroup'], None]) -> None:
        """
        Add a callback to be executed when the task group completes.
        
        Args:
            callback: Function to call when the group completes
        """
        self._completion_callbacks.append(callback)
    
    async def wait_for_completion(self) -> None:
        """Wait for this task group to complete (whether success, failure, or cancellation)."""
        await self._completion_event.wait()
    
    def is_complete(self) -> bool:
        """Check if the task group has completed (succeeded, failed, or cancelled)."""
        return self.status in [
            TaskGroupStatus.COMPLETED, 
            TaskGroupStatus.FAILED,
            TaskGroupStatus.CANCELLED
        ]
    
    async def start(self) -> List[str]:
        """
        Start all agents in this task group.
        
        Returns:
            List of agent IDs that were started
            
        Raises:
            RuntimeError: If the task group is already running or has completed
            ValueError: If no ProcessManager is available
        """
        # Check if the group can be started
        if self.status != TaskGroupStatus.PENDING:
            raise RuntimeError(
                f"Cannot start TaskGroup '{self.name}' with status {self.status.value}"
            )
        
        # Ensure we have a ProcessManager
        if not self.process_manager:
            raise ValueError(
                f"Cannot start TaskGroup '{self.name}' without a ProcessManager"
            )
        
        # Mark as starting
        self._record_status_change(TaskGroupStatus.STARTING, "Starting agents")
        self._start_time = time.time()
        
        # Start all subgroups first
        subgroup_failures = []
        for subgroup in self.subgroups.values():
            try:
                await subgroup.start()
            except Exception as e:
                logger.error(f"Failed to start subgroup '{subgroup.name}': {str(e)}")
                subgroup_failures.append(subgroup.name)
        
        if subgroup_failures:
            self._record_status_change(
                TaskGroupStatus.FAILED, 
                f"Failed to start subgroups: {', '.join(subgroup_failures)}"
            )
            self._end_time = time.time()
            self._completion_event.set()
            for callback in self._completion_callbacks:
                try:
                    callback(self)
                except Exception as e:
                    logger.error(f"Error in completion callback: {str(e)}")
            return []
        
        # Start all configured agents
        agent_ids = []
        try:
            if self.agent_configs:
                # Use the more efficient spawn_multiple_agents method
                new_agent_ids = await self.process_manager.spawn_multiple_agents(
                    self.agent_configs
                )
                agent_ids.extend(new_agent_ids)
                self.agent_ids.update(new_agent_ids)
            
            self._record_status_change(
                TaskGroupStatus.RUNNING, 
                f"Started {len(agent_ids)} agents"
            )
            
            # Start monitoring task group completion
            asyncio.create_task(self._monitor_completion())
            
            return agent_ids
            
        except Exception as e:
            logger.error(f"Failed to start TaskGroup '{self.name}': {str(e)}")
            self._record_status_change(
                TaskGroupStatus.FAILED, 
                f"Start failed: {str(e)}"
            )
            self._end_time = time.time()
            self._completion_event.set()
            for callback in self._completion_callbacks:
                try:
                    callback(self)
                except Exception as e:
                    logger.error(f"Error in completion callback: {str(e)}")
            return []
    
    async def _monitor_completion(self) -> None:
        """Monitor the completion status of all agents in the group."""
        while self.status == TaskGroupStatus.RUNNING:
            # Get metrics for all agents in the group
            all_completed = True
            any_failed = False
            
            for agent_id in self.agent_ids:
                metrics = self.process_manager.get_agent_metrics(agent_id)
                status = metrics.get("status", "unknown")
                
                if status not in ["completed", "failed", "cancelled"]:
                    all_completed = False
                
                if status == "failed":
                    any_failed = True
            
            # Also check subgroups
            for subgroup in self.subgroups.values():
                if not subgroup.is_complete():
                    all_completed = False
                
                if subgroup.status == TaskGroupStatus.FAILED:
                    any_failed = True
            
            # If all agents have completed, mark the group as complete
            if all_completed:
                if any_failed:
                    self._record_status_change(
                        TaskGroupStatus.FAILED, 
                        "One or more agents failed"
                    )
                else:
                    self._record_status_change(
                        TaskGroupStatus.COMPLETED, 
                        "All agents completed successfully"
                    )
                
                self._end_time = time.time()
                self._completion_event.set()
                
                # Execute completion callbacks
                for callback in self._completion_callbacks:
                    try:
                        callback(self)
                    except Exception as e:
                        logger.error(f"Error in completion callback: {str(e)}")
                
                return
            
            # Wait before checking again
            await asyncio.sleep(1.0)
    
    async def cancel(self, reason: str = "Manually cancelled") -> None:
        """
        Cancel all agents in this task group.
        
        Args:
            reason: Reason for cancellation
        """
        if self.is_complete():
            logger.warning(f"TaskGroup '{self.name}' already completed, cannot cancel")
            return
        
        logger.info(f"Cancelling TaskGroup '{self.name}': {reason}")
        
        # Cancel all subgroups first
        for subgroup in self.subgroups.values():
            await subgroup.cancel(reason=f"Parent group cancelled: {reason}")
        
        # Cancel all agents in this group
        for agent_id in self.agent_ids:
            if agent_id in self.process_manager.active_agents:
                # The agent's task will be cancelled via the shutdown coordinator
                # when we initiate a shutdown for this specific agent
                logger.info(f"Cancelling agent {agent_id}")
                # In a real implementation, we'd have a method to cancel individual agents
                # For now, assume process_manager has such a method
                # await self.process_manager.cancel_agent(agent_id)
        
        self._record_status_change(TaskGroupStatus.CANCELLED, reason)
        self._end_time = time.time()
        self._completion_event.set()
        
        # Execute completion callbacks
        for callback in self._completion_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in completion callback: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get metrics for this task group.
        
        Returns:
            Dictionary with task group metrics
        """
        # Calculate duration if applicable
        duration = None
        if self._start_time:
            if self._end_time:
                duration = self._end_time - self._start_time
            else:
                duration = time.time() - self._start_time
        
        # Build metrics dictionary
        metrics = {
            "group_id": self.group_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "start_time": self._start_time,
            "end_time": self._end_time,
            "duration": duration,
            "agent_count": len(self.agent_ids),
            "subgroup_count": len(self.subgroups),
            "status_history": self.status_history,
            "depends_on": self.depends_on
        }
        
        # Include agent metrics if available
        if self.process_manager:
            agent_metrics = {}
            for agent_id in self.agent_ids:
                agent_metrics[agent_id] = self.process_manager.get_agent_metrics(agent_id)
            metrics["agents"] = agent_metrics
        
        # Include subgroup metrics
        subgroup_metrics = {}
        for group_id, group in self.subgroups.items():
            subgroup_metrics[group_id] = group.get_metrics()
        metrics["subgroups"] = subgroup_metrics
        
        return metrics


class TaskGroupManager:
    """
    Manages multiple task groups and their dependencies.
    
    This class provides a high-level interface for creating, starting,
    and monitoring task groups, ensuring dependencies are respected.
    """
    
    def __init__(self, process_manager: ProcessManager):
        """
        Initialize a new TaskGroupManager.
        
        Args:
            process_manager: ProcessManager instance to use for agent management
        """
        self.process_manager = process_manager
        self.task_groups: Dict[str, TaskGroup] = {}
        self.dependency_graph: Dict[str, Set[str]] = {}  # group_id -> set of groups that depend on it
        
        logger.info("TaskGroupManager initialized")
    
    def create_task_group(
        self,
        group_id: str,
        name: str,
        description: str = "",
        depends_on: List[str] = None,
        parent_id: Optional[str] = None
    ) -> TaskGroup:
        """
        Create a new task group.
        
        Args:
            group_id: Unique identifier for the task group
            name: Human-readable name for the group
            description: Detailed description of the group's purpose
            depends_on: List of task group IDs this group depends on
            parent_id: ID of the parent task group, if this is a subgroup
            
        Returns:
            The created TaskGroup
            
        Raises:
            ValueError: If a group with the given ID already exists or if
                       a dependency or parent group doesn't exist
        """
        # Check if ID already exists
        if group_id in self.task_groups:
            raise ValueError(f"TaskGroup with ID '{group_id}' already exists")
        
        # Validate dependencies
        dependencies = []
        if depends_on:
            for dep_id in depends_on:
                if dep_id not in self.task_groups:
                    raise ValueError(f"Dependency TaskGroup '{dep_id}' does not exist")
                dependencies.append(dep_id)
        
        # Get parent group if specified
        parent_group = None
        if parent_id:
            if parent_id not in self.task_groups:
                raise ValueError(f"Parent TaskGroup '{parent_id}' does not exist")
            parent_group = self.task_groups[parent_id]
        
        # Create the task group
        task_group = TaskGroup(
            group_id=group_id,
            name=name,
            description=description,
            process_manager=self.process_manager,
            parent_group=parent_group,
            depends_on=dependencies
        )
        
        # Register the group
        self.task_groups[group_id] = task_group
        
        # Update dependency graph
        for dep_id in dependencies:
            if dep_id not in self.dependency_graph:
                self.dependency_graph[dep_id] = set()
            self.dependency_graph[dep_id].add(group_id)
        
        # Add as subgroup if it has a parent
        if parent_group:
            parent_group.add_subgroup(task_group)
        
        logger.info(f"Created TaskGroup '{name}' with ID '{group_id}'")
        return task_group
    
    async def start_task_group(self, group_id: str) -> None:
        """
        Start a task group and all its dependencies.
        
        Args:
            group_id: ID of the task group to start
            
        Raises:
            ValueError: If the group does not exist
            RuntimeError: If a dependency cannot be started
        """
        if group_id not in self.task_groups:
            raise ValueError(f"TaskGroup '{group_id}' does not exist")
        
        task_group = self.task_groups[group_id]
        
        # Start dependencies first
        for dep_id in task_group.depends_on:
            dep_group = self.task_groups[dep_id]
            
            if dep_group.status == TaskGroupStatus.PENDING:
                await self.start_task_group(dep_id)
            
            elif dep_group.status in [TaskGroupStatus.FAILED, TaskGroupStatus.CANCELLED]:
                raise RuntimeError(
                    f"Cannot start TaskGroup '{group_id}' - dependency '{dep_id}' "
                    f"has status {dep_group.status.value}"
                )
        
        # Start the task group
        await task_group.start()
    
    async def start_all_independent_groups(self) -> List[str]:
        """
        Start all task groups that have no dependencies.
        
        Returns:
            List of group IDs that were started
        """
        started_groups = []
        
        # Find all groups with no dependencies
        for group_id, task_group in self.task_groups.items():
            if not task_group.depends_on and task_group.status == TaskGroupStatus.PENDING:
                await task_group.start()
                started_groups.append(group_id)
        
        return started_groups
    
    async def wait_for_all_groups(self) -> None:
        """Wait for all task groups to complete."""
        tasks = []
        for task_group in self.task_groups.values():
            tasks.append(task_group.wait_for_completion())
        
        if tasks:
            await asyncio.gather(*tasks)
    
    async def wait_for_group(self, group_id: str) -> None:
        """
        Wait for a specific task group to complete.
        
        Args:
            group_id: ID of the task group to wait for
            
        Raises:
            ValueError: If the group does not exist
        """
        if group_id not in self.task_groups:
            raise ValueError(f"TaskGroup '{group_id}' does not exist")
        
        await self.task_groups[group_id].wait_for_completion()
    
    async def cancel_group(self, group_id: str, reason: str = "Manually cancelled") -> None:
        """
        Cancel a task group and all dependent groups.
        
        Args:
            group_id: ID of the task group to cancel
            reason: Reason for cancellation
            
        Raises:
            ValueError: If the group does not exist
        """
        if group_id not in self.task_groups:
            raise ValueError(f"TaskGroup '{group_id}' does not exist")
        
        # First, cancel all groups that depend on this one
        if group_id in self.dependency_graph:
            for dependent_id in self.dependency_graph[group_id]:
                await self.cancel_group(
                    dependent_id, 
                    reason=f"Dependency '{group_id}' was cancelled"
                )
        
        # Then cancel the group itself
        await self.task_groups[group_id].cancel(reason)
    
    async def cancel_all_groups(self, reason: str = "Shutdown requested") -> None:
        """
        Cancel all task groups.
        
        Args:
            reason: Reason for cancellation
        """
        # Cancel only root groups first (groups with no parent)
        # Subgroups will be cancelled by their parents
        root_groups = [
            group for group in self.task_groups.values()
            if not group.parent_group
        ]
        
        for group in root_groups:
            await group.cancel(reason)
    
    def get_task_group(self, group_id: str) -> Optional[TaskGroup]:
        """
        Get a specific task group.
        
        Args:
            group_id: ID of the task group to get
            
        Returns:
            The TaskGroup if found, None otherwise
        """
        return self.task_groups.get(group_id)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get metrics for all task groups.
        
        Returns:
            Dictionary with metrics for all task groups
        """
        metrics = {
            "group_count": len(self.task_groups),
            "groups": {}
        }
        
        # Add metrics for each root group
        root_groups = [
            group for group in self.task_groups.values()
            if not group.parent_group
        ]
        
        for group in root_groups:
            metrics["groups"][group.group_id] = group.get_metrics()
        
        return metrics 