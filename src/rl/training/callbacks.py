import os
import time
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Union
import gymnasium as gym
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.vec_env import VecEnv


class TensorboardCallback(BaseCallback):
    """
    Custom callback for logging additional metrics to tensorboard.
    """
    
    def __init__(self, verbose: int = 0):
        """
        Initialize the callback.
        
        Args:
            verbose: Verbosity level
        """
        super(TensorboardCallback, self).__init__(verbose)
        self.training_start_time = None
        self.episode_count = 0
        self.total_steps = 0
        self.episode_rewards = []
        self.episode_lengths = []
    
    def _on_training_start(self) -> None:
        """Called at the start of training."""
        self.training_start_time = time.time()
        
        # Make sure the model has a logger
        if self.logger is None:
            self.model.set_logger(self.model.logger)
            self.logger = self.model.logger
    
    def _on_step(self) -> bool:
        """
        Process new data when called during training.
        
        Returns:
            True to continue training
        """
        # Increment step counter
        self.total_steps += 1
        
        # Log to tensorboard every 1000 steps
        if self.total_steps % 1000 == 0:
            # Calculate training speed
            elapsed_time = time.time() - self.training_start_time
            steps_per_second = self.total_steps / max(1.0, elapsed_time)
            
            # Log training speed
            self.logger.record("time/steps_per_second", steps_per_second)
            
            # Log memory usage if available
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mem_info = process.memory_info()
                memory_usage = mem_info.rss / (1024 * 1024)  # MB
                self.logger.record("resources/memory_usage_mb", memory_usage)
            except ImportError:
                pass
        
        # Check for completed episodes in a vectorized environment
        if isinstance(self.model.env, VecEnv):
            # For DQN and other off-policy algorithms, the done signal is in info
            info = self.locals.get("infos", [{} for _ in range(self.model.env.num_envs)])
            for i, done in enumerate(self.locals.get("dones", [False] * self.model.env.num_envs)):
                if done:
                    self.episode_count += 1
                    
                    # Extract episode stats
                    episode_info = info[i].get("episode", {})
                    if episode_info:
                        episode_reward = episode_info.get("r", 0)
                        episode_length = episode_info.get("l", 0)
                        
                        self.episode_rewards.append(episode_reward)
                        self.episode_lengths.append(episode_length)
                        
                        # Only keep the most recent 100 episodes
                        self.episode_rewards = self.episode_rewards[-100:]
                        self.episode_lengths = self.episode_lengths[-100:]
                        
                        # Calculate statistics
                        mean_reward = np.mean(self.episode_rewards)
                        mean_length = np.mean(self.episode_lengths)
                        
                        # Log to tensorboard
                        self.logger.record("episode/reward", episode_reward)
                        self.logger.record("episode/length", episode_length)
                        self.logger.record("episode/mean_reward_100", mean_reward)
                        self.logger.record("episode/mean_length_100", mean_length)
                        self.logger.record("episode/count", self.episode_count)
                        
                        # For trading environments, log additional metrics if available
                        if "portfolio_value" in info[i]:
                            self.logger.record("trading/portfolio_value", info[i]["portfolio_value"])
                        if "position" in info[i]:
                            self.logger.record("trading/position", info[i]["position"])
                        if "balance" in info[i]:
                            self.logger.record("trading/balance", info[i]["balance"])
                        if "return" in info[i]:
                            self.logger.record("trading/return", info[i]["return"])
        
        return True
    
    def _on_training_end(self) -> None:
        """Called at the end of training."""
        # Calculate final statistics
        if self.episode_rewards:
            mean_reward = np.mean(self.episode_rewards)
            std_reward = np.std(self.episode_rewards)
            
            self.logger.record("training/mean_reward", mean_reward)
            self.logger.record("training/std_reward", std_reward)
        
        # Log training time
        if self.training_start_time is not None:
            training_time = time.time() - self.training_start_time
            self.logger.record("time/total_training_time", training_time)
            
            # Calculate average speed
            steps_per_second = self.total_steps / max(1.0, training_time)
            self.logger.record("time/average_steps_per_second", steps_per_second)


class ModelEvaluationCallback(BaseCallback):
    """
    Callback for detailed model evaluation during training.
    This goes beyond the standard EvalCallback to calculate additional
    trading-specific metrics.
    """
    
    def __init__(
        self, 
        eval_env: gym.Env, 
        log_freq: int = 10000,
        n_eval_episodes: int = 5,
        deterministic: bool = True,
        verbose: int = 0,
    ):
        """
        Initialize the callback.
        
        Args:
            eval_env: Environment to evaluate on
            log_freq: Frequency of evaluation
            n_eval_episodes: Number of episodes to evaluate
            deterministic: Whether to use deterministic actions
            verbose: Verbosity level
        """
        super(ModelEvaluationCallback, self).__init__(verbose)
        self.eval_env = eval_env
        self.log_freq = log_freq
        self.n_eval_episodes = n_eval_episodes
        self.deterministic = deterministic
        self.best_sharpe = -np.inf
        self.best_return = -np.inf
        self.evaluation_count = 0
    
    def _on_step(self) -> bool:
        """
        Evaluate the model periodically during training.
        
        Returns:
            True to continue training
        """
        if self.n_calls % self.log_freq == 0:
            self.evaluation_count += 1
            # Perform evaluation
            episode_rewards, episode_lengths, episode_portfolios, episode_positions = self._evaluate_model()
            
            # Calculate metrics
            mean_reward = np.mean(episode_rewards)
            std_reward = np.std(episode_rewards)
            mean_length = np.mean(episode_lengths)
            
            # Track the best model based on mean reward
            if mean_reward > self.best_return:
                self.best_return = mean_reward
            
            # Calculate trading-specific metrics if available
            if episode_portfolios:
                # Calculate returns
                portfolio_values = np.array(episode_portfolios)
                returns = portfolio_values[:, 1:] / portfolio_values[:, :-1] - 1.0
                
                # Calculate mean return
                mean_return = np.mean(returns)
                
                # Calculate volatility
                volatility = np.std(returns)
                
                # Calculate Sharpe ratio
                if volatility > 0:
                    sharpe_ratio = mean_return / volatility * np.sqrt(252)  # Annualized
                    
                    # Track the best model based on Sharpe ratio
                    if sharpe_ratio > self.best_sharpe:
                        self.best_sharpe = sharpe_ratio
                        
                    # Log Sharpe ratio
                    self.logger.record("eval/sharpe_ratio", sharpe_ratio)
                
                # Calculate max drawdown
                cumulative_returns = np.cumprod(1 + returns, axis=1)
                running_max = np.maximum.accumulate(cumulative_returns, axis=1)
                drawdowns = (running_max - cumulative_returns) / running_max
                max_drawdown = np.max(drawdowns)
                
                # Log trading metrics
                self.logger.record("eval/mean_return", mean_return)
                self.logger.record("eval/volatility", volatility)
                self.logger.record("eval/max_drawdown", max_drawdown)
            
            # Log standard metrics
            self.logger.record("eval/mean_reward", mean_reward)
            self.logger.record("eval/std_reward", std_reward)
            self.logger.record("eval/mean_length", mean_length)
            self.logger.record("eval/best_return", self.best_return)
            self.logger.record("eval/best_sharpe", self.best_sharpe)
            self.logger.record("eval/evaluation_count", self.evaluation_count)
            
            # Dump log
            self.logger.dump(self.n_calls)
        
        return True
    
    def _evaluate_model(self) -> tuple:
        """
        Evaluate the model on the evaluation environment.
        
        Returns:
            Tuple of (episode_rewards, episode_lengths, episode_portfolios, episode_positions)
        """
        episode_rewards = []
        episode_lengths = []
        episode_portfolios = []
        episode_positions = []
        
        for _ in range(self.n_eval_episodes):
            obs, _ = self.eval_env.reset()
            done = False
            episode_reward = 0.0
            episode_length = 0
            portfolio_values = []
            positions = []
            
            while not done:
                action, _ = self.model.predict(obs, deterministic=self.deterministic)
                obs, reward, terminated, truncated, info = self.eval_env.step(action)
                done = terminated or truncated
                
                episode_reward += reward
                episode_length += 1
                
                # Extract portfolio value and position if available
                if isinstance(info, dict):
                    portfolio_value = info.get("portfolio_value", None)
                    if portfolio_value is not None:
                        portfolio_values.append(portfolio_value)
                    
                    position = info.get("position", None)
                    if position is not None:
                        positions.append(position)
            
            episode_rewards.append(episode_reward)
            episode_lengths.append(episode_length)
            
            if portfolio_values:
                episode_portfolios.append(portfolio_values)
            
            if positions:
                episode_positions.append(positions)
        
        return episode_rewards, episode_lengths, episode_portfolios, episode_positions 