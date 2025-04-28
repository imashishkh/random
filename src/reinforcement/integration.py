"""
Integration module for reinforcement learning components.

This module demonstrates how reward functions, experience replay buffer,
and visualization utilities work together in a reinforcement learning context.
"""

import numpy as np
import torch
import matplotlib.pyplot as plt
from pathlib import Path
import time
import os
import pickle
from typing import Dict, List, Tuple, Optional, Any, Union

from .reward_functions import (
    RewardFunction, PnLReward, SharpeReward, SortinoReward, 
    DrawdownPenaltyReward, MultiObjectiveReward, RewardFactory
)
from .experience_replay import (
    ExperienceReplayBuffer, TorchRLExperienceReplayBuffer
)
from .visualize import (
    RewardVisualizer, ReplayBufferVisualizer
)


class RLIntegration:
    """
    Integrates reward functions, experience replay, and visualization
    for reinforcement learning.
    """
    
    def __init__(
        self,
        reward_config: Dict[str, Any],
        buffer_config: Dict[str, Any],
        visualize_config: Dict[str, Any],
        device: str = "cpu"
    ):
        """
        Initialize the reinforcement learning integration.
        
        Args:
            reward_config: Configuration for reward functions
            buffer_config: Configuration for experience replay buffer
            visualize_config: Configuration for visualization
            device: Device to use for tensor operations ("cpu" or "cuda")
        """
        self.device = device
        
        # Initialize reward function
        self.reward_fn = self._setup_reward_function(reward_config)
        
        # Initialize experience replay buffer
        self.buffer = self._setup_experience_buffer(buffer_config)
        
        # Initialize visualizers
        self.reward_viz = RewardVisualizer(
            save_dir=visualize_config.get("save_dir", "plots/rewards"),
            components=reward_config.get("components", ["pnl"]),
            rolling_window=visualize_config.get("rolling_window", 100)
        )
        
        self.buffer_viz = ReplayBufferVisualizer(
            save_dir=visualize_config.get("save_dir", "plots/buffer")
        )
        
        # Tracking variables
        self.episode_count = 0
        self.step_count = 0
        self.training_count = 0
        self.last_update_time = time.time()
        self.metrics = {
            "episode_returns": [],
            "episode_lengths": [],
            "loss_history": [],
            "training_time": []
        }
    
    def _setup_reward_function(self, config: Dict[str, Any]) -> RewardFunction:
        """
        Set up the reward function based on configuration.
        
        Args:
            config: Reward function configuration
            
        Returns:
            Configured reward function
        """
        reward_type = config.get("type", "pnl")
        
        if reward_type == "multi":
            # Create individual reward functions
            reward_fns = {}
            weights = {}
            
            for name, reward_cfg in config.get("rewards", {}).items():
                reward_fns[name] = RewardFactory.create(
                    reward_type=reward_cfg.get("type", "pnl"),
                    **reward_cfg.get("params", {})
                )
                weights[name] = reward_cfg.get("weight", 1.0)
            
            return MultiObjectiveReward(reward_functions=reward_fns, weights=weights)
        else:
            # Create a single reward function
            return RewardFactory.create(
                reward_type=reward_type,
                **config.get("params", {})
            )
    
    def _setup_experience_buffer(self, config: Dict[str, Any]) -> Union[ExperienceReplayBuffer, TorchRLExperienceReplayBuffer]:
        """
        Set up the experience replay buffer based on configuration.
        
        Args:
            config: Buffer configuration
            
        Returns:
            Configured experience replay buffer
        """
        buffer_type = config.get("type", "standard")
        capacity = config.get("capacity", 10000)
        
        if buffer_type == "torch":
            return TorchRLExperienceReplayBuffer(
                capacity=capacity,
                observation_shape=config.get("observation_shape", (4,)),
                action_shape=config.get("action_shape", (1,)),
                n_step=config.get("n_step", 1),
                gamma=config.get("gamma", 0.99),
                prioritized=config.get("prioritized", True),
                alpha=config.get("alpha", 0.6),
                beta=config.get("beta", 0.4),
                device=self.device
            )
        else:
            return ExperienceReplayBuffer(
                capacity=capacity,
                n_step=config.get("n_step", 1),
                gamma=config.get("gamma", 0.99),
                prioritized=config.get("prioritized", True),
                alpha=config.get("alpha", 0.6),
                beta=config.get("beta", 0.4)
            )
    
    def process_step(
        self,
        state: np.ndarray,
        action: Union[int, float, np.ndarray],
        next_state: np.ndarray,
        portfolio_state: Dict[str, float],
        next_portfolio_state: Dict[str, float],
        done: bool = False,
        info: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        Process a step from the environment, calculating rewards and storing in buffer.
        
        Args:
            state: Current state observation
            action: Action taken
            next_state: Next state observation
            portfolio_state: Current portfolio state (including positions, balance, etc.)
            next_portfolio_state: Next portfolio state
            done: Whether this step concludes an episode
            info: Additional information from the environment
            
        Returns:
            Tuple of (total_reward, reward_components)
        """
        # Calculate reward using the reward function
        reward, components = self.reward_fn.calculate(
            portfolio_state=portfolio_state,
            next_portfolio_state=next_portfolio_state,
            action=action,
            done=done,
            info=info
        )
        
        # Add the experience to the buffer
        if isinstance(self.buffer, TorchRLExperienceReplayBuffer):
            # Convert to tensors for torch buffer
            state_t = torch.as_tensor(state, dtype=torch.float32, device=self.device)
            next_state_t = torch.as_tensor(next_state, dtype=torch.float32, device=self.device)
            
            if isinstance(action, (int, float)):
                action_t = torch.tensor([action], dtype=torch.float32, device=self.device)
            else:
                action_t = torch.as_tensor(action, dtype=torch.float32, device=self.device)
                
            reward_t = torch.tensor([reward], dtype=torch.float32, device=self.device)
            done_t = torch.tensor([done], dtype=torch.float32, device=self.device)
            
            self.buffer.add(state_t, action_t, reward_t, next_state_t, done_t)
        else:
            # Add to standard buffer
            self.buffer.add(state, action, reward, next_state, done)
        
        # Add to reward visualizer
        self.reward_viz.add_reward(
            reward=reward,
            components=components,
            done=done,
            episode_idx=self.episode_count if done else None
        )
        
        # Update tracking variables
        self.step_count += 1
        if done:
            self.episode_count += 1
        
        return reward, components
    
    def train(
        self,
        model: Any,
        batch_size: int = 32,
        gamma: float = 0.99,
        update_priorities: bool = True
    ) -> Dict[str, float]:
        """
        Sample from the experience replay buffer and update the model.
        
        Args:
            model: The model to train (should have a method update(batch) or similar)
            batch_size: Batch size for training
            gamma: Discount factor
            update_priorities: Whether to update priorities based on TD errors
            
        Returns:
            Dictionary of training metrics
        """
        # Check if we have enough samples
        if len(self.buffer) < batch_size:
            return {"loss": 0.0, "td_error_mean": 0.0}
        
        # Sample from the buffer
        if isinstance(self.buffer, TorchRLExperienceReplayBuffer):
            batch, indices, weights = self.buffer.sample(batch_size)
            
            # Record weights for visualization
            if weights is not None:
                self.buffer_viz.record_weights(weights)
        else:
            batch, indices, weights = self.buffer.sample(batch_size)
            
            # Convert to tensors if using a torch model
            if hasattr(model, "device"):
                batch = {
                    "states": torch.as_tensor(batch["states"], dtype=torch.float32, device=model.device),
                    "actions": torch.as_tensor(batch["actions"], dtype=torch.float32, device=model.device),
                    "rewards": torch.as_tensor(batch["rewards"], dtype=torch.float32, device=model.device),
                    "next_states": torch.as_tensor(batch["next_states"], dtype=torch.float32, device=model.device),
                    "dones": torch.as_tensor(batch["dones"], dtype=torch.float32, device=model.device),
                }
                
                if weights is not None:
                    weights = torch.as_tensor(weights, dtype=torch.float32, device=model.device)
        
        # Train the model
        start_time = time.time()
        
        # If model has an update method
        if hasattr(model, "update"):
            loss, td_errors = model.update(batch, weights)
        # If model expects separate arguments
        elif hasattr(model, "learn"):
            if isinstance(batch, dict):
                loss, td_errors = model.learn(
                    batch["states"], 
                    batch["actions"], 
                    batch["rewards"], 
                    batch["next_states"], 
                    batch["dones"], 
                    importance_weights=weights
                )
            else:
                # Assume batch is a tuple of (states, actions, rewards, next_states, dones)
                loss, td_errors = model.learn(*batch, importance_weights=weights)
        else:
            raise ValueError("Model must have either 'update' or 'learn' method")
        
        training_time = time.time() - start_time
        
        # Update priorities if needed
        if update_priorities and indices is not None and td_errors is not None:
            if isinstance(td_errors, torch.Tensor):
                td_errors = td_errors.detach().cpu().numpy()
            
            self.buffer.update_priorities(indices, td_errors)
            
            # Record TD errors and priorities for visualization
            self.buffer_viz.record_td_errors(td_errors, indices)
            
            if hasattr(self.buffer, "priorities"):
                self.buffer_viz.record_priorities(self.buffer.priorities)
        
        # Update metrics
        if isinstance(loss, torch.Tensor):
            loss = loss.item()
        
        td_error_mean = np.mean(np.abs(td_errors)) if td_errors is not None else 0.0
        
        metrics = {
            "loss": loss,
            "td_error_mean": td_error_mean,
            "training_time": training_time
        }
        
        # Store metrics
        self.metrics["loss_history"].append(loss)
        self.metrics["training_time"].append(training_time)
        
        # Record time and increment counter
        self.last_update_time = time.time()
        self.training_count += 1
        
        return metrics
    
    def save(self, path: str) -> None:
        """
        Save the RL integration state.
        
        Args:
            path: Directory path to save files
        """
        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)
        
        # Save buffer
        self.buffer.save(str(save_path / "buffer.pkl"))
        
        # Save metrics and other state info
        with open(save_path / "metrics.pkl", "wb") as f:
            pickle.dump(self.metrics, f)
        
        # Save current state
        state = {
            "episode_count": self.episode_count,
            "step_count": self.step_count,
            "training_count": self.training_count,
            "last_update_time": self.last_update_time,
        }
        
        with open(save_path / "state.pkl", "wb") as f:
            pickle.dump(state, f)
    
    def load(self, path: str) -> None:
        """
        Load the RL integration state.
        
        Args:
            path: Directory path to load files from
        """
        load_path = Path(path)
        
        # Load buffer
        buffer_path = load_path / "buffer.pkl"
        if buffer_path.exists():
            self.buffer.load(str(buffer_path))
        
        # Load metrics
        metrics_path = load_path / "metrics.pkl"
        if metrics_path.exists():
            with open(metrics_path, "rb") as f:
                self.metrics = pickle.load(f)
        
        # Load state
        state_path = load_path / "state.pkl"
        if state_path.exists():
            with open(state_path, "rb") as f:
                state = pickle.load(f)
                self.episode_count = state["episode_count"]
                self.step_count = state["step_count"]
                self.training_count = state["training_count"]
                self.last_update_time = state["last_update_time"]
    
    def generate_visualizations(self, show: bool = False) -> Dict[str, List[plt.Figure]]:
        """
        Generate visualizations for rewards and buffer statistics.
        
        Args:
            show: Whether to show the plots
            
        Returns:
            Dictionary of generated figures
        """
        reward_figures = self.reward_viz.generate_report(show=show)
        buffer_figures = self.buffer_viz.generate_report(show=show)
        
        return {
            "reward": reward_figures,
            "buffer": buffer_figures
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current RL state.
        
        Returns:
            Dictionary containing summary metrics
        """
        # Get latest metrics
        if self.metrics["loss_history"]:
            latest_loss = self.metrics["loss_history"][-1]
            avg_loss_recent = np.mean(self.metrics["loss_history"][-100:])
        else:
            latest_loss = 0
            avg_loss_recent = 0
        
        # Get buffer info
        buffer_size = len(self.buffer)
        buffer_capacity = self.buffer.capacity
        buffer_fullness = buffer_size / buffer_capacity if buffer_capacity > 0 else 0
        
        return {
            "episodes": self.episode_count,
            "steps": self.step_count,
            "training_updates": self.training_count,
            "buffer_size": buffer_size,
            "buffer_capacity": buffer_capacity,
            "buffer_fullness": buffer_fullness,
            "latest_loss": latest_loss,
            "avg_loss_recent": avg_loss_recent,
            "seconds_since_update": time.time() - self.last_update_time
        }


# Example usage
def example_usage():
    """Example demonstrating how to use the RLIntegration class."""
    
    # Example configurations
    reward_config = {
        "type": "multi",
        "rewards": {
            "pnl": {
                "type": "pnl",
                "params": {},
                "weight": 1.0
            },
            "sharpe": {
                "type": "sharpe",
                "params": {"window_size": 20},
                "weight": 0.5
            },
            "drawdown": {
                "type": "drawdown",
                "params": {"penalty_factor": 2.0},
                "weight": 0.3
            }
        },
        "components": ["pnl", "sharpe", "drawdown"]
    }
    
    buffer_config = {
        "type": "torch",
        "capacity": 10000,
        "observation_shape": (10,),  # Example state shape
        "action_shape": (3,),        # Example action shape
        "n_step": 3,
        "gamma": 0.99,
        "prioritized": True,
        "alpha": 0.6,
        "beta": 0.4
    }
    
    visualize_config = {
        "save_dir": "plots",
        "rolling_window": 100
    }
    
    # Set device (CPU or CUDA)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Create the integration
    rl = RLIntegration(
        reward_config=reward_config,
        buffer_config=buffer_config,
        visualize_config=visualize_config,
        device=device
    )
    
    # Example loop (would normally be part of a gym environment)
    for episode in range(5):
        # Reset environment (simulation)
        state = np.random.rand(10)  # Example state
        portfolio_state = {
            "balance": 10000.0,
            "positions": {"BTC": 1.0},
            "portfolio_value": 10000.0,
            "returns": []
        }
        
        done = False
        episode_reward = 0
        
        for step in range(100):  # Steps per episode
            # Choose action (random for this example)
            action = np.random.rand(3)
            
            # Simulate next state and portfolio update
            next_state = np.random.rand(10)
            
            # Update portfolio state with simulated changes
            price_change = np.random.normal(0.001, 0.02)  # Small random price change
            next_portfolio_value = portfolio_state["portfolio_value"] * (1 + price_change)
            
            next_portfolio_state = {
                "balance": portfolio_state["balance"] * (1 + 0.0001),  # Small interest
                "positions": {"BTC": portfolio_state["positions"]["BTC"] * (1 + action[0] * 0.01)},
                "portfolio_value": next_portfolio_value,
                "returns": portfolio_state["returns"] + [price_change]
            }
            
            # Process step in the RL integration
            reward, components = rl.process_step(
                state=state,
                action=action,
                next_state=next_state,
                portfolio_state=portfolio_state,
                next_portfolio_state=next_portfolio_state,
                done=step == 99,  # Last step in episode
                info={"market_volatility": 0.02}
            )
            
            # Update for next step
            state = next_state
            portfolio_state = next_portfolio_state
            episode_reward += reward
            
            # Example training every 10 steps
            if step % 10 == 0 and step > 0:
                # Mock model for example
                class MockModel:
                    def __init__(self):
                        self.device = device
                    
                    def update(self, batch, weights=None):
                        # Simulate model update
                        time.sleep(0.01)
                        loss = 0.5 / (step + 1)  # Decreasing loss
                        
                        # Return loss and TD errors
                        if isinstance(batch["rewards"], torch.Tensor):
                            td_errors = torch.abs(batch["rewards"] - 0.1 * torch.rand_like(batch["rewards"]))
                        else:
                            td_errors = np.abs(batch["rewards"] - 0.1 * np.random.rand(*batch["rewards"].shape))
                        
                        return loss, td_errors
                
                model = MockModel()
                metrics = rl.train(model=model, batch_size=32)
                print(f"Episode {episode}, Step {step}, Loss: {metrics['loss']:.4f}")
        
        print(f"Episode {episode} complete, total reward: {episode_reward:.4f}")
        
        # Generate visualizations after each episode
        if episode % 2 == 0:
            rl.generate_visualizations(show=False)
        
        # Print summary every episode
        summary = rl.get_summary()
        print(f"Summary: {summary}")
    
    # Save the state
    rl.save("rl_checkpoints")
    
    # Generate final visualizations
    figures = rl.generate_visualizations(show=False)
    print(f"Generated {len(figures['reward'])} reward figures and {len(figures['buffer'])} buffer figures")


if __name__ == "__main__":
    example_usage() 