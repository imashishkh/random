"""
Hybrid RL Model with Rule-Based Safeguards
------------------------------------------
Implements a hybrid model that combines reinforcement learning with rule-based safeguards.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union, List, Tuple, Callable
import logging
import json
import os
import datetime

from ..strategy_evaluation.strategy_evaluator import Strategy
from .safeguards import SafeguardEnsemble


class HybridRLStrategy(Strategy):
    """
    Hybrid strategy that combines reinforcement learning with rule-based safeguards.
    
    This strategy uses a reinforcement learning model for decision making,
    but applies rule-based safeguards to override or modify actions in certain
    market conditions.
    """
    
    def __init__(self, 
                 rl_model: Any,
                 safeguard_ensemble: SafeguardEnsemble,
                 state_preprocessor: Optional[Callable] = None,
                 action_postprocessor: Optional[Callable] = None,
                 name: str = "HybridRLStrategy",
                 log_dir: Optional[str] = None):
        """
        Initialize the hybrid RL strategy.
        
        Args:
            rl_model: Reinforcement learning model with a predict method
            safeguard_ensemble: Ensemble of rule-based safeguards
            state_preprocessor: Function to preprocess state before RL prediction
            action_postprocessor: Function to postprocess action after safeguards
            name: Name of the strategy
            log_dir: Directory to save logs
        """
        super().__init__(name)
        self.rl_model = rl_model
        self.safeguard_ensemble = safeguard_ensemble
        self.state_preprocessor = state_preprocessor
        self.action_postprocessor = action_postprocessor
        
        # Set up logging
        self.log_dir = log_dir
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        self.logger = logging.getLogger(f"{name}_logger")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            # Add file handler
            if log_dir:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = os.path.join(log_dir, f"{name}_{timestamp}.log")
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.INFO)
                self.logger.addHandler(file_handler)
            
            # Add console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            self.logger.addHandler(console_handler)
        
        # State variables
        self.current_state = {}
        self.last_action = None
        self.action_history = []
        self.safeguard_triggers = []
    
    def _preprocess_state(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Preprocess the market data into a state representation.
        
        Args:
            data: Market data DataFrame
            
        Returns:
            Dictionary with state representation
        """
        if self.state_preprocessor:
            return self.state_preprocessor(data)
        
        # Default simple state representation
        state = {}
        
        if len(data) > 0:
            current_data = data.iloc[-1].to_dict()
            state.update(current_data)
            
            # Add some basic derived features if we have enough data
            if len(data) >= 2:
                state['price_change'] = data['close'].iloc[-1] / data['close'].iloc[-2] - 1
            
            if len(data) >= 14:
                # Simple momentum
                state['momentum_14d'] = data['close'].iloc[-1] / data['close'].iloc[-14] - 1
                
                # Simple volatility
                state['volatility_14d'] = data['close'].pct_change().dropna()[-14:].std()
        
        return state
    
    def _get_rl_action(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get action from the RL model.
        
        Args:
            state: Current state representation
            
        Returns:
            Action dictionary from the RL model
        """
        try:
            # This should be adapted to the specific RL model's interface
            raw_action = self.rl_model.predict(state)
            
            # Convert the action to a standardized format
            # This might differ based on the RL framework used
            if isinstance(raw_action, (int, float, np.integer, np.floating)):
                # Simple scalar action (e.g., -1 for sell, 0 for hold, 1 for buy)
                action_type = 'buy' if raw_action > 0 else 'sell' if raw_action < 0 else 'hold'
                action = {
                    'type': action_type,
                    'confidence': abs(float(raw_action)),
                    'position_size': min(1.0, abs(float(raw_action)))
                }
            elif isinstance(raw_action, (list, tuple, np.ndarray)):
                # Vector action (e.g., [action_type_idx, position_size])
                if len(raw_action) >= 2:
                    action_types = ['hold', 'buy', 'sell']
                    action_type_idx = np.argmax(raw_action[:3]) if len(raw_action) >= 3 else int(raw_action[0])
                    action_type = action_types[action_type_idx] if action_type_idx < len(action_types) else 'hold'
                    position_size = float(raw_action[-1])
                    
                    action = {
                        'type': action_type,
                        'position_size': min(1.0, max(0.0, position_size))
                    }
                else:
                    # Fallback for single value in array
                    action_value = float(raw_action[0])
                    action_type = 'buy' if action_value > 0 else 'sell' if action_value < 0 else 'hold'
                    
                    action = {
                        'type': action_type,
                        'position_size': min(1.0, abs(action_value))
                    }
            elif isinstance(raw_action, dict):
                # Already in dictionary format
                action = raw_action.copy()
                
                # Ensure required fields
                if 'type' not in action:
                    action['type'] = 'hold'
                if 'position_size' not in action:
                    action['position_size'] = 0.0
            else:
                self.logger.warning(f"Unexpected RL action format: {type(raw_action)}")
                action = {'type': 'hold', 'position_size': 0.0}
            
            return action
            
        except Exception as e:
            self.logger.error(f"Error getting RL action: {str(e)}")
            return {'type': 'hold', 'position_size': 0.0, 'error': str(e)}
    
    def _postprocess_action(self, action: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply postprocessing to the action.
        
        Args:
            action: Action to postprocess
            state: Current state representation
            
        Returns:
            Postprocessed action
        """
        if self.action_postprocessor:
            return self.action_postprocessor(action, state)
        
        # Convert action type to signal for strategy evaluator
        processed_action = action.copy()
        
        if action['type'] == 'buy':
            processed_action['signal'] = 1.0
        elif action['type'] == 'sell':
            processed_action['signal'] = -1.0
        else:  # hold or none
            processed_action['signal'] = 0.0
        
        return processed_action
    
    def _log_action(self, original_action: Dict[str, Any], modified_action: Dict[str, Any], data: pd.DataFrame):
        """
        Log the action for debugging and analysis.
        
        Args:
            original_action: Original action from RL model
            modified_action: Action after applying safeguards
            data: Current market data
        """
        timestamp = data.iloc[-1]['timestamp'] if len(data) > 0 else datetime.datetime.now()
        
        log_entry = {
            'timestamp': timestamp,
            'original_action': original_action,
            'modified_action': modified_action,
            'safeguard_triggered': 'safeguard_triggered' in modified_action and modified_action['safeguard_triggered'],
            'safeguard_info': modified_action.get('safeguard_info', {}),
            'ensemble_info': modified_action.get('ensemble_info', {})
        }
        
        # Add to action history
        self.action_history.append(log_entry)
        
        # Keep history manageable
        if len(self.action_history) > 1000:
            self.action_history = self.action_history[-1000:]
        
        # Track safeguard triggers
        if log_entry['safeguard_triggered']:
            self.safeguard_triggers.append({
                'timestamp': timestamp,
                'info': log_entry['safeguard_info'],
                'ensemble_info': log_entry['ensemble_info']
            })
        
        # Log the action
        self.logger.info(f"Action: {modified_action['type']}, Size: {modified_action.get('position_size', 0)}")
        
        if log_entry['safeguard_triggered']:
            trigger_info = log_entry['ensemble_info'] if 'ensemble_info' in log_entry else log_entry['safeguard_info']
            self.logger.info(f"Safeguard triggered: {json.dumps(trigger_info, default=str)}")
    
    def predict(self, data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Generate predictions using the hybrid strategy.
        
        Args:
            data: Market data DataFrame
            **kwargs: Additional arguments
            
        Returns:
            DataFrame with predictions
        """
        # Preprocess state
        self.current_state = self._preprocess_state(data)
        
        # Update state with additional info
        self.current_state.update({
            'current_time': data.iloc[-1]['timestamp'] if len(data) > 0 else None,
            'last_action': self.last_action,
            'trade_result': kwargs.get('trade_result', None)
        })
        
        # Get action from RL model
        rl_action = self._get_rl_action(self.current_state)
        
        # Apply safeguards
        safeguarded_action = self.safeguard_ensemble.check_safeguards(
            data, rl_action, self.current_state
        )
        
        # Postprocess action
        final_action = self._postprocess_action(safeguarded_action, self.current_state)
        
        # Log the action
        self._log_action(rl_action, safeguarded_action, data)
        
        # Store last action
        self.last_action = final_action
        
        # Convert to DataFrame
        timestamp = data.iloc[-1]['timestamp'] if len(data) > 0 else datetime.datetime.now()
        
        predictions = pd.DataFrame({
            'timestamp': [timestamp],
            'signal': [final_action['signal']],
            'position_size': [final_action.get('position_size', 1.0)],
            'action_type': [final_action['type']]
        })
        
        return predictions
    
    def get_safeguard_stats(self) -> Dict[str, Any]:
        """
        Get statistics about safeguard triggers.
        
        Returns:
            Dictionary with safeguard statistics
        """
        stats = {
            'total_actions': len(self.action_history),
            'total_triggers': len(self.safeguard_triggers),
            'trigger_rate': len(self.safeguard_triggers) / max(1, len(self.action_history)),
            'safeguards': {}
        }
        
        # Count triggers by safeguard
        safeguard_counts = {}
        
        for trigger in self.safeguard_triggers:
            # Handle ensemble triggers
            if 'ensemble_info' in trigger and trigger['ensemble_info']:
                for safeguard_trigger in trigger['ensemble_info'].get('triggered_safeguards', []):
                    safeguard_name = safeguard_trigger.get('safeguard')
                    if safeguard_name:
                        safeguard_counts[safeguard_name] = safeguard_counts.get(safeguard_name, 0) + 1
            
            # Handle direct triggers
            elif 'info' in trigger and 'safeguard' in trigger['info']:
                safeguard_name = trigger['info']['safeguard']
                safeguard_counts[safeguard_name] = safeguard_counts.get(safeguard_name, 0) + 1
        
        stats['safeguards'] = safeguard_counts
        
        return stats
    
    def save_logs(self, path: str = None) -> str:
        """
        Save action history and safeguard triggers to files.
        
        Args:
            path: Directory to save files (defaults to log_dir)
            
        Returns:
            Path to the saved files
        """
        if not path:
            if not self.log_dir:
                raise ValueError("No log directory specified")
            path = self.log_dir
        
        os.makedirs(path, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save action history
        action_file = os.path.join(path, f"{self.name}_actions_{timestamp}.json")
        with open(action_file, 'w') as f:
            json.dump(self.action_history, f, default=str, indent=2)
        
        # Save safeguard triggers
        trigger_file = os.path.join(path, f"{self.name}_triggers_{timestamp}.json")
        with open(trigger_file, 'w') as f:
            json.dump(self.safeguard_triggers, f, default=str, indent=2)
        
        # Save safeguard stats
        stats_file = os.path.join(path, f"{self.name}_stats_{timestamp}.json")
        with open(stats_file, 'w') as f:
            json.dump(self.get_safeguard_stats(), f, indent=2)
        
        return path 