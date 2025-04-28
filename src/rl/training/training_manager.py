import os
import time
import json
import logging
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Union, Tuple, Callable
import gymnasium as gym
import mlflow
import torch as th
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback, EvalCallback
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.vec_env import VecEnv

from .environments.env_factory import create_env
from .models.dqn_extensions import ExtendedDQN
from .models.custom_ppo import CryptoPPO
from .training.callbacks import TensorboardCallback, ModelEvaluationCallback


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("training.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class TrainingManager:
    """
    Training manager for reinforcement learning models.
    
    This class orchestrates the entire training process, including:
    - Environment setup
    - Model initialization
    - Training with checkpointing
    - Hyperparameter management
    - Experiment tracking
    - Curriculum learning
    - Distributed training coordination
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        experiment_name: Optional[str] = None,
        log_dir: str = "logs",
        checkpoint_dir: str = "checkpoints",
        use_mlflow: bool = True,
    ):
        """
        Initialize the training manager.
        
        Args:
            config_path: Path to JSON configuration file
            config: Dictionary containing configuration (overrides config_path if both provided)
            experiment_name: Name for the experiment (used in logging and checkpoints)
            log_dir: Directory to store logs
            checkpoint_dir: Directory to store checkpoints
            use_mlflow: Whether to use MLflow for experiment tracking
        """
        # Set up configuration
        self.config = self._load_config(config_path) if config is None else config
        self.experiment_name = experiment_name or self.config.get("experiment_name", f"rl_training_{int(time.time())}")
        
        # Set up directories
        self.log_dir = os.path.join(log_dir, self.experiment_name)
        self.checkpoint_dir = os.path.join(checkpoint_dir, self.experiment_name)
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        
        # Initialize MLflow if needed
        self.use_mlflow = use_mlflow
        if use_mlflow:
            mlflow.set_experiment(self.experiment_name)
        
        # Initialize attributes
        self.env = None
        self.eval_env = None
        self.model = None
        self.callbacks = []
        self.distributed = False
        self.device = "auto"
        self.best_model_path = None
        
        # Set seed for reproducibility
        self.seed = self.config.get("seed", 42)
        np.random.seed(self.seed)
        th.manual_seed(self.seed)
        
        # Log initialization
        logger.info(f"Initialized TrainingManager with experiment name: {self.experiment_name}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from a JSON file.
        
        Args:
            config_path: Path to JSON configuration file
            
        Returns:
            Dictionary containing configuration
        """
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_path}: {e}")
            # Return default configuration
            return {
                "algorithm": "dqn",
                "env": {
                    "n_envs": 1,
                    "normalize": True,
                    "action_type": "discrete",
                },
                "model": {
                    "learning_rate": 1e-4,
                    "batch_size": 64,
                    "buffer_size": 100000,
                    "learning_starts": 1000,
                    "gamma": 0.99,
                    "target_update_interval": 1000,
                    "train_freq": 4,
                    "gradient_steps": 1,
                },
                "training": {
                    "total_timesteps": 100000,
                    "log_interval": 1000,
                    "save_interval": 10000,
                    "eval_interval": 10000,
                    "n_eval_episodes": 5,
                    "curriculum": False,
                },
            }
    
    def setup_environment(
        self,
        price_data: pd.DataFrame,
        override_env_config: Optional[Dict[str, Any]] = None,
    ) -> VecEnv:
        """
        Set up the training environment.
        
        Args:
            price_data: Historical price data with OHLCV columns
            override_env_config: Override environment configuration
            
        Returns:
            Vectorized environment
        """
        # Get environment configuration
        env_config = self.config.get("env", {})
        if override_env_config:
            env_config.update(override_env_config)
        
        # Configure environment kwargs
        env_kwargs = {
            "initial_balance": env_config.get("initial_balance", 10000.0),
            "transaction_fee": env_config.get("transaction_fee", 0.001),
            "slippage": env_config.get("slippage", 0.0005),
            "window_size": env_config.get("window_size", 24),
            "reward_function": env_config.get("reward_function", "sharpe"),
            "action_type": env_config.get("action_type", "discrete"),
            "max_position": env_config.get("max_position", 1.0),
            "seed": self.seed,
        }
        
        # Create the environment
        n_envs = env_config.get("n_envs", 1)
        normalize = env_config.get("normalize", True)
        use_subproc = env_config.get("use_subproc", False)
        
        self.env = create_env(
            price_data=price_data,
            n_envs=n_envs,
            use_subproc=use_subproc,
            normalize=normalize,
            **env_kwargs
        )
        
        # Create evaluation environment (single environment, no normalization)
        self.eval_env = create_env(
            price_data=price_data,
            n_envs=1,
            use_subproc=False,
            normalize=False,
            **env_kwargs
        )
        
        logger.info(f"Created environment with {n_envs} parallel environments")
        return self.env
    
    def create_model(
        self,
        algorithm: Optional[str] = None,
        override_model_config: Optional[Dict[str, Any]] = None,
    ) -> Union[ExtendedDQN, CryptoPPO]:
        """
        Create a reinforcement learning model.
        
        Args:
            algorithm: Algorithm to use ("dqn" or "ppo")
            override_model_config: Override model configuration
            
        Returns:
            Reinforcement learning model
        """
        if self.env is None:
            raise ValueError("Environment must be set up before creating the model")
        
        # Get model configuration
        algorithm = algorithm or self.config.get("algorithm", "dqn")
        model_config = self.config.get("model", {})
        if override_model_config:
            model_config.update(override_model_config)
        
        # Configure device
        self.device = model_config.get("device", "auto")
        device = self.device
        
        # Common model kwargs
        common_kwargs = {
            "env": self.env,
            "verbose": 1,
            "tensorboard_log": self.log_dir,
            "device": device,
            "seed": self.seed,
        }
        
        # Create model based on algorithm
        if algorithm.lower() == "dqn":
            # DQN-specific config
            dqn_kwargs = {
                "learning_rate": model_config.get("learning_rate", 1e-4),
                "buffer_size": model_config.get("buffer_size", 100000),
                "learning_starts": model_config.get("learning_starts", 1000),
                "batch_size": model_config.get("batch_size", 64),
                "gamma": model_config.get("gamma", 0.99),
                "train_freq": model_config.get("train_freq", 4),
                "gradient_steps": model_config.get("gradient_steps", 1),
                "target_update_interval": model_config.get("target_update_interval", 1000),
                "exploration_fraction": model_config.get("exploration_fraction", 0.1),
                "exploration_initial_eps": model_config.get("exploration_initial_eps", 1.0),
                "exploration_final_eps": model_config.get("exploration_final_eps", 0.05),
                "max_grad_norm": model_config.get("max_grad_norm", 10),
                # Extended DQN params
                "use_double_dqn": model_config.get("use_double_dqn", True),
                "use_dueling": model_config.get("use_dueling", True),
                "use_noisy": model_config.get("use_noisy", True),
                "hidden_dim": model_config.get("hidden_dim", 128),
            }
            
            # Create the model
            self.model = ExtendedDQN(
                policy="MlpPolicy",
                **common_kwargs,
                **dqn_kwargs
            )
            logger.info(f"Created ExtendedDQN model with parameters: {dqn_kwargs}")
            
        elif algorithm.lower() == "ppo":
            # PPO-specific config
            ppo_kwargs = {
                "learning_rate": model_config.get("learning_rate", 3e-4),
                "n_steps": model_config.get("n_steps", 2048),
                "batch_size": model_config.get("batch_size", 64),
                "n_epochs": model_config.get("n_epochs", 10),
                "gamma": model_config.get("gamma", 0.99),
                "gae_lambda": model_config.get("gae_lambda", 0.95),
                "clip_range": model_config.get("clip_range", 0.2),
                "clip_range_vf": model_config.get("clip_range_vf", None),
                "normalize_advantage": model_config.get("normalize_advantage", True),
                "ent_coef": model_config.get("ent_coef", 0.0),
                "vf_coef": model_config.get("vf_coef", 0.5),
                "max_grad_norm": model_config.get("max_grad_norm", 0.5),
                "target_kl": model_config.get("target_kl", None),
                # Crypto PPO params
                "dynamic_clip_range": model_config.get("dynamic_clip_range", True),
                "risk_adjustment": model_config.get("risk_adjustment", True),
                "value_clip_factor": model_config.get("value_clip_factor", 1.0),
            }
            
            # Create the model
            self.model = CryptoPPO(
                policy="MlpPolicy",
                **common_kwargs,
                **ppo_kwargs
            )
            logger.info(f"Created CryptoPPO model with parameters: {ppo_kwargs}")
            
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        return self.model
    
    def setup_callbacks(self) -> List[BaseCallback]:
        """
        Set up training callbacks.
        
        Returns:
            List of callbacks
        """
        training_config = self.config.get("training", {})
        
        # Checkpoint callback
        save_interval = training_config.get("save_interval", 10000)
        checkpoint_callback = CheckpointCallback(
            save_freq=save_interval,
            save_path=self.checkpoint_dir,
            name_prefix=f"{self.experiment_name}",
            save_replay_buffer=True,
            save_vecnormalize=True,
        )
        
        # Evaluation callback
        eval_interval = training_config.get("eval_interval", 10000)
        n_eval_episodes = training_config.get("n_eval_episodes", 5)
        eval_callback = EvalCallback(
            self.eval_env,
            best_model_save_path=self.checkpoint_dir,
            log_path=self.log_dir,
            eval_freq=eval_interval,
            n_eval_episodes=n_eval_episodes,
            deterministic=True,
            render=False,
        )
        
        # Tensorboard callback for custom metrics
        tensorboard_callback = TensorboardCallback()
        
        # Model evaluation callback
        model_eval_callback = ModelEvaluationCallback(self.eval_env, log_freq=eval_interval)
        
        self.callbacks = [
            checkpoint_callback,
            eval_callback,
            tensorboard_callback,
            model_eval_callback,
        ]
        
        logger.info(f"Set up {len(self.callbacks)} training callbacks")
        return self.callbacks
    
    def train(
        self,
        total_timesteps: Optional[int] = None,
        curriculum_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Train the reinforcement learning model.
        
        Args:
            total_timesteps: Total number of timesteps to train for
            curriculum_config: Configuration for curriculum learning
        """
        if self.model is None:
            raise ValueError("Model must be created before training")
        
        # Get training configuration
        training_config = self.config.get("training", {})
        total_timesteps = total_timesteps or training_config.get("total_timesteps", 100000)
        log_interval = training_config.get("log_interval", 1000)
        
        # Set up MLflow
        if self.use_mlflow:
            mlflow.start_run(run_name=self.experiment_name)
            # Log parameters
            mlflow.log_params({
                "algorithm": self.config.get("algorithm", "dqn"),
                "total_timesteps": total_timesteps,
                "seed": self.seed,
                **{f"env.{k}": v for k, v in self.config.get("env", {}).items()},
                **{f"model.{k}": v for k, v in self.config.get("model", {}).items()},
            })
        
        # Check if curriculum learning is enabled
        use_curriculum = training_config.get("curriculum", False)
        
        if use_curriculum and curriculum_config is not None:
            self._train_with_curriculum(total_timesteps, curriculum_config, log_interval)
        else:
            # Regular training
            logger.info(f"Starting training for {total_timesteps} timesteps")
            self.model.learn(
                total_timesteps=total_timesteps,
                callback=self.callbacks,
                log_interval=log_interval,
                tb_log_name=self.experiment_name,
            )
            
            # Save final model
            final_model_path = os.path.join(self.checkpoint_dir, f"{self.experiment_name}_final")
            self.model.save(final_model_path)
            logger.info(f"Saved final model to {final_model_path}")
            
            # Identify best model path
            self.best_model_path = os.path.join(self.checkpoint_dir, f"best_model")
            if not os.path.exists(f"{self.best_model_path}.zip"):
                self.best_model_path = final_model_path
        
        # End MLflow run
        if self.use_mlflow:
            mlflow.end_run()
    
    def _train_with_curriculum(
        self,
        total_timesteps: int,
        curriculum_config: Dict[str, Any],
        log_interval: int,
    ) -> None:
        """
        Train with curriculum learning.
        
        Args:
            total_timesteps: Total number of timesteps to train for
            curriculum_config: Configuration for curriculum learning
            log_interval: Interval for logging
        """
        logger.info("Starting training with curriculum learning")
        
        # Extract curriculum stages
        stages = curriculum_config.get("stages", [])
        
        if not stages:
            logger.warning("No curriculum stages provided, falling back to regular training")
            self.train(total_timesteps=total_timesteps)
            return
        
        # Calculate timesteps per stage
        timesteps_per_stage = total_timesteps // len(stages)
        
        # Train on each stage
        for i, stage_config in enumerate(stages):
            stage_name = stage_config.get("name", f"stage_{i}")
            logger.info(f"Starting curriculum stage {i+1}/{len(stages)}: {stage_name}")
            
            # Update environment configuration for this stage
            env_config = stage_config.get("env", {})
            if env_config:
                # Recreate environment with new configuration
                if hasattr(self.env, "close"):
                    self.env.close()
                if hasattr(self.eval_env, "close"):
                    self.eval_env.close()
                
                # Get price data from existing environment
                # This is a simplified approach; in a real implementation,
                # you would need to extract the price data more carefully
                price_data = self.config.get("price_data", None)
                if price_data is None:
                    raise ValueError("Price data must be provided for curriculum learning")
                
                self.setup_environment(price_data, override_env_config=env_config)
                
                # Recreate model with new environment
                algorithm = self.config.get("algorithm", "dqn")
                self.create_model(algorithm=algorithm)
                
                # Recreate callbacks
                self.setup_callbacks()
            
            # Update model configuration for this stage
            model_config = stage_config.get("model", {})
            if model_config and i > 0:  # Skip first stage as the model is already created
                # Apply model config updates (learning rate, etc.)
                for param, value in model_config.items():
                    if hasattr(self.model, param):
                        setattr(self.model, param, value)
                        logger.info(f"Updated model parameter {param} to {value}")
            
            # Train for this stage
            stage_timesteps = stage_config.get("timesteps", timesteps_per_stage)
            
            self.model.learn(
                total_timesteps=stage_timesteps,
                callback=self.callbacks,
                log_interval=log_interval,
                tb_log_name=f"{self.experiment_name}_{stage_name}",
                reset_num_timesteps=False,  # Continue counting timesteps
            )
            
            # Save stage model
            stage_model_path = os.path.join(self.checkpoint_dir, f"{self.experiment_name}_{stage_name}")
            self.model.save(stage_model_path)
            logger.info(f"Saved stage model to {stage_model_path}")
        
        # Save final model
        final_model_path = os.path.join(self.checkpoint_dir, f"{self.experiment_name}_final")
        self.model.save(final_model_path)
        logger.info(f"Saved final model to {final_model_path}")
        
        # Identify best model path
        self.best_model_path = os.path.join(self.checkpoint_dir, f"best_model")
        if not os.path.exists(f"{self.best_model_path}.zip"):
            self.best_model_path = final_model_path
    
    def evaluate(
        self,
        model_path: Optional[str] = None,
        n_eval_episodes: int = 10,
        deterministic: bool = True,
    ) -> Dict[str, float]:
        """
        Evaluate a trained model.
        
        Args:
            model_path: Path to model file (uses best model if None)
            n_eval_episodes: Number of episodes to evaluate
            deterministic: Whether to use deterministic actions
            
        Returns:
            Dictionary of evaluation metrics
        """
        # Load model if path provided
        if model_path is not None:
            if self.config.get("algorithm", "dqn").lower() == "dqn":
                model = ExtendedDQN.load(model_path, env=self.eval_env)
            else:
                model = CryptoPPO.load(model_path, env=self.eval_env)
            logger.info(f"Loaded model from {model_path}")
        else:
            # Use best model if available, otherwise use current model
            if self.best_model_path and os.path.exists(f"{self.best_model_path}.zip"):
                if self.config.get("algorithm", "dqn").lower() == "dqn":
                    model = ExtendedDQN.load(self.best_model_path, env=self.eval_env)
                else:
                    model = CryptoPPO.load(self.best_model_path, env=self.eval_env)
                logger.info(f"Loaded best model from {self.best_model_path}")
            else:
                model = self.model
                logger.info("Using current model for evaluation")
        
        # Evaluate model
        mean_reward, std_reward = evaluate_policy(
            model,
            self.eval_env,
            n_eval_episodes=n_eval_episodes,
            deterministic=deterministic,
        )
        
        # Calculate additional metrics
        metrics = {
            "mean_reward": mean_reward,
            "std_reward": std_reward,
        }
        
        # Log metrics
        logger.info(f"Evaluation metrics: {metrics}")
        
        # Log to MLflow if enabled
        if self.use_mlflow:
            mlflow.log_metrics(metrics)
        
        return metrics
    
    def load_model(
        self,
        model_path: str,
        algorithm: Optional[str] = None,
    ) -> Union[ExtendedDQN, CryptoPPO]:
        """
        Load a trained model.
        
        Args:
            model_path: Path to model file
            algorithm: Algorithm type ("dqn" or "ppo", auto-detected if None)
            
        Returns:
            Loaded model
        """
        if self.env is None:
            raise ValueError("Environment must be set up before loading a model")
        
        # Determine algorithm if not provided
        if algorithm is None:
            # Try to infer from file name
            if "dqn" in model_path.lower():
                algorithm = "dqn"
            elif "ppo" in model_path.lower():
                algorithm = "ppo"
            else:
                # Default to configuration
                algorithm = self.config.get("algorithm", "dqn")
        
        # Load model
        if algorithm.lower() == "dqn":
            self.model = ExtendedDQN.load(model_path, env=self.env)
        elif algorithm.lower() == "ppo":
            self.model = CryptoPPO.load(model_path, env=self.env)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        logger.info(f"Loaded {algorithm} model from {model_path}")
        return self.model
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.env is not None and hasattr(self.env, "close"):
            self.env.close()
        
        if self.eval_env is not None and hasattr(self.eval_env, "close"):
            self.eval_env.close()
        
        logger.info("Cleaned up resources")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup() 