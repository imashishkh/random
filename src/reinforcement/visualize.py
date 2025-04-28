"""
Visualization utilities for reinforcement learning.

This module provides visualizers for:
1. Reward tracking and visualization
2. Experience replay buffer statistics
"""

import numpy as np
import matplotlib.pyplot as plt
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Union
import time
from collections import deque, defaultdict
import matplotlib.colors as mcolors
from matplotlib.figure import Figure


class RewardVisualizer:
    """
    Visualizer for tracking and plotting rewards over time.
    
    Features:
    - Tracks overall rewards and component rewards
    - Plots reward curves over episodes and steps
    - Generates histograms and statistics
    - Supports rolling averages
    """
    
    def __init__(
        self,
        save_dir: str = "plots",
        components: List[str] = None,
        rolling_window: int = 100,
        max_history: int = 10000
    ):
        """
        Initialize the reward visualizer.
        
        Args:
            save_dir: Directory to save plots
            components: List of reward component names to track
            rolling_window: Window size for rolling average calculations
            max_history: Maximum number of steps to keep in history
        """
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.components = components or []
        self.rolling_window = rolling_window
        self.max_history = max_history
        
        # Tracking variables
        self.rewards = deque(maxlen=max_history)
        self.episode_rewards = []
        self.step_counter = 0
        self.episode_counter = 0
        self.episode_steps = []
        
        # Component tracking
        self.component_rewards = {comp: deque(maxlen=max_history) for comp in self.components}
        self.episode_component_rewards = {comp: [] for comp in self.components}
        
        # Color mapping for consistent colors
        self.colors = self._get_color_map(self.components)
    
    def _get_color_map(self, keys: List[str]) -> Dict[str, str]:
        """
        Create a consistent color mapping for components.
        
        Args:
            keys: List of component names
            
        Returns:
            Dictionary mapping component names to colors
        """
        base_colors = list(mcolors.TABLEAU_COLORS.values())
        return {
            key: base_colors[i % len(base_colors)]
            for i, key in enumerate(keys)
        }
    
    def add_reward(
        self,
        reward: float,
        components: Dict[str, float] = None,
        done: bool = False,
        episode_idx: Optional[int] = None
    ) -> None:
        """
        Add a reward observation.
        
        Args:
            reward: The overall reward value
            components: Dictionary of component rewards
            done: Whether this is the final step in an episode
            episode_idx: Episode index if known
        """
        self.rewards.append(reward)
        self.step_counter += 1
        
        # Track component rewards
        if components:
            for comp, value in components.items():
                if comp in self.component_rewards:
                    self.component_rewards[comp].append(value)
        
        # Handle episode completion
        if done:
            episode_reward = sum(list(self.rewards)[-self.step_counter:])
            self.episode_rewards.append(episode_reward)
            self.episode_steps.append(self.step_counter)
            
            # Track component rewards for this episode
            for comp in self.components:
                if comp in self.component_rewards:
                    episode_component = sum(list(self.component_rewards[comp])[-self.step_counter:])
                    self.episode_component_rewards[comp].append(episode_component)
            
            # Update episode counter
            if episode_idx is not None:
                self.episode_counter = episode_idx + 1
            else:
                self.episode_counter += 1
            
            # Reset step counter
            self.step_counter = 0
    
    def get_statistics(self) -> Dict[str, float]:
        """
        Get summary statistics of collected rewards.
        
        Returns:
            Dictionary with reward statistics
        """
        rewards_array = np.array(self.rewards)
        
        stats = {
            "mean": float(np.mean(rewards_array)),
            "std": float(np.std(rewards_array)),
            "min": float(np.min(rewards_array)),
            "max": float(np.max(rewards_array)),
            "median": float(np.median(rewards_array)),
            "last_episode_reward": float(self.episode_rewards[-1]) if self.episode_rewards else 0.0,
            "episode_count": self.episode_counter,
            "total_steps": len(self.rewards)
        }
        
        # Calculate rolling average if enough data
        if len(self.rewards) >= self.rolling_window:
            rolling_mean = np.mean(list(self.rewards)[-self.rolling_window:])
            stats["rolling_mean"] = float(rolling_mean)
        
        return stats
    
    def plot_rewards(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot reward curve over time.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        rewards_array = np.array(self.rewards)
        
        # Plot individual rewards
        ax.plot(rewards_array, alpha=0.3, label="Rewards", color="blue")
        
        # Plot rolling average if enough data
        if len(rewards_array) >= self.rolling_window:
            rolling_mean = np.convolve(
                rewards_array, 
                np.ones(self.rolling_window) / self.rolling_window, 
                mode="valid"
            )
            ax.plot(
                np.arange(self.rolling_window - 1, len(rewards_array)), 
                rolling_mean, 
                label=f"Rolling Avg ({self.rolling_window})", 
                color="orange",
                linewidth=2
            )
        
        ax.set_title("Reward over Time")
        ax.set_xlabel("Steps")
        ax.set_ylabel("Reward")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add statistics as text box
        stats = self.get_statistics()
        stats_text = "\n".join([
            f"Mean: {stats['mean']:.4f}",
            f"Std: {stats['std']:.4f}",
            f"Min: {stats['min']:.4f}",
            f"Max: {stats['max']:.4f}",
            f"Episodes: {stats['episode_count']}"
        ])
        ax.text(
            0.02, 0.02, stats_text,
            transform=ax.transAxes,
            bbox=dict(facecolor="white", alpha=0.7),
            verticalalignment="bottom"
        )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"rewards_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
        
        return fig
    
    def plot_components(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot component rewards over time.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if not self.components:
            return None
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Plot each component
        for comp in self.components:
            if comp in self.component_rewards and len(self.component_rewards[comp]) > 0:
                values = np.array(self.component_rewards[comp])
                ax.plot(
                    values, 
                    alpha=0.3, 
                    label=f"{comp} (raw)",
                    color=self.colors.get(comp, "blue")
                )
                
                # Plot rolling average
                if len(values) >= self.rolling_window:
                    rolling_mean = np.convolve(
                        values, 
                        np.ones(self.rolling_window) / self.rolling_window, 
                        mode="valid"
                    )
                    ax.plot(
                        np.arange(self.rolling_window - 1, len(values)), 
                        rolling_mean, 
                        label=f"{comp} (rolling)",
                        color=self.colors.get(comp, "blue"),
                        linewidth=2
                    )
        
        ax.set_title("Component Rewards over Time")
        ax.set_xlabel("Steps")
        ax.set_ylabel("Reward Value")
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
        ax.grid(True, alpha=0.3)
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"component_rewards_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def plot_distribution(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot reward distribution histogram.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if len(self.rewards) < 10:  # Need enough data for a histogram
            return None
        
        fig, ax = plt.subplots(figsize=(10, 6))
        rewards_array = np.array(self.rewards)
        
        # Plot histogram
        n, bins, patches = ax.hist(
            rewards_array, 
            bins=min(50, len(self.rewards) // 5), 
            alpha=0.7, 
            color="blue",
            density=True
        )
        
        # Add normal distribution curve for comparison
        mean = np.mean(rewards_array)
        std = np.std(rewards_array)
        x = np.linspace(min(rewards_array), max(rewards_array), 100)
        y = 1 / (std * np.sqrt(2 * np.pi)) * np.exp(-(x - mean)**2 / (2 * std**2))
        ax.plot(x, y, "r--", linewidth=2, label="Normal Distribution")
        
        ax.set_title("Reward Distribution")
        ax.set_xlabel("Reward")
        ax.set_ylabel("Density")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add statistics as text box
        stats = self.get_statistics()
        stats_text = "\n".join([
            f"Mean: {stats['mean']:.4f}",
            f"Std: {stats['std']:.4f}",
            f"Min: {stats['min']:.4f}",
            f"Max: {stats['max']:.4f}",
            f"Median: {stats['median']:.4f}"
        ])
        ax.text(
            0.02, 0.95, stats_text,
            transform=ax.transAxes,
            bbox=dict(facecolor="white", alpha=0.7),
            verticalalignment="top"
        )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"reward_distribution_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def plot_statistics(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot statistical metrics over episodes.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if len(self.episode_rewards) < 3:  # Need enough episodes
            return None
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Plot episode rewards
        episodes = np.arange(len(self.episode_rewards))
        ax.plot(episodes, self.episode_rewards, label="Episode Reward", color="blue", marker="o")
        
        # Calculate and plot rolling mean if enough data
        window = min(10, len(self.episode_rewards) // 2)
        if len(self.episode_rewards) >= window and window > 1:
            rolling_mean = np.convolve(
                self.episode_rewards, 
                np.ones(window) / window, 
                mode="valid"
            )
            ax.plot(
                np.arange(window - 1, len(self.episode_rewards)), 
                rolling_mean, 
                label=f"Rolling Avg ({window} episodes)", 
                color="orange",
                linewidth=2
            )
        
        ax.set_title("Reward per Episode")
        ax.set_xlabel("Episode")
        ax.set_ylabel("Total Reward")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add episode lengths as secondary y-axis
        if self.episode_steps:
            ax2 = ax.twinx()
            ax2.plot(episodes, self.episode_steps, "g--", label="Episode Length", alpha=0.6)
            ax2.set_ylabel("Steps", color="green")
            ax2.tick_params(axis="y", labelcolor="green")
            
            # Add legend for right y-axis
            lines2, labels2 = ax2.get_legend_handles_labels()
            lines1, labels1 = ax.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"episode_statistics_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def generate_report(self, show: bool = False) -> List[Figure]:
        """
        Generate a comprehensive visualization report.
        
        Args:
            show: Whether to show the plots
            
        Returns:
            List of generated matplotlib figures
        """
        figures = []
        
        # Generate all plots
        figs = [
            self.plot_rewards(show=show, save=True),
            self.plot_components(show=show, save=True),
            self.plot_distribution(show=show, save=True),
            self.plot_statistics(show=show, save=True)
        ]
        
        # Filter out None values (plots that couldn't be generated)
        figures = [fig for fig in figs if fig is not None]
        return figures


class ReplayBufferVisualizer:
    """
    Visualizer for monitoring experience replay buffer statistics.
    
    Features:
    - Tracks TD errors, priorities, and importance sampling weights
    - Visualizes replay frequency of buffer entries
    - Plots distributions of key metrics
    """
    
    def __init__(
        self,
        save_dir: str = "plots",
        max_history: int = 10000
    ):
        """
        Initialize the replay buffer visualizer.
        
        Args:
            save_dir: Directory to save plots
            max_history: Maximum number of updates to track
        """
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_history = max_history
        
        # Tracking data
        self.td_errors = []
        self.priorities = []
        self.weights = []
        self.indices_history = []
        self.replay_count = defaultdict(int)
        self.update_counter = 0
    
    def record_td_errors(self, td_errors: np.ndarray, indices: np.ndarray = None) -> None:
        """
        Record TD errors from the most recent batch.
        
        Args:
            td_errors: Array of TD errors
            indices: Buffer indices corresponding to the TD errors
        """
        self.td_errors.extend(td_errors.flatten())
        self.td_errors = self.td_errors[-self.max_history:]
        
        # Track which indices were sampled
        if indices is not None:
            self.indices_history.append(indices.tolist())
            for idx in indices:
                self.replay_count[int(idx)] += 1
        
        self.update_counter += 1
    
    def record_priorities(self, priorities: np.ndarray) -> None:
        """
        Record buffer priorities after an update.
        
        Args:
            priorities: Array of priorities for the entire buffer
        """
        # Store a snapshot of priorities
        self.priorities.append(priorities.copy())
        self.priorities = self.priorities[-50:]  # Keep last 50 snapshots to save memory
    
    def record_weights(self, weights: np.ndarray) -> None:
        """
        Record importance sampling weights.
        
        Args:
            weights: Array of importance sampling weights from last batch
        """
        self.weights.extend(weights.flatten())
        self.weights = self.weights[-self.max_history:]
    
    def plot_td_error_distribution(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot the distribution of TD errors.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if len(self.td_errors) < 10:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Convert to absolute values for the histogram
        abs_td_errors = np.abs(np.array(self.td_errors))
        
        # Plot histogram
        n, bins, patches = ax.hist(
            abs_td_errors,
            bins=min(50, len(abs_td_errors) // 5),
            alpha=0.7,
            density=True,
            color="blue"
        )
        
        # Plot distribution curve (gamma distribution often fits TD errors well)
        if len(abs_td_errors) > 30:  # Need enough samples for distribution fitting
            from scipy import stats
            shape, loc, scale = stats.gamma.fit(abs_td_errors)
            x = np.linspace(0, max(abs_td_errors), 100)
            y = stats.gamma.pdf(x, shape, loc=loc, scale=scale)
            ax.plot(x, y, "r--", linewidth=2, label="Gamma Distribution")
        
        ax.set_title("Absolute TD Error Distribution")
        ax.set_xlabel("|TD Error|")
        ax.set_ylabel("Density")
        ax.grid(True, alpha=0.3)
        
        # Add statistics as text box
        stats_text = "\n".join([
            f"Mean: {np.mean(abs_td_errors):.6f}",
            f"Median: {np.median(abs_td_errors):.6f}",
            f"Max: {np.max(abs_td_errors):.6f}",
            f"Updates: {self.update_counter}"
        ])
        ax.text(
            0.02, 0.95, stats_text,
            transform=ax.transAxes,
            bbox=dict(facecolor="white", alpha=0.7),
            verticalalignment="top"
        )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"td_error_distribution_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def plot_priority_distribution(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot the distribution of priorities over time.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if not self.priorities:
            return None
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Plot the most recent priority distribution
        priorities = self.priorities[-1]
        
        # Sort priorities for better visualization
        sorted_priorities = np.sort(priorities)[::-1]  # Descending order
        
        # Plot with log scale
        ax.semilogy(np.arange(len(sorted_priorities)), sorted_priorities, label="Current Priorities")
        
        # Plot some historical distributions if available
        if len(self.priorities) > 5:
            for i, historical in enumerate([self.priorities[0], self.priorities[len(self.priorities)//2]]):
                sorted_hist = np.sort(historical)[::-1]
                if len(sorted_hist) == len(sorted_priorities):  # Only if same length
                    label = "Initial" if i == 0 else "Intermediate"
                    ax.semilogy(np.arange(len(sorted_hist)), sorted_hist, alpha=0.5, 
                              linestyle="--", label=f"{label} Priorities")
        
        ax.set_title("Priority Distribution (Log Scale)")
        ax.set_xlabel("Sorted Buffer Index")
        ax.set_ylabel("Priority (log scale)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add statistics
        stats_text = "\n".join([
            f"Mean Priority: {np.mean(priorities):.8f}",
            f"Max/Min Ratio: {np.max(priorities)/np.min(priorities):.2f}",
            f"Updates: {self.update_counter}"
        ])
        ax.text(
            0.02, 0.95, stats_text,
            transform=ax.transAxes,
            bbox=dict(facecolor="white", alpha=0.7),
            verticalalignment="top"
        )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"priority_distribution_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def plot_weight_distribution(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot the distribution of importance sampling weights.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if len(self.weights) < 10:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Plot histogram
        n, bins, patches = ax.hist(
            self.weights,
            bins=min(50, len(self.weights) // 5),
            alpha=0.7,
            density=True,
            color="green"
        )
        
        ax.set_title("IS Weight Distribution")
        ax.set_xlabel("Weight")
        ax.set_ylabel("Density")
        ax.grid(True, alpha=0.3)
        
        # Add statistics
        stats_text = "\n".join([
            f"Mean Weight: {np.mean(self.weights):.4f}",
            f"Median Weight: {np.median(self.weights):.4f}",
            f"Min Weight: {np.min(self.weights):.4f}",
            f"Max Weight: {np.max(self.weights):.4f}"
        ])
        ax.text(
            0.02, 0.95, stats_text,
            transform=ax.transAxes,
            bbox=dict(facecolor="white", alpha=0.7),
            verticalalignment="top"
        )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"weight_distribution_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def plot_replay_frequency(self, show: bool = False, save: bool = True) -> Figure:
        """
        Plot the replay frequency of buffer entries.
        
        Args:
            show: Whether to display the plot
            save: Whether to save the plot
            
        Returns:
            The matplotlib figure
        """
        if not self.replay_count:
            return None
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Get indices and counts
        indices = list(self.replay_count.keys())
        counts = list(self.replay_count.values())
        
        # Sort by count
        sorted_data = sorted(zip(indices, counts), key=lambda x: -x[1])
        sorted_indices, sorted_counts = zip(*sorted_data)
        
        # Plot top 100 most replayed entries
        top_n = min(100, len(sorted_indices))
        ax.bar(range(top_n), sorted_counts[:top_n], alpha=0.7)
        
        ax.set_title(f"Top {top_n} Most Replayed Buffer Entries")
        ax.set_xlabel("Buffer Entry Rank")
        ax.set_ylabel("Replay Count")
        ax.grid(True, alpha=0.3)
        
        # Add buffer index labels for top entries
        for i in range(min(10, top_n)):
            ax.text(i, sorted_counts[i], f"idx={sorted_indices[i]}", 
                   ha="center", va="bottom", rotation=90, fontsize=8)
        
        # Add statistics
        if self.priorities and len(self.priorities[-1]) > 0:
            # Calculate correlation between replay frequency and priority
            indices_array = np.array(list(self.replay_count.keys()))
            counts_array = np.array(list(self.replay_count.values()))
            
            # Only use indices that are valid for the current buffer
            valid_mask = indices_array < len(self.priorities[-1])
            if np.any(valid_mask):
                valid_indices = indices_array[valid_mask]
                valid_counts = counts_array[valid_mask]
                priorities_for_indices = np.array([self.priorities[-1][i] for i in valid_indices])
                
                from scipy.stats import spearmanr
                correlation, p_value = spearmanr(valid_counts, priorities_for_indices)
                
                stats_text = "\n".join([
                    f"Spearman correlation: {correlation:.4f}",
                    f"p-value: {p_value:.4f}",
                    f"Total updates: {self.update_counter}"
                ])
                ax.text(
                    0.02, 0.95, stats_text,
                    transform=ax.transAxes,
                    bbox=dict(facecolor="white", alpha=0.7),
                    verticalalignment="top"
                )
        
        if save:
            plt.tight_layout()
            filename = self.save_dir / f"replay_frequency_{int(time.time())}.png"
            plt.savefig(filename)
            print(f"Saved figure to {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
            
        return fig
    
    def generate_report(self, show: bool = False) -> List[Figure]:
        """
        Generate a comprehensive visualization report.
        
        Args:
            show: Whether to show the plots
            
        Returns:
            List of generated matplotlib figures
        """
        figures = []
        
        # Generate all plots
        figs = [
            self.plot_td_error_distribution(show=show, save=True),
            self.plot_priority_distribution(show=show, save=True),
            self.plot_weight_distribution(show=show, save=True),
            self.plot_replay_frequency(show=show, save=True)
        ]
        
        # Filter out None values (plots that couldn't be generated)
        figures = [fig for fig in figs if fig is not None]
        return figures 