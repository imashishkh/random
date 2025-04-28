from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .models import ExitStrategyType


@dataclass
class ExitStrategyConfig:
    """Configuration for a specific exit strategy"""
    strategy_type: ExitStrategyType
    parameters: Dict = field(default_factory=dict)  # Strategy-specific parameters


@dataclass
class GlobalRiskParameters:
    """Global risk parameters that apply across all positions"""
    
    # Maximum allowed drawdown (as percentage of account)
    max_drawdown_percent: float = 0.05  # 5%
    
    # Maximum exposure as percentage of account
    max_exposure_percent: float = 0.50  # 50%
    
    # Maximum positions allowed simultaneously
    max_positions: int = 20
    
    # Default risk per trade (percentage of account)
    default_risk_per_trade: float = 0.01  # 1%
    
    # Circuit breaker parameters
    circuit_breaker_enabled: bool = True
    daily_loss_circuit_breaker: float = 0.03  # 3% daily loss triggers a pause
    
    # Default stop-loss parameters
    default_stop_loss_config: ExitStrategyConfig = field(default_factory=lambda: ExitStrategyConfig(
        strategy_type=ExitStrategyType.TRAILING_STOP_LOSS,
        parameters={"trail_percentage": 0.02, "activation_percentage": 0.01}
    ))
    
    # Default take-profit parameters
    default_take_profit_config: ExitStrategyConfig = field(default_factory=lambda: ExitStrategyConfig(
        strategy_type=ExitStrategyType.SCALED_EXIT,
        parameters={
            "base_percentage": 0.03,
            "scale_factor": 2.0,
            "levels": 3
        }
    ))
    
    # Default parameters for volatility-based exits
    default_atr_multiplier: float = 2.5
    default_atr_period: int = 14


@dataclass
class StrategyExitConfig:
    """Configuration for a specific trading strategy's exit parameters"""
    
    # Strategy identifier
    strategy_id: str
    
    # Override global risk percentage for this strategy
    risk_percent_override: Optional[float] = None
    
    # Stop-loss configuration for this strategy
    stop_loss_config: Optional[ExitStrategyConfig] = None
    
    # Take-profit configuration for this strategy
    take_profit_config: Optional[ExitStrategyConfig] = None
    
    # Strategy-specific exit parameters
    exit_params: Dict = field(default_factory=dict)
    
    def get_stop_loss_config(self, global_params: GlobalRiskParameters) -> ExitStrategyConfig:
        """Get stop-loss config, falling back to global if not specified"""
        return self.stop_loss_config or global_params.default_stop_loss_config
        
    def get_take_profit_config(self, global_params: GlobalRiskParameters) -> ExitStrategyConfig:
        """Get take-profit config, falling back to global if not specified"""
        return self.take_profit_config or global_params.default_take_profit_config
        
    def get_risk_percent(self, global_params: GlobalRiskParameters) -> float:
        """Get risk percentage, falling back to global if not specified"""
        return self.risk_percent_override or global_params.default_risk_per_trade


@dataclass
class ExitManagerConfig:
    """Overall configuration for exit management"""
    
    # Global risk parameters
    global_params: GlobalRiskParameters = field(default_factory=GlobalRiskParameters)
    
    # Strategy-specific configurations
    strategy_configs: Dict[str, StrategyExitConfig] = field(default_factory=dict)
    
    # Update interval in milliseconds
    update_interval_ms: int = 1000
    
    # Maximum retries for order operations
    max_order_retries: int = 3
    
    # Exponential backoff parameters for retries
    retry_backoff_factor: float = 1.5
    retry_initial_delay_ms: int = 100
    
    # Circuit breaker parameters
    circuit_breaker_threshold: int = 5  # Number of failures to trigger breaker
    circuit_breaker_reset_time_ms: int = 300000  # 5 minutes
    
    def get_strategy_config(self, strategy_id: str) -> StrategyExitConfig:
        """Get configuration for a specific strategy, creating default if needed"""
        if strategy_id not in self.strategy_configs:
            self.strategy_configs[strategy_id] = StrategyExitConfig(strategy_id=strategy_id)
        return self.strategy_configs[strategy_id] 