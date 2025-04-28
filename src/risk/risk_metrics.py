"""
Risk metrics calculation for portfolio risk management.

This module implements various risk metrics calculations for portfolio risk management,
including Value at Risk (VaR), Conditional Value at Risk (CVaR), and other measures.
"""

import logging
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union, Any
from datetime import datetime, timedelta
from scipy import stats

from .position_monitor import Position, PositionStatus, PositionSide

# Configure logger
logger = logging.getLogger(__name__)


class RiskMetricsCalculator:
    """
    Calculator for various risk metrics on position and portfolio level.
    
    This class implements various risk metrics calculations including:
    - Value at Risk (VaR) using multiple methods
    - Conditional Value at Risk (CVaR)
    - Exposure analysis
    - Concentration risk
    - Correlation-adjusted metrics
    """
    
    def __init__(self, price_history_window: int = 100):
        """
        Initialize the risk metrics calculator.
        
        Args:
            price_history_window: Number of data points to use for historical calculations
        """
        self.price_history_window = price_history_window
        self.price_history: Dict[str, List[float]] = {}
        self.return_history: Dict[str, List[float]] = {}
        self.var_confidence_levels = [0.95, 0.99]  # 95% and 99% confidence levels
        self.position_correlations: Dict[str, Dict[str, float]] = {}
    
    def update_price_history(self, symbol: str, price: float) -> None:
        """
        Update price history for a symbol.
        
        Args:
            symbol: Trading symbol
            price: Current price
        """
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.return_history[symbol] = []
        
        # Add price to history
        self.price_history[symbol].append(price)
        
        # Keep only the most recent window
        if len(self.price_history[symbol]) > self.price_history_window:
            self.price_history[symbol].pop(0)
        
        # Calculate returns if we have at least 2 prices
        if len(self.price_history[symbol]) >= 2:
            prev_price = self.price_history[symbol][-2]
            current_price = self.price_history[symbol][-1]
            
            # Log return: ln(current_price / prev_price)
            log_return = math.log(current_price / prev_price)
            self.return_history[symbol].append(log_return)
            
            # Keep only the most recent window
            if len(self.return_history[symbol]) > self.price_history_window - 1:
                self.return_history[symbol].pop(0)
    
    def calculate_historical_var(
        self, 
        positions: List[Position], 
        confidence_level: float = 0.95, 
        time_horizon: int = 1
    ) -> Dict[str, float]:
        """
        Calculate Value at Risk using historical method.
        
        Args:
            positions: List of positions
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            time_horizon: Time horizon in days
            
        Returns:
            Dictionary with VaR results
        """
        # Filter open positions
        open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
        
        if not open_positions:
            return {"var": 0.0, "method": "historical", "confidence_level": confidence_level}
        
        # Build portfolio returns
        position_values = {}
        historical_returns = {}
        
        # Calculate position values
        for position in open_positions:
            symbol = position.symbol
            value = position.quantity * position.current_price
            position_values[symbol] = value
            
            # Skip if we don't have enough return history
            if symbol not in self.return_history or len(self.return_history[symbol]) < 10:
                logger.warning(f"Insufficient return history for {symbol}, skipping in VaR calculation")
                continue
            
            # Get return history
            returns = self.return_history[symbol]
            historical_returns[symbol] = returns
        
        if not historical_returns:
            logger.warning("No historical returns available for VaR calculation")
            return {"var": 0.0, "method": "historical", "confidence_level": confidence_level}
        
        # Calculate portfolio returns
        portfolio_value = sum(position_values.values())
        
        if portfolio_value == 0:
            return {"var": 0.0, "method": "historical", "confidence_level": confidence_level}
        
        # Calculate weighted portfolio returns
        portfolio_returns = []
        
        # Find the minimum length of return histories
        min_history_length = min(len(returns) for returns in historical_returns.values())
        
        # Calculate portfolio returns for each historical point
        for i in range(min_history_length):
            # Weighted sum of returns based on position values
            weighted_return = sum(
                (historical_returns[symbol][i] * position_values[symbol] / portfolio_value)
                for symbol in historical_returns
            )
            portfolio_returns.append(weighted_return)
        
        # Convert to numpy array
        portfolio_returns = np.array(portfolio_returns)
        
        # Calculate VaR as the quantile of returns
        var_percentile = 1 - confidence_level
        var_return = np.quantile(portfolio_returns, var_percentile)
        
        # Scale for time horizon (square root of time rule)
        var_return_scaled = var_return * math.sqrt(time_horizon)
        
        # Calculate VaR in portfolio value terms
        var_value = portfolio_value * (1 - math.exp(var_return_scaled))
        
        return {
            "var": var_value,
            "var_percent": var_value / portfolio_value * 100 if portfolio_value > 0 else 0,
            "method": "historical",
            "confidence_level": confidence_level,
            "time_horizon": time_horizon,
            "portfolio_value": portfolio_value
        }
    
    def calculate_parametric_var(
        self, 
        positions: List[Position], 
        confidence_level: float = 0.95, 
        time_horizon: int = 1
    ) -> Dict[str, float]:
        """
        Calculate Value at Risk using parametric method (normal distribution).
        
        Args:
            positions: List of positions
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            time_horizon: Time horizon in days
            
        Returns:
            Dictionary with VaR results
        """
        # Filter open positions
        open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
        
        if not open_positions:
            return {"var": 0.0, "method": "parametric", "confidence_level": confidence_level}
        
        # Calculate position values and collect return histories
        position_values = {}
        return_stdevs = {}
        
        for position in open_positions:
            symbol = position.symbol
            value = position.quantity * position.current_price
            position_values[symbol] = value
            
            # Skip if we don't have enough return history
            if symbol not in self.return_history or len(self.return_history[symbol]) < 10:
                logger.warning(f"Insufficient return history for {symbol}, skipping in VaR calculation")
                continue
            
            # Calculate standard deviation of returns
            returns = np.array(self.return_history[symbol])
            return_stdevs[symbol] = np.std(returns)
        
        if not return_stdevs:
            logger.warning("No return standard deviations available for VaR calculation")
            return {"var": 0.0, "method": "parametric", "confidence_level": confidence_level}
        
        # Calculate portfolio value
        portfolio_value = sum(position_values.values())
        
        if portfolio_value == 0:
            return {"var": 0.0, "method": "parametric", "confidence_level": confidence_level}
        
        # Calculate portfolio volatility (simplified - assumes zero correlation)
        portfolio_variance = sum(
            (position_values[symbol] / portfolio_value) ** 2 * return_stdevs[symbol] ** 2
            for symbol in return_stdevs
        )
        portfolio_volatility = math.sqrt(portfolio_variance)
        
        # Calculate VaR using normal distribution
        # Note: stats.norm.ppf(1 - confidence_level) gives the z-score for the confidence level
        z_score = stats.norm.ppf(1 - confidence_level)
        
        # Scale volatility for time horizon
        scaled_volatility = portfolio_volatility * math.sqrt(time_horizon)
        
        # Calculate VaR
        var_value = portfolio_value * (1 - math.exp(z_score * scaled_volatility))
        
        return {
            "var": var_value,
            "var_percent": var_value / portfolio_value * 100 if portfolio_value > 0 else 0,
            "method": "parametric",
            "confidence_level": confidence_level,
            "time_horizon": time_horizon,
            "portfolio_value": portfolio_value,
            "portfolio_volatility": portfolio_volatility
        }
    
    def calculate_monte_carlo_var(
        self, 
        positions: List[Position], 
        confidence_level: float = 0.95, 
        time_horizon: int = 1,
        simulations: int = 10000
    ) -> Dict[str, float]:
        """
        Calculate Value at Risk using Monte Carlo simulation.
        
        Args:
            positions: List of positions
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            time_horizon: Time horizon in days
            simulations: Number of Monte Carlo simulations
            
        Returns:
            Dictionary with VaR results
        """
        # Filter open positions
        open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
        
        if not open_positions:
            return {"var": 0.0, "method": "monte_carlo", "confidence_level": confidence_level}
        
        # Calculate position values and collect return statistics
        position_values = {}
        return_means = {}
        return_stdevs = {}
        
        for position in open_positions:
            symbol = position.symbol
            value = position.quantity * position.current_price
            position_values[symbol] = value
            
            # Skip if we don't have enough return history
            if symbol not in self.return_history or len(self.return_history[symbol]) < 10:
                logger.warning(f"Insufficient return history for {symbol}, skipping in VaR calculation")
                continue
            
            # Calculate mean and standard deviation of returns
            returns = np.array(self.return_history[symbol])
            return_means[symbol] = np.mean(returns)
            return_stdevs[symbol] = np.std(returns)
        
        if not return_stdevs:
            logger.warning("No return statistics available for VaR calculation")
            return {"var": 0.0, "method": "monte_carlo", "confidence_level": confidence_level}
        
        # Calculate portfolio value
        portfolio_value = sum(position_values.values())
        
        if portfolio_value == 0:
            return {"var": 0.0, "method": "monte_carlo", "confidence_level": confidence_level}
        
        # Generate correlated random returns (simplified: assuming zero correlation)
        np.random.seed(42)  # For reproducibility
        
        # Simulate portfolio returns
        portfolio_returns = np.zeros(simulations)
        
        for symbol in return_means:
            # Calculate weight of this position in the portfolio
            weight = position_values[symbol] / portfolio_value
            
            # Generate random returns
            random_returns = np.random.normal(
                loc=return_means[symbol] * time_horizon,
                scale=return_stdevs[symbol] * math.sqrt(time_horizon),
                size=simulations
            )
            
            # Add to portfolio returns (weighted)
            portfolio_returns += weight * random_returns
        
        # Calculate simulated portfolio values
        simulated_values = portfolio_value * np.exp(portfolio_returns)
        
        # Calculate losses
        losses = portfolio_value - simulated_values
        
        # Sort losses and find VaR
        sorted_losses = np.sort(losses)
        var_index = int(simulations * confidence_level)
        var_value = sorted_losses[var_index]
        
        # Calculate CVaR (average loss beyond VaR)
        cvar_losses = sorted_losses[var_index:]
        cvar_value = np.mean(cvar_losses) if len(cvar_losses) > 0 else var_value
        
        return {
            "var": var_value,
            "var_percent": var_value / portfolio_value * 100 if portfolio_value > 0 else 0,
            "cvar": cvar_value,
            "cvar_percent": cvar_value / portfolio_value * 100 if portfolio_value > 0 else 0,
            "method": "monte_carlo",
            "confidence_level": confidence_level,
            "time_horizon": time_horizon,
            "simulations": simulations,
            "portfolio_value": portfolio_value
        }
    
    def calculate_portfolio_risk_metrics(
        self, 
        positions: List[Position],
        calculate_var: bool = True,
        var_methods: List[str] = ["historical", "parametric", "monte_carlo"]
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive risk metrics for a portfolio.
        
        Args:
            positions: List of positions
            calculate_var: Whether to calculate VaR metrics
            var_methods: VaR calculation methods to use
            
        Returns:
            Dictionary with risk metrics
        """
        # Filter open positions
        open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
        
        # Calculate basic metrics
        total_positions = len(open_positions)
        portfolio_value = sum(p.quantity * p.current_price for p in open_positions)
        
        # Calculate P&L
        total_unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
        total_realized_pnl = sum(p.realized_pnl for p in positions)
        total_pnl = total_unrealized_pnl + total_realized_pnl
        
        # Group positions by symbol
        positions_by_symbol = {}
        for position in open_positions:
            if position.symbol not in positions_by_symbol:
                positions_by_symbol[position.symbol] = []
            positions_by_symbol[position.symbol].append(position)
        
        # Calculate exposure metrics
        exposure_metrics = self._calculate_exposure_metrics(positions_by_symbol, portfolio_value)
        
        # Calculate VaR metrics if requested
        var_metrics = {}
        if calculate_var:
            for method in var_methods:
                for confidence_level in self.var_confidence_levels:
                    if method == "historical":
                        var_result = self.calculate_historical_var(
                            open_positions, confidence_level, time_horizon=1
                        )
                    elif method == "parametric":
                        var_result = self.calculate_parametric_var(
                            open_positions, confidence_level, time_horizon=1
                        )
                    elif method == "monte_carlo":
                        var_result = self.calculate_monte_carlo_var(
                            open_positions, confidence_level, time_horizon=1
                        )
                    else:
                        logger.warning(f"Unknown VaR method: {method}")
                        continue
                    
                    key = f"var_{method}_{int(confidence_level * 100)}"
                    var_metrics[key] = var_result
        
        # Calculate max drawdown
        max_drawdown = max([p.max_drawdown for p in positions], default=0.0)
        
        # Build result dictionary
        result = {
            "timestamp": datetime.utcnow(),
            "total_positions": total_positions,
            "portfolio_value": portfolio_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "total_pnl": total_pnl,
            "pnl_percent": (total_pnl / portfolio_value * 100) if portfolio_value > 0 else 0,
            "max_drawdown": max_drawdown,
            "exposure": exposure_metrics
        }
        
        # Add VaR metrics if calculated
        if var_metrics:
            result["var"] = var_metrics
        
        return result
    
    def _calculate_exposure_metrics(
        self, 
        positions_by_symbol: Dict[str, List[Position]], 
        portfolio_value: float
    ) -> Dict[str, Any]:
        """
        Calculate exposure metrics for the portfolio.
        
        Args:
            positions_by_symbol: Positions grouped by symbol
            portfolio_value: Total portfolio value
            
        Returns:
            Dictionary with exposure metrics
        """
        # Calculate exposure by symbol
        exposure_by_symbol = {}
        for symbol, positions in positions_by_symbol.items():
            long_positions = [p for p in positions if p.side == PositionSide.LONG]
            short_positions = [p for p in positions if p.side == PositionSide.SHORT]
            
            long_exposure = sum(p.quantity * p.current_price for p in long_positions)
            short_exposure = sum(p.quantity * p.current_price for p in short_positions)
            net_exposure = long_exposure - short_exposure
            gross_exposure = long_exposure + short_exposure
            
            exposure_by_symbol[symbol] = {
                "long": long_exposure,
                "short": short_exposure,
                "net": net_exposure,
                "gross": gross_exposure,
                "net_percent": (net_exposure / portfolio_value * 100) if portfolio_value > 0 else 0,
                "gross_percent": (gross_exposure / portfolio_value * 100) if portfolio_value > 0 else 0
            }
        
        # Calculate overall exposure
        total_long = sum(data["long"] for data in exposure_by_symbol.values())
        total_short = sum(data["short"] for data in exposure_by_symbol.values())
        total_net = total_long - total_short
        total_gross = total_long + total_short
        
        # Sort by absolute exposure
        sorted_exposures = sorted(
            exposure_by_symbol.items(),
            key=lambda x: abs(x[1]["net"]),
            reverse=True
        )
        
        # Calculate concentration metrics
        top_exposures = {}
        
        # Top 3 exposures
        for i, (symbol, data) in enumerate(sorted_exposures[:3], 1):
            top_exposures[f"top_{i}"] = {
                "symbol": symbol,
                "exposure": data["net"],
                "percent": (data["net"] / portfolio_value * 100) if portfolio_value > 0 else 0
            }
        
        return {
            "by_symbol": exposure_by_symbol,
            "total": {
                "long": total_long,
                "short": total_short,
                "net": total_net,
                "gross": total_gross,
                "net_percent": (total_net / portfolio_value * 100) if portfolio_value > 0 else 0,
                "gross_percent": (total_gross / portfolio_value * 100) if portfolio_value > 0 else 0,
                "long_percent": (total_long / portfolio_value * 100) if portfolio_value > 0 else 0,
                "short_percent": (total_short / portfolio_value * 100) if portfolio_value > 0 else 0
            },
            "concentration": {
                "top_exposures": top_exposures,
                "herfindahl_index": self._calculate_herfindahl_index(
                    [data["net"] for _, data in exposure_by_symbol.items()]
                )
            }
        }
    
    def _calculate_herfindahl_index(self, exposures: List[float]) -> float:
        """
        Calculate Herfindahl index for concentration risk.
        
        Args:
            exposures: List of exposures
            
        Returns:
            Herfindahl index value
        """
        # Handle empty exposures
        if not exposures:
            return 0.0
        
        # Calculate absolute exposures
        abs_exposures = [abs(e) for e in exposures]
        total_exposure = sum(abs_exposures)
        
        # Handle zero total exposure
        if total_exposure == 0:
            return 0.0
        
        # Calculate normalized squared exposures
        squared_shares = [(e / total_exposure) ** 2 for e in abs_exposures]
        
        # Herfindahl index
        return sum(squared_shares)
    
    def calculate_correlation_matrix(self, min_history_length: int = 30) -> Dict[str, Dict[str, float]]:
        """
        Calculate correlation matrix for all symbols with return history.
        
        Args:
            min_history_length: Minimum length of return history required
            
        Returns:
            Dictionary with correlation matrix
        """
        # Filter symbols with sufficient history
        valid_symbols = [
            symbol for symbol, returns in self.return_history.items()
            if len(returns) >= min_history_length
        ]
        
        correlations = {}
        
        # Calculate correlations for each pair
        for symbol1 in valid_symbols:
            correlations[symbol1] = {}
            
            for symbol2 in valid_symbols:
                # Get return histories
                returns1 = np.array(self.return_history[symbol1])[-min_history_length:]
                returns2 = np.array(self.return_history[symbol2])[-min_history_length:]
                
                # Calculate correlation
                correlation, _ = stats.pearsonr(returns1, returns2)
                correlations[symbol1][symbol2] = correlation
        
        # Store the correlation matrix
        self.position_correlations = correlations
        
        return correlations 