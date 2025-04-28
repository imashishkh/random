import numpy as np
import torch as th
import torch.nn as nn
from typing import Any, Dict, List, Optional, Tuple, Type, Union, Callable

from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.type_aliases import Schedule


class CryptoActorCriticPolicy(ActorCriticPolicy):
    """
    Actor-critic policy for cryptocurrency trading.
    
    This extends the base ActorCriticPolicy from Stable Baselines3 with
    customizations specific to cryptocurrency trading.
    """
    
    def __init__(
        self,
        observation_space,
        action_space,
        lr_schedule: Schedule,
        net_arch: Optional[List[Union[int, Dict[str, List[int]]]]] = None,
        activation_fn: Type[nn.Module] = nn.Tanh,
        ortho_init: bool = True,
        use_sde: bool = False,
        log_std_init: float = -0.5,
        full_std: bool = True,
        use_expln: bool = False,
        squash_output: bool = False,
        features_extractor_class = None,
        features_extractor_kwargs: Optional[Dict[str, Any]] = None,
        share_features_extractor: bool = True,
        normalize_images: bool = True,
        optimizer_class: Type[th.optim.Optimizer] = th.optim.Adam,
        optimizer_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the policy.
        
        Args:
            observation_space: Observation space
            action_space: Action space
            lr_schedule: Learning rate schedule
            net_arch: Network architecture
            activation_fn: Activation function
            ortho_init: Whether to use orthogonal initialization
            use_sde: Whether to use State Dependent Exploration
            log_std_init: Initial value for log standard deviation
            full_std: Whether to use a separate network for the std
            use_expln: Whether to use expln() instead of exp() when using sde
            squash_output: Whether to squash the output using tanh
            features_extractor_class: Features extractor class
            features_extractor_kwargs: Features extractor kwargs
            share_features_extractor: Whether to share the features extractor for actor and critic
            normalize_images: Whether to normalize images
            optimizer_class: Optimizer class
            optimizer_kwargs: Optimizer kwargs
        """
        # Set default net_arch if not provided
        if net_arch is None:
            # Larger network for crypto trading
            net_arch = [dict(pi=[128, 128], vf=[128, 128])]
        
        # Set default optimizer_kwargs if not provided
        if optimizer_kwargs is None:
            optimizer_kwargs = {
                "eps": 1e-5,  # For better numerical stability
                "weight_decay": 1e-5,  # L2 regularization
            }
        
        # Initialize parent class
        super(CryptoActorCriticPolicy, self).__init__(
            observation_space=observation_space,
            action_space=action_space,
            lr_schedule=lr_schedule,
            net_arch=net_arch,
            activation_fn=activation_fn,
            ortho_init=ortho_init,
            use_sde=use_sde,
            log_std_init=log_std_init,
            full_std=full_std,
            use_expln=use_expln,
            squash_output=squash_output,
            features_extractor_class=features_extractor_class,
            features_extractor_kwargs=features_extractor_kwargs,
            share_features_extractor=share_features_extractor,
            normalize_images=normalize_images,
            optimizer_class=optimizer_class,
            optimizer_kwargs=optimizer_kwargs,
        )


class CryptoPPO(PPO):
    """
    Custom PPO implementation for cryptocurrency trading.
    
    This extends the base PPO implementation from Stable Baselines3 with
    customizations specific to cryptocurrency trading, including additional
    configuration options that are beneficial for financial markets.
    """
    
    def __init__(
        self,
        policy,
        env,
        learning_rate: Union[float, Schedule] = 3e-4,
        n_steps: int = 2048,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: Union[float, Schedule] = 0.2,
        clip_range_vf: Union[None, float, Schedule] = None,
        normalize_advantage: bool = True,
        ent_coef: float = 0.0,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        use_sde: bool = False,
        sde_sample_freq: int = -1,
        target_kl: Optional[float] = None,
        tensorboard_log: Optional[str] = None,
        create_eval_env: bool = False,
        policy_kwargs: Optional[Dict[str, Any]] = None,
        verbose: int = 0,
        seed: Optional[int] = None,
        device: Union[th.device, str] = "auto",
        _init_setup_model: bool = True,
        # Crypto trading specific parameters
        dynamic_clip_range: bool = True,  # Dynamically adjust clip range based on value loss
        risk_adjustment: bool = True,  # Apply risk adjustment to rewards
        value_clip_factor: float = 1.0,  # Factor for value function clipping (relative to policy clip_range)
    ):
        """
        Initialize the PPO algorithm.
        
        Args:
            policy: The policy model to use
            env: The environment to learn from
            learning_rate: The learning rate
            n_steps: The number of steps to run for each environment per update
            batch_size: Minibatch size
            n_epochs: Number of epochs when optimizing the surrogate loss
            gamma: Discount factor
            gae_lambda: Factor for trade-off between bias and variance in GAE
            clip_range: Clipping parameter for PPO
            clip_range_vf: Clipping parameter for value function
            normalize_advantage: Whether to normalize advantages
            ent_coef: Entropy coefficient for the loss calculation
            vf_coef: Value function coefficient for the loss calculation
            max_grad_norm: The maximum value for the gradient clipping
            use_sde: Whether to use generalized State Dependent Exploration
            sde_sample_freq: Sample a new noise matrix every n steps when using SDE
            target_kl: Limit the KL divergence between updates
            tensorboard_log: The log location for tensorboard
            create_eval_env: Whether to create a second environment to evaluate on
            policy_kwargs: Arguments to pass to the policy on creation
            verbose: Verbosity level
            seed: Random seed
            device: Device to use for computation
            _init_setup_model: Whether or not to build the network at the creation of the instance
            dynamic_clip_range: Whether to adjust clip range dynamically based on value loss
            risk_adjustment: Whether to apply risk adjustment to rewards
            value_clip_factor: Factor for value function clipping
        """
        # Initialize policy_kwargs if not provided
        policy_kwargs = {} if policy_kwargs is None else policy_kwargs
        
        # Set default value for clip_range_vf if not provided
        if clip_range_vf is None and value_clip_factor > 0:
            clip_range_vf = clip_range * value_clip_factor
        
        # Store crypto trading specific parameters
        self.dynamic_clip_range = dynamic_clip_range
        self.risk_adjustment = risk_adjustment
        self.value_clip_factor = value_clip_factor
        self.original_clip_range = clip_range
        
        # Initialize parent class
        super(CryptoPPO, self).__init__(
            policy=policy,
            env=env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            clip_range_vf=clip_range_vf,
            normalize_advantage=normalize_advantage,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            max_grad_norm=max_grad_norm,
            use_sde=use_sde,
            sde_sample_freq=sde_sample_freq,
            target_kl=target_kl,
            tensorboard_log=tensorboard_log,
            create_eval_env=create_eval_env,
            policy_kwargs=policy_kwargs,
            verbose=verbose,
            seed=seed,
            device=device,
            _init_setup_model=_init_setup_model,
        )
    
    def train(self) -> None:
        """
        Update policy using the currently gathered rollout buffer.
        This is an override of the parent method to add risk adjustment
        and dynamic clip range adjustment.
        """
        # Switch to train mode (affects dropout, batch norm, etc.)
        self.policy.set_training_mode(True)
        
        # Update optimizer learning rate
        self._update_learning_rate(self.policy.optimizer)
        
        # Get clip range
        clip_range = self.clip_range(self._current_progress_remaining)
        
        # Optional: adjust clip range based on recent performance
        if self.dynamic_clip_range and hasattr(self, "_last_value_loss"):
            # If value loss is high, reduce clip range to stabilize training
            value_loss_threshold = 0.1
            if self._last_value_loss > value_loss_threshold:
                clip_range *= 0.8  # Reduce clip range
                if hasattr(self, "clip_range_vf") and self.clip_range_vf is not None:
                    self.clip_range_vf *= 0.8
        
        # Compute clip range for value function if needed
        if self.clip_range_vf is not None:
            clip_range_vf = self.clip_range_vf(self._current_progress_remaining)
        
        entropy_losses = []
        pg_losses, value_losses = [], []
        clip_fractions = []
        
        # Train for n_epochs epochs
        continue_training = True
        for epoch in range(self.n_epochs):
            approx_kl_divs = []
            # Do a complete pass on the rollout buffer
            for rollout_data in self.rollout_buffer.get(self.batch_size):
                actions = rollout_data.actions
                if isinstance(self.action_space, gym.spaces.Discrete):
                    # Convert discrete action indices to one-hot vectors
                    actions = th.as_tensor(actions, device=self.device).long().flatten()
                
                # Apply risk adjustment to rewards if enabled
                if self.risk_adjustment:
                    # Simple downside risk penalty based on negative returns
                    # This penalizes large losses more heavily
                    returns = rollout_data.returns
                    negative_returns = th.minimum(returns, th.zeros_like(returns))
                    downside_risk_penalty = 0.5 * th.square(negative_returns)
                    rollout_data.returns = returns - downside_risk_penalty
                
                # Re-sample actions using the latest version of the policy
                values, log_probs, entropy = self.policy.evaluate_actions(
                    rollout_data.observations, actions
                )
                
                advantages = rollout_data.advantages
                if self.normalize_advantage:
                    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
                
                # Ratio between old and new policy
                ratio = th.exp(log_probs - rollout_data.old_log_probs)
                
                # Clipped surrogate loss
                policy_loss_1 = advantages * ratio
                policy_loss_2 = advantages * th.clamp(ratio, 1 - clip_range, 1 + clip_range)
                policy_loss = -th.min(policy_loss_1, policy_loss_2).mean()
                
                # Clipping fraction for logging
                clip_fraction = th.mean((th.abs(ratio - 1) > clip_range).float()).item()
                clip_fractions.append(clip_fraction)
                
                # Value loss
                if self.clip_range_vf is None:
                    # No clipping
                    values_pred = values
                else:
                    # Clip value function to reduce variability
                    values_pred = rollout_data.old_values + th.clamp(
                        values - rollout_data.old_values, -clip_range_vf, clip_range_vf
                    )
                value_loss = th.mean(th.square(values_pred - rollout_data.returns))
                
                # Store value loss for dynamic clip range adjustment
                self._last_value_loss = value_loss.item()
                
                # Entropy loss (maximize entropy to encourage exploration)
                if entropy is None:
                    # Some distributions have no entropy defined
                    entropy_loss = 0
                else:
                    entropy_loss = -th.mean(entropy)
                
                # Total loss
                loss = policy_loss + self.vf_coef * value_loss + self.ent_coef * entropy_loss
                
                # Calculate approximate KL divergence for early stopping
                if self.target_kl is not None:
                    with th.no_grad():
                        approx_kl_div = th.mean(rollout_data.old_log_probs - log_probs).item()
                        approx_kl_divs.append(approx_kl_div)
                
                # Optimization step
                self.policy.optimizer.zero_grad()
                loss.backward()
                
                # Clip gradients
                th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.policy.optimizer.step()
            
            # Log values
            self.logger.record("train/entropy_loss", np.mean(entropy_losses))
            self.logger.record("train/policy_gradient_loss", np.mean(pg_losses))
            self.logger.record("train/value_loss", np.mean(value_losses))
            self.logger.record("train/clip_fraction", np.mean(clip_fractions))
            self.logger.record("train/loss", loss.item())
            self.logger.record("train/approx_kl", np.mean(approx_kl_divs) if len(approx_kl_divs) > 0 else 0)
            
            # Early stopping based on KL divergence
            if self.target_kl is not None and np.mean(approx_kl_divs) > 1.5 * self.target_kl:
                self.logger.record("train/early_stopping", epoch)
                if self.verbose >= 1:
                    print(f"Early stopping at step {epoch} due to reaching max KL: {np.mean(approx_kl_divs):.2f}")
                continue_training = False
                break
        
        # Reset clip range if using dynamic adjustment
        if self.dynamic_clip_range:
            self.clip_range = self.original_clip_range
            
        self._n_updates += self.n_epochs
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        
    def _setup_model(self) -> None:
        """
        Set up the model and initialize all necessary components.
        This is overridden to use the CryptoActorCriticPolicy by default.
        """
        # Use CryptoActorCriticPolicy by default if policy is "MlpPolicy"
        if self.policy == "MlpPolicy":
            self.policy = CryptoActorCriticPolicy
            
        # Call parent method
        super(CryptoPPO, self)._setup_model() 