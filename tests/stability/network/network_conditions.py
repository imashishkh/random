"""
Network Condition Simulator

This module provides utilities for simulating various network conditions
during stability tests, such as latency, packet loss, and network partitions.
"""

import asyncio
import logging
import random
import socket
import subprocess
import time
from typing import Dict, List, Optional, Callable, Union, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import platform
import os
import sys
import atexit
import tempfile
import ipaddress
from contextlib import contextmanager

from ..config import NetworkConfig, NetworkCondition

# Configure logging
logger = logging.getLogger("network_conditions")


class NetworkSimulationError(Exception):
    """Error during network condition simulation."""
    pass


class NetworkConditionApplier:
    """
    Base class for applying network conditions.
    
    This is an abstract class that defines the interface for network condition
    appliers. Concrete implementations should handle platform-specific details.
    """
    
    def __init__(self):
        """Initialize the network condition applier."""
        self.active_conditions: Dict[str, NetworkConfig] = {}
        
    def apply_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply a network condition to a target.
        
        Args:
            target: Target identifier (e.g., IP address, hostname, interface)
            config: Network condition configuration
        
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        raise NotImplementedError("Subclasses must implement apply_condition")
        
    def remove_condition(self, target: str) -> None:
        """
        Remove a network condition from a target.
        
        Args:
            target: Target identifier
            
        Raises:
            NetworkSimulationError: If condition cannot be removed
        """
        raise NotImplementedError("Subclasses must implement remove_condition")
        
    def reset_all(self) -> None:
        """
        Reset all network conditions.
        
        Raises:
            NetworkSimulationError: If conditions cannot be reset
        """
        raise NotImplementedError("Subclasses must implement reset_all")
        
    def is_supported(self) -> bool:
        """
        Check if this applier is supported on the current platform.
        
        Returns:
            True if supported, False otherwise
        """
        raise NotImplementedError("Subclasses must implement is_supported")


class LinuxNetworkConditionApplier(NetworkConditionApplier):
    """
    Network condition applier for Linux platforms.
    
    Uses the 'tc' (Traffic Control) utility to simulate network conditions.
    Requires root privileges or sudo.
    """
    
    def __init__(self, use_sudo: bool = True):
        """
        Initialize the Linux network condition applier.
        
        Args:
            use_sudo: Whether to use sudo for executing commands
        """
        super().__init__()
        self.use_sudo = use_sudo
        self._tc_path = self._find_tc()
        
    def _find_tc(self) -> str:
        """
        Find the path to the tc command.
        
        Returns:
            Path to tc command
            
        Raises:
            NetworkSimulationError: If tc command is not found
        """
        try:
            result = subprocess.run(
                ["which", "tc"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            raise NetworkSimulationError("tc command not found, please install iproute2")
            
    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """
        Run a command with optional sudo.
        
        Args:
            command: Command to run
            
        Returns:
            Completed process
            
        Raises:
            NetworkSimulationError: If command fails
        """
        if self.use_sudo:
            command = ["sudo"] + command
            
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise NetworkSimulationError(
                f"Command failed: {' '.join(command)}\n"
                f"Error: {e.stderr}"
            )
            
    def apply_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply a network condition to a target interface.
        
        Args:
            target: Network interface name (e.g., 'eth0')
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        # Store the condition for later removal
        self.active_conditions[target] = config
        
        # Remove any existing conditions first
        try:
            self.remove_condition(target)
        except NetworkSimulationError:
            pass  # Ignore if there was no existing condition
            
        # Apply new condition
        try:
            # Add qdisc (queuing discipline)
            self._run_command([
                self._tc_path, "qdisc", "add", "dev", target,
                "root", "netem"
            ])
            
            # Apply specific conditions based on config
            self._apply_specific_condition(target, config)
            
            logger.info(f"Applied network condition to {target}: {config.condition.value}")
            
        except Exception as e:
            logger.error(f"Failed to apply network condition: {e}")
            raise NetworkSimulationError(f"Failed to apply network condition: {e}")
            
    def _apply_specific_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply specific network condition parameters.
        
        Args:
            target: Network interface name
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        netem_args = []
        
        # Apply latency
        if config.latency_ms > 0:
            netem_args.extend([
                "delay", str(config.latency_ms) + "ms"
            ])
            
            # Add latency variation if specified
            if config.latency_variance_ms > 0:
                netem_args.extend([
                    str(config.latency_variance_ms) + "ms",
                    "distribution", "normal"
                ])
                
        # Apply packet loss
        if config.packet_loss_percent > 0:
            netem_args.extend([
                "loss", f"{config.packet_loss_percent}%"
            ])
            
        # Apply bandwidth limit (requires tbf qdisc)
        if config.bandwidth_limit_kbps is not None and config.bandwidth_limit_kbps > 0:
            # For bandwidth limiting, we use a different approach with tbf
            self._run_command([
                self._tc_path, "qdisc", "change", "dev", target,
                "root", "tbf", "rate", f"{config.bandwidth_limit_kbps}kbit",
                "burst", "32kbit", "latency", "400ms"
            ])
            return
            
        # If we have netem parameters, apply them
        if netem_args:
            self._run_command([
                self._tc_path, "qdisc", "change", "dev", target,
                "root", "netem"
            ] + netem_args)
            
    def remove_condition(self, target: str) -> None:
        """
        Remove a network condition from a target interface.
        
        Args:
            target: Network interface name
            
        Raises:
            NetworkSimulationError: If condition cannot be removed
        """
        try:
            self._run_command([
                self._tc_path, "qdisc", "del", "dev", target, "root"
            ])
            
            if target in self.active_conditions:
                del self.active_conditions[target]
                
            logger.info(f"Removed network condition from {target}")
            
        except Exception as e:
            logger.error(f"Failed to remove network condition: {e}")
            raise NetworkSimulationError(f"Failed to remove network condition: {e}")
            
    def reset_all(self) -> None:
        """
        Reset all network conditions.
        
        Raises:
            NetworkSimulationError: If conditions cannot be reset
        """
        # Make a copy of active_conditions keys since we'll be modifying it
        targets = list(self.active_conditions.keys())
        
        for target in targets:
            try:
                self.remove_condition(target)
            except NetworkSimulationError as e:
                logger.warning(f"Failed to remove condition from {target}: {e}")
                
        logger.info("Reset all network conditions")
        
    def is_supported(self) -> bool:
        """
        Check if this applier is supported on the current platform.
        
        Returns:
            True if supported, False otherwise
        """
        return (
            platform.system() == "Linux" and
            os.path.exists(self._tc_path)
        )


class MacOSNetworkConditionApplier(NetworkConditionApplier):
    """
    Network condition applier for macOS platforms.
    
    Uses the Network Link Conditioner or 'dnctl' to simulate network conditions.
    Requires root privileges or sudo.
    """
    
    def __init__(self, use_sudo: bool = True):
        """
        Initialize the macOS network condition applier.
        
        Args:
            use_sudo: Whether to use sudo for executing commands
        """
        super().__init__()
        self.use_sudo = use_sudo
        self._pfctl_path = self._find_pfctl()
        self._dnctl_path = self._find_dnctl()
        self._pipe_path = tempfile.mktemp()
        self._rules_file = tempfile.mktemp()
        
        # Register cleanup at exit
        atexit.register(self.reset_all)
        
    def _find_pfctl(self) -> str:
        """
        Find the path to the pfctl command.
        
        Returns:
            Path to pfctl command
            
        Raises:
            NetworkSimulationError: If pfctl command is not found
        """
        try:
            result = subprocess.run(
                ["which", "pfctl"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            raise NetworkSimulationError("pfctl command not found")
            
    def _find_dnctl(self) -> str:
        """
        Find the path to the dnctl command.
        
        Returns:
            Path to dnctl command
            
        Raises:
            NetworkSimulationError: If dnctl command is not found
        """
        try:
            result = subprocess.run(
                ["which", "dnctl"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            # Try legacy dummynet command for older macOS versions
            try:
                result = subprocess.run(
                    ["which", "dummynet"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.stdout.strip()
            except subprocess.CalledProcessError:
                raise NetworkSimulationError("dnctl command not found")
                
    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """
        Run a command with optional sudo.
        
        Args:
            command: Command to run
            
        Returns:
            Completed process
            
        Raises:
            NetworkSimulationError: If command fails
        """
        if self.use_sudo:
            command = ["sudo"] + command
            
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise NetworkSimulationError(
                f"Command failed: {' '.join(command)}\n"
                f"Error: {e.stderr}"
            )
            
    def apply_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply a network condition to a target interface or IP.
        
        Args:
            target: Network interface name or IP address
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        # Store the condition for later removal
        self.active_conditions[target] = config
        
        # Create pipe
        with open(self._rules_file, 'w') as f:
            f.write(f"""
                dummynet-anchor "stability_test"
                anchor "stability_test"
            """)
            
        self._run_command([
            self._pfctl_path, "-f", self._rules_file
        ])
        
        # Create pipe for traffic
        try:
            self._run_command([
                self._dnctl_path, "pipe", "1", "config"
            ])
            
            # Apply specific conditions based on config
            self._apply_specific_condition("1", config)
            
            # Set up routing rule
            if self._is_ip_address(target):
                # Target is an IP address
                with open(self._rules_file, 'w') as f:
                    f.write(f"""
                        dummynet-anchor "stability_test"
                        anchor "stability_test" {{
                            dummynet in quick proto tcp from any to {target} pipe 1
                            dummynet out quick proto tcp from {target} to any pipe 1
                        }}
                    """)
            else:
                # Target is an interface
                with open(self._rules_file, 'w') as f:
                    f.write(f"""
                        dummynet-anchor "stability_test"
                        anchor "stability_test" {{
                            dummynet in quick proto tcp on {target} pipe 1
                            dummynet out quick proto tcp on {target} pipe 1
                        }}
                    """)
                    
            self._run_command([
                self._pfctl_path, "-a", "stability_test", "-f", self._rules_file
            ])
            
            logger.info(f"Applied network condition to {target}: {config.condition.value}")
            
        except Exception as e:
            logger.error(f"Failed to apply network condition: {e}")
            raise NetworkSimulationError(f"Failed to apply network condition: {e}")
            
    def _is_ip_address(self, target: str) -> bool:
        """
        Check if target is an IP address.
        
        Args:
            target: Target identifier
            
        Returns:
            True if target is an IP address, False otherwise
        """
        try:
            ipaddress.ip_address(target)
            return True
        except ValueError:
            return False
            
    def _apply_specific_condition(self, pipe_id: str, config: NetworkConfig) -> None:
        """
        Apply specific network condition parameters.
        
        Args:
            pipe_id: Pipe identifier
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        cmd = [self._dnctl_path, "pipe", pipe_id, "config"]
        
        # Apply latency
        if config.latency_ms > 0:
            cmd.extend(["delay", str(config.latency_ms)])
            
        # Apply packet loss
        if config.packet_loss_percent > 0:
            cmd.extend(["plr", str(config.packet_loss_percent / 100.0)])
            
        # Apply bandwidth limit
        if config.bandwidth_limit_kbps is not None and config.bandwidth_limit_kbps > 0:
            cmd.extend(["bw", f"{config.bandwidth_limit_kbps}Kbit/s"])
            
        self._run_command(cmd)
            
    def remove_condition(self, target: str) -> None:
        """
        Remove a network condition from a target.
        
        Args:
            target: Target identifier
            
        Raises:
            NetworkSimulationError: If condition cannot be removed
        """
        try:
            # Remove pf rule
            self._run_command([
                self._pfctl_path, "-a", "stability_test", "-F", "all"
            ])
            
            # Remove pipe
            self._run_command([
                self._dnctl_path, "pipe", "1", "delete"
            ])
            
            if target in self.active_conditions:
                del self.active_conditions[target]
                
            logger.info(f"Removed network condition from {target}")
            
        except Exception as e:
            logger.error(f"Failed to remove network condition: {e}")
            raise NetworkSimulationError(f"Failed to remove network condition: {e}")
            
    def reset_all(self) -> None:
        """
        Reset all network conditions.
        
        Raises:
            NetworkSimulationError: If conditions cannot be reset
        """
        try:
            # Remove pf rule
            self._run_command([
                self._pfctl_path, "-a", "stability_test", "-F", "all"
            ])
            
            # Remove all pipes
            self._run_command([
                self._dnctl_path, "flush"
            ])
            
            # Clean up temporary files
            if os.path.exists(self._rules_file):
                os.unlink(self._rules_file)
                
            self.active_conditions.clear()
            logger.info("Reset all network conditions")
            
        except Exception as e:
            logger.error(f"Failed to reset network conditions: {e}")
            
    def is_supported(self) -> bool:
        """
        Check if this applier is supported on the current platform.
        
        Returns:
            True if supported, False otherwise
        """
        return (
            platform.system() == "Darwin" and
            os.path.exists(self._pfctl_path) and
            os.path.exists(self._dnctl_path)
        )


class WindowsNetworkConditionApplier(NetworkConditionApplier):
    """
    Network condition applier for Windows platforms.
    
    Uses Network Emulator for Windows Toolkit (NewT) if available,
    or falls back to other methods.
    """
    
    def __init__(self):
        """Initialize the Windows network condition applier."""
        super().__init__()
        # Windows implementation would go here
        # For now, this is a placeholder
        
    def apply_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply a network condition to a target.
        
        Args:
            target: Target identifier
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        raise NetworkSimulationError("Windows network condition simulation not implemented")
        
    def remove_condition(self, target: str) -> None:
        """
        Remove a network condition from a target.
        
        Args:
            target: Target identifier
            
        Raises:
            NetworkSimulationError: If condition cannot be removed
        """
        raise NetworkSimulationError("Windows network condition simulation not implemented")
        
    def reset_all(self) -> None:
        """
        Reset all network conditions.
        
        Raises:
            NetworkSimulationError: If conditions cannot be reset
        """
        raise NetworkSimulationError("Windows network condition simulation not implemented")
        
    def is_supported(self) -> bool:
        """
        Check if this applier is supported on the current platform.
        
        Returns:
            True if supported, False otherwise
        """
        return platform.system() == "Windows"


class NetworkSimulator:
    """
    High-level interface for simulating network conditions.
    
    This class automatically selects the appropriate implementation based on
    the current platform.
    """
    
    def __init__(self):
        """Initialize the network simulator."""
        self.appliers = [
            LinuxNetworkConditionApplier(),
            MacOSNetworkConditionApplier(),
            WindowsNetworkConditionApplier()
        ]
        
        # Find the first supported applier
        self.applier = next(
            (applier for applier in self.appliers if applier.is_supported()),
            None
        )
        
        if self.applier is None:
            logger.warning("No supported network condition applier found")
            
    def is_supported(self) -> bool:
        """
        Check if network simulation is supported on this platform.
        
        Returns:
            True if supported, False otherwise
        """
        return self.applier is not None
        
    def apply_condition(self, target: str, config: NetworkConfig) -> None:
        """
        Apply a network condition to a target.
        
        Args:
            target: Target identifier (e.g., IP address, hostname, interface)
            config: Network condition configuration
            
        Raises:
            NetworkSimulationError: If condition cannot be applied
        """
        if not self.is_supported():
            raise NetworkSimulationError("Network simulation not supported on this platform")
            
        self.applier.apply_condition(target, config)
        
    def remove_condition(self, target: str) -> None:
        """
        Remove a network condition from a target.
        
        Args:
            target: Target identifier
            
        Raises:
            NetworkSimulationError: If condition cannot be removed
        """
        if not self.is_supported():
            raise NetworkSimulationError("Network simulation not supported on this platform")
            
        self.applier.remove_condition(target)
        
    def reset_all(self) -> None:
        """
        Reset all network conditions.
        
        Raises:
            NetworkSimulationError: If conditions cannot be reset
        """
        if not self.is_supported():
            raise NetworkSimulationError("Network simulation not supported on this platform")
            
        self.applier.reset_all()
        
    @contextmanager
    def temporary_condition(self, target: str, config: NetworkConfig):
        """
        Apply a network condition temporarily.
        
        Args:
            target: Target identifier
            config: Network condition configuration
            
        Yields:
            None
            
        Raises:
            NetworkSimulationError: If condition cannot be applied or removed
        """
        try:
            self.apply_condition(target, config)
            yield
        finally:
            self.remove_condition(target)


# Global network simulator instance
_network_simulator: Optional[NetworkSimulator] = None


def get_network_simulator() -> NetworkSimulator:
    """
    Get the global network simulator instance.
    
    If no simulator has been initialized, a default one is created.
    
    Returns:
        The global NetworkSimulator instance
    """
    global _network_simulator
    
    if _network_simulator is None:
        _network_simulator = NetworkSimulator()
        
    return _network_simulator


def set_network_simulator(simulator: NetworkSimulator) -> None:
    """
    Set the global network simulator instance.
    
    Args:
        simulator: NetworkSimulator instance to use
    """
    global _network_simulator
    _network_simulator = simulator 