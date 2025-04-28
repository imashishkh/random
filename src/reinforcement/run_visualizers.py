#!/usr/bin/env python
"""
Runner script to demonstrate visualization utilities for reinforcement learning.

This script provides direct examples of using the visualization tools without
going through an integration layer. It includes demonstrations for:
1. Reward visualization with synthetic reward data
2. Replay buffer visualization with simulated buffer statistics
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import time
import argparse
import random
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
import math

# Import visualizers
from visualize import RewardVisualizer, ReplayBufferVisualizer


def simulate_rewards(
    num_episodes: int = 10,
    steps_per_episode: int = 100,
    plots_dir: str = "plots/reward_demo",
    show_plots: bool = False,
    noise_level: float = 0.2,
    components: List[str] = None
) -> None:
    """
    Simulate and visualize reward data with the RewardVisualizer.
    
    Args:
        num_episodes: Number of episodes to simulate
        steps_per_episode: Steps per episode
        plots_dir: Directory to save plots
        show_plots: Whether to display plots
        noise_level: Level of random noise to add
        components: List of reward components to track
    """
    print(f"Simulating rewards for {num_episodes} episodes with {steps_per_episode} steps each...")
    
    # Initialize components if not provided
    if components is None:
        components = ["pnl", "sharpe", "drawdown"]
    
    # Initialize visualizer
    visualizer = RewardVisualizer(
        save_dir=plots_dir,
        components=components,
        rolling_window=min(50, steps_per_episode // 2)
    )
    
    # Learning curve parameters (reward improves over episodes)
    base_reward = -0.5
    learning_rate = 2.0
    
    # Simulate episodes
    for episode in range(num_episodes):
        # Calculate episode progress (0 to 1)
        progress = episode / max(1, num_episodes - 1)
        
        # Reward improves with episode number (simulating learning)
        episode_base = base_reward + progress * learning_rate
        
        # Add sinusoidal oscillation to simulate market cycles
        cycle_factor = math.sin(episode * 0.5) * 0.3
        
        # Initial component values for this episode
        component_bases = {
            "pnl": episode_base * 0.6 + cycle_factor,
            "sharpe": min(3.0, max(0.0, 0.5 + progress * 2.5)) + cycle_factor * 0.5,
            "drawdown": -0.3 - progress * 0.1 - abs(cycle_factor) * 0.2
        }
        
        for step in range(steps_per_episode):
            # Step progress (0 to 1)
            step_progress = step / max(1, steps_per_episode - 1)
            
            # Calculate component rewards with noise and trends
            component_rewards = {}
            for comp in components:
                if comp in component_bases:
                    # Add noise and some trend within the episode
                    base = component_bases[comp]
                    trend = step_progress * 0.2 * (1 if base > 0 else -1)  # Trend depends on sign
                    noise = (random.random() - 0.5) * 2 * noise_level
                    component_rewards[comp] = base + trend + noise
            
            # Total reward is a weighted sum of components
            total_reward = (
                0.7 * component_rewards.get("pnl", 0) +
                0.2 * component_rewards.get("sharpe", 0) +
                0.1 * component_rewards.get("drawdown", 0)
            )
            
            # Add reward to visualizer
            is_last_step = step == steps_per_episode - 1
            visualizer.add_reward(
                reward=total_reward,
                components=component_rewards,
                done=is_last_step,
                episode_idx=episode
            )
            
            # For real-time visualization, you could add a small delay
            # time.sleep(0.01)
    
    # Generate all plots
    print("Generating reward visualization report...")
    figures = visualizer.generate_report(show=show_plots)
    print(f"Generated {len(figures)} plots in {plots_dir}")


def simulate_replay_buffer(
    buffer_size: int = 1000,
    batch_size: int = 64,
    num_updates: int = 200,
    plots_dir: str = "plots/buffer_demo",
    show_plots: bool = False,
    prioritized: bool = True,
    alpha: float = 0.6,
    beta_start: float = 0.4,
    beta_end: float = 1.0
) -> None:
    """
    Simulate and visualize replay buffer statistics.
    
    Args:
        buffer_size: Size of the replay buffer
        batch_size: Batch size for updates
        num_updates: Number of updates to simulate
        plots_dir: Directory to save plots
        show_plots: Whether to display plots
        prioritized: Whether to simulate prioritized experience replay
        alpha: Priority exponent
        beta_start: Initial importance sampling exponent
        beta_end: Final importance sampling exponent
    """
    print(f"Simulating replay buffer with {buffer_size} entries and {num_updates} updates...")
    
    # Initialize visualizer
    visualizer = ReplayBufferVisualizer(save_dir=plots_dir)
    
    # Initialize simulated buffer with random priorities
    priorities = np.ones(buffer_size) * 1e-6  # Small initial priorities
    
    # Simulate buffer filling up
    buffer_fill = min(buffer_size, batch_size * 5)
    
    # Initially, mark some experiences as "interesting" with higher priorities
    interesting_indices = np.random.choice(buffer_fill, size=buffer_fill//10, replace=False)
    priorities[interesting_indices] = 1.0
    
    # Simulate updates
    for update in range(num_updates):
        # Linear beta schedule
        beta = beta_start + (beta_end - beta_start) * (update / max(1, num_updates - 1))
        
        if prioritized:
            # Sample based on priorities
            probs = priorities[:buffer_fill] ** alpha
            probs /= probs.sum()
            
            # Sample indices based on priorities
            indices = np.random.choice(
                buffer_fill,
                size=min(batch_size, buffer_fill),
                replace=False,
                p=probs
            )
            
            # Calculate importance sampling weights
            weights = (buffer_fill * probs[indices]) ** (-beta)
            weights /= weights.max()  # Normalize weights
        else:
            # Uniform sampling
            indices = np.random.choice(
                buffer_fill,
                size=min(batch_size, buffer_fill),
                replace=False
            )
            weights = np.ones(len(indices))
        
        # Simulate TD errors: higher for interesting experiences, plus noise
        td_errors = np.zeros(len(indices))
        for i, idx in enumerate(indices):
            # Base TD error depends on whether it's an "interesting" experience
            if idx in interesting_indices:
                base_error = 1.0 - update/num_updates * 0.5  # Gradually decreases as we learn
            else:
                base_error = 0.1 + update/num_updates * 0.2  # Gradually increases as other experiences get more important
            
            # Add noise
            noise = np.random.normal(0, 0.2)
            td_errors[i] = base_error + noise
        
        # Update priorities based on TD errors
        for i, idx in enumerate(indices):
            # Update with some momentum to avoid wild oscillations
            priorities[idx] = 0.7 * priorities[idx] + 0.3 * (abs(td_errors[i]) + 1e-6)
        
        # Increase buffer fill
        buffer_fill = min(buffer_size, buffer_fill + batch_size//2)
        
        # Periodically add new interesting experiences
        if update % 20 == 0 and update > 0:
            new_interesting = np.random.choice(
                buffer_fill,
                size=min(5, buffer_fill//20),
                replace=False
            )
            interesting_indices = np.concatenate([interesting_indices, new_interesting])
            priorities[new_interesting] = 1.0
        
        # Record data in visualizer
        visualizer.record_td_errors(td_errors, indices)
        visualizer.record_priorities(priorities)
        visualizer.record_weights(weights)
    
    # Generate all plots
    print("Generating replay buffer visualization report...")
    figures = visualizer.generate_report(show=show_plots)
    print(f"Generated {len(figures)} plots in {plots_dir}")


def main():
    """Main function to run the demos."""
    parser = argparse.ArgumentParser(description="Reinforcement Learning Visualization Demo")
    parser.add_argument("--demo", choices=["rewards", "buffer", "both"], default="both",
                       help="Which demo to run (rewards, buffer, or both)")
    parser.add_argument("--episodes", type=int, default=20,
                       help="Number of episodes for reward demo")
    parser.add_argument("--steps", type=int, default=100,
                       help="Steps per episode for reward demo")
    parser.add_argument("--buffer-size", type=int, default=1000,
                       help="Buffer size for replay buffer demo")
    parser.add_argument("--updates", type=int, default=200,
                       help="Number of updates for replay buffer demo")
    parser.add_argument("--show", action="store_true",
                       help="Show plots (not just save them)")
    parser.add_argument("--output-dir", type=str, default="plots",
                       help="Base directory for saving plots")
    
    args = parser.parse_args()
    
    # Create output directories
    base_dir = Path(args.output_dir)
    rewards_dir = base_dir / "reward_demo"
    buffer_dir = base_dir / "buffer_demo"
    
    # Run selected demos
    if args.demo in ["rewards", "both"]:
        simulate_rewards(
            num_episodes=args.episodes,
            steps_per_episode=args.steps,
            plots_dir=str(rewards_dir),
            show_plots=args.show
        )
    
    if args.demo in ["buffer", "both"]:
        simulate_replay_buffer(
            buffer_size=args.buffer_size,
            num_updates=args.updates,
            plots_dir=str(buffer_dir),
            show_plots=args.show
        )
    
    print("Demo(s) completed successfully!")


if __name__ == "__main__":
    main() 