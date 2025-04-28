#!/usr/bin/env python3
"""
Example script that demonstrates how to use RiskManager in a backtesting scenario.
This script simulates a backtest with risk management controls.
"""

import os
import csv
import yaml
import random
import logging
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('backtest_example')


# Mock RiskManager class to avoid import dependencies
class RiskManager:
    """Simplified mock RiskManager for demonstration purposes."""
    
    def __init__(self, account_balance: float = 10000.0, params: Dict[str, Any] = None):
        self.account_balance = account_balance
        self.params = params or {
            "max_risk_per_trade": 0.02,  # 2% max risk per trade
            "max_asset_exposure": 0.1,   # 10% max exposure per asset
            "max_class_exposure": 0.25,  # 25% max exposure per asset class
            "max_global_exposure": 0.6,  # 60% max total exposure
            "circuit_breaker_enabled": True,
            "circuit_breaker_threshold": 0.05,  # 5% drawdown triggers circuit breaker
            "warning_threshold": 0.8,    # 80% of any limit triggers warning
            "danger_threshold": 0.95,    # 95% of any limit triggers danger
        }
        self.positions = []
        self.asset_exposures = {}
        self.class_exposures = {"forex": 0.0, "crypto": 0.0, "stocks": 0.0}
        
    def update_account_balance(self, new_balance: float) -> None:
        """Update the account balance."""
        self.account_balance = new_balance
        
    def update_positions(self, positions: List[Dict[str, Any]]) -> None:
        """Update internal position tracking."""
        self._update_position_tracking(positions)
        
    def _update_position_tracking(self, positions: List[Dict[str, Any]]) -> None:
        """Update internal position tracking."""
        self.positions = positions
        
        # Reset exposures
        self.asset_exposures = {}
        self.class_exposures = {"forex": 0.0, "crypto": 0.0, "stocks": 0.0}
        
        # Calculate exposures
        for position in positions:
            symbol = position["symbol"]
            value = position.get("notional_value", 0)
            if not value and "amount" in position and "current_price" in position:
                value = position["amount"] * position["current_price"]
                
            # Update asset exposure
            self.asset_exposures[symbol] = self.asset_exposures.get(symbol, 0) + value
            
            # Determine asset class based on symbol
            asset_class = "forex"
            if "/" in symbol:
                asset_class = "forex"
            elif symbol.endswith("USDT"):
                asset_class = "crypto"
            elif symbol in ["GOLD", "SILVER", "OIL"]:
                asset_class = "commodities"
                
            # Update class exposure
            self.class_exposures[asset_class] = self.class_exposures.get(asset_class, 0) + value
    
    def get_exposure_summary(self) -> Dict[str, Any]:
        """Get a summary of current risk exposures."""
        total_exposure = sum(self.asset_exposures.values())
        
        return {
            "total_exposure": total_exposure,
            "total_exposure_ratio": total_exposure / self.account_balance if self.account_balance > 0 else 0,
            "asset_exposure": self.asset_exposures,
            "class_exposure": self.class_exposures,
            "position_count": len(self.positions)
        }
    
    def check_risk_limits(self, positions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Check if current positions violate any risk limits."""
        if positions is not None:
            self._update_position_tracking(positions)
            
        violations = []
        exposure_summary = self.get_exposure_summary()
        
        # Check global exposure
        global_limit = self.params.get("max_global_exposure", 0.8)
        global_exposure = exposure_summary["total_exposure_ratio"]
        
        if global_exposure > global_limit:
            violations.append({
                "type": "global_exposure",
                "severity": "critical" if global_exposure > global_limit * 1.1 else "warning",
                "current": global_exposure,
                "limit": global_limit
            })
        
        # Check per-symbol exposure
        max_asset_exposure = self.params.get("max_asset_exposure", 0.1)
        for symbol, exposure in self.asset_exposures.items():
            exposure_ratio = exposure / self.account_balance if self.account_balance > 0 else 0
            symbol_limit = self.params.get("symbol_limits", {}).get(symbol, max_asset_exposure)
            
            if exposure_ratio > symbol_limit:
                violations.append({
                    "type": "symbol_exposure",
                    "symbol": symbol,
                    "severity": "critical" if exposure_ratio > symbol_limit * 1.1 else "warning",
                    "current": exposure_ratio,
                    "limit": symbol_limit
                })
        
        # Return status
        return {
            "status": "violation" if violations else "ok",
            "violations": violations
        }
    
    def is_circuit_breaker_active(self) -> bool:
        """Check if the circuit breaker is currently active."""
        return False  # Simplified mock
        
    def add_position(self, symbol: str, position_data: Dict[str, Any], asset_class: str = None) -> None:
        """Add a position to tracking."""
        # This is a simplified mock implementation
        self.positions.append({
            "symbol": symbol,
            "amount": position_data.get("size", 0),
            "entry_price": position_data.get("metadata", {}).get("entry_price", 0),
            "current_price": position_data.get("metadata", {}).get("current_price", 0),
            "notional_value": position_data.get("value", 0),
            "pnl": 0
        })
        self._update_position_tracking(self.positions)
        
    def validate_position(self, symbol: str, position_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and potentially adjust a position before execution."""
        # Check if adding this position would violate risk limits
        test_position = {
            "symbol": symbol,
            "amount": position_data.get("size", 0),
            "entry_price": position_data.get("metadata", {}).get("entry_price", 0),
            "current_price": position_data.get("metadata", {}).get("current_price", 0),
            "notional_value": position_data.get("value", 0),
            "pnl": 0
        }
        
        test_positions = self.positions + [test_position]
        risk_status = self.check_risk_limits(test_positions)
        
        if not risk_status.get("violations", []):
            return position_data  # No violations, position is valid
            
        # Position violates limits, adjust it
        adjustment_factor = 0.5  # Simplified: just reduce by half
        
        adjusted_position = position_data.copy()
        adjusted_position["size"] = position_data["size"] * adjustment_factor
        adjusted_position["value"] = position_data["value"] * adjustment_factor
        adjusted_position["risk_amount"] = position_data.get("risk_amount", 0) * adjustment_factor
        
        if "metadata" not in adjusted_position:
            adjusted_position["metadata"] = {}
            
        adjusted_position["metadata"]["adjusted"] = True
        adjusted_position["metadata"]["adjustment_factor"] = adjustment_factor
        adjusted_position["metadata"]["adjustment_reason"] = "Risk limit violation"
        
        return adjusted_position


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        logger.warning(f"Configuration file not found: {config_path}")
        return {}
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def generate_sample_price_data(
    start_date: datetime,
    end_date: datetime,
    symbols: List[str],
    interval_minutes: int = 60
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generate sample price data for backtesting.
    In a real application, you would load historical data from a file or API.
    """
    price_data = {symbol: [] for symbol in symbols}
    current_date = start_date
    
    # Generate random starting prices for each symbol
    base_prices = {
        symbol: random.uniform(1.0, 2.0) for symbol in symbols
    }
    
    # Generate price series with random walks
    while current_date <= end_date:
        for symbol in symbols:
            # Random walk price model with some volatility
            price_change = random.normalvariate(0, 0.002) * base_prices[symbol]
            base_prices[symbol] += price_change
            
            # Ensure price doesn't go negative
            base_prices[symbol] = max(base_prices[symbol], 0.001)
            
            price_data[symbol].append({
                "timestamp": current_date.isoformat(),
                "open": base_prices[symbol],
                "high": base_prices[symbol] * (1 + random.uniform(0, 0.005)),
                "low": base_prices[symbol] * (1 - random.uniform(0, 0.005)),
                "close": base_prices[symbol],
                "volume": random.randint(1000, 10000)
            })
        
        current_date += timedelta(minutes=interval_minutes)
    
    return price_data


class BacktestSimulator:
    """Simple simulator to demonstrate risk management in a backtest scenario."""
    
    def __init__(self, initial_balance: float = 10000.0, params: Dict[str, Any] = None):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.positions = []
        self.trades_history = []
        self.current_time = None
        
        # Initialize risk manager
        self.risk_manager = RiskManager(
            account_balance=initial_balance, 
            params=params or {}
        )
        
        # Performance metrics
        self.metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "rejected_trades": 0,
            "max_drawdown": 0.0,
            "max_balance": initial_balance,
            "min_balance": initial_balance,
            "final_balance": initial_balance,
            "risk_violations": 0,
        }
    
    def update_position_prices(self, current_prices: Dict[str, float]) -> None:
        """Update current prices for all open positions."""
        for position in self.positions:
            symbol = position["symbol"]
            if symbol in current_prices:
                position["current_price"] = current_prices[symbol]
                
                # Calculate PnL
                entry_price = position["entry_price"]
                current_price = position["current_price"]
                amount = position["amount"]
                direction = position["direction"]
                
                # PnL calculation
                if direction == "buy":
                    position["pnl"] = (current_price - entry_price) * amount
                else:  # sell
                    position["pnl"] = (entry_price - current_price) * amount
    
    def get_current_equity(self) -> float:
        """Calculate current equity (balance + unrealized PnL)."""
        unrealized_pnl = sum(position["pnl"] for position in self.positions)
        return self.current_balance + unrealized_pnl
    
    def update_max_drawdown(self) -> None:
        """Update maximum drawdown metric."""
        current_equity = self.get_current_equity()
        self.metrics["max_balance"] = max(self.metrics["max_balance"], current_equity)
        self.metrics["min_balance"] = min(self.metrics["min_balance"], current_equity)
        
        # Calculate current drawdown
        peak = self.metrics["max_balance"]
        if peak > 0:
            current_drawdown = (peak - current_equity) / peak
            self.metrics["max_drawdown"] = max(self.metrics["max_drawdown"], current_drawdown)
    
    def check_potential_trade(
        self, symbol: str, direction: str, amount: float, entry_price: float
    ) -> Dict[str, Any]:
        """Check if a potential trade is within risk limits."""
        # Create a simulated position for the trade we want to make
        potential_position = {
            "symbol": symbol,
            "direction": direction, 
            "amount": amount,
            "entry_price": entry_price,
            "current_price": entry_price,
            "pnl": 0,
            "timestamp": self.current_time.isoformat() if self.current_time else datetime.now().isoformat()
        }
        
        # Check if adding this position would violate risk limits
        augmented_positions = self.positions + [potential_position]
        risk_status = self.risk_manager.check_risk_limits(augmented_positions)
        
        return risk_status
    
    def execute_trade(
        self, timestamp: datetime, symbol: str, direction: str, 
        amount: float, entry_price: float, apply_risk_limits: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a trade in the backtest.
        Returns the trade result with status (accepted/rejected).
        """
        self.current_time = timestamp
        
        # Apply risk management if enabled
        if apply_risk_limits:
            risk_status = self.check_potential_trade(symbol, direction, amount, entry_price)
            
            if risk_status.get("violations", []):
                violations = risk_status["violations"]
                logger.debug(f"Trade rejected at {timestamp}: {violations}")
                
                self.metrics["rejected_trades"] += 1
                trade_result = {
                    "timestamp": timestamp.isoformat(),
                    "symbol": symbol,
                    "direction": direction,
                    "amount": amount,
                    "price": entry_price,
                    "status": "rejected",
                    "reason": "risk_limits",
                    "violations": violations
                }
                
                self.trades_history.append(trade_result)
                return trade_result
        
        # If we're here, either risk checks passed or were disabled
        # Execute the trade
        trade_result = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "price": entry_price,
            "status": "executed",
            "trade_id": f"BT-{len(self.trades_history) + 1}"
        }
        
        # Add to positions list
        position = {
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "entry_price": entry_price,
            "current_price": entry_price,
            "pnl": 0,
            "timestamp": timestamp.isoformat(),
            "trade_id": trade_result["trade_id"]
        }
        
        self.positions.append(position)
        self.trades_history.append(trade_result)
        self.metrics["total_trades"] += 1
        
        # Update the risk manager
        self.risk_manager.update_positions(self.positions)
        
        return trade_result
    
    def close_position(
        self, timestamp: datetime, trade_id: str, exit_price: float
    ) -> Dict[str, Any]:
        """Close an existing position by trade_id."""
        position_index = None
        for i, position in enumerate(self.positions):
            if position["trade_id"] == trade_id:
                position_index = i
                break
        
        if position_index is None:
            logger.warning(f"Attempted to close non-existent position: {trade_id}")
            return {"status": "error", "reason": "position_not_found"}
        
        # Get the position details
        position = self.positions[position_index]
        symbol = position["symbol"]
        direction = position["direction"]
        amount = position["amount"]
        entry_price = position["entry_price"]
        
        # Calculate PnL
        if direction == "buy":
            pnl = (exit_price - entry_price) * amount
        else:  # sell
            pnl = (entry_price - exit_price) * amount
        
        # Update account balance
        self.current_balance += pnl
        
        # Record the closed trade
        close_result = {
            "timestamp": timestamp.isoformat(),
            "trade_id": trade_id,
            "symbol": symbol,
            "close_price": exit_price,
            "pnl": pnl,
            "status": "closed"
        }
        
        # Update metrics
        if pnl > 0:
            self.metrics["winning_trades"] += 1
        else:
            self.metrics["losing_trades"] += 1
        
        # Remove the position
        self.positions.pop(position_index)
        
        # Update the risk manager
        self.risk_manager.update_positions(self.positions)
        
        return close_result
    
    def run_backtest(
        self, price_data: Dict[str, List[Dict[str, Any]]], 
        strategy_func, apply_risk_limits: bool = True
    ) -> Dict[str, Any]:
        """
        Run the backtest using the provided price data and strategy function.
        
        Args:
            price_data: Dictionary mapping symbols to lists of price bars
            strategy_func: Function that returns trade decisions given current state
            apply_risk_limits: Whether to apply risk management limits
            
        Returns:
            Dictionary of backtest results and metrics
        """
        # Determine the common timestamp range across all symbols
        all_timestamps = set()
        for symbol, bars in price_data.items():
            symbol_timestamps = [datetime.fromisoformat(bar["timestamp"]) for bar in bars]
            all_timestamps.update(symbol_timestamps)
        
        # Sort timestamps chronologically
        sorted_timestamps = sorted(all_timestamps)
        
        if not sorted_timestamps:
            logger.error("No price data available for backtest")
            return {"status": "error", "reason": "no_data"}
        
        # Main backtest loop
        for current_time in sorted_timestamps:
            # Get current price for each symbol
            current_prices = {}
            for symbol, bars in price_data.items():
                # Find the bar with the closest timestamp
                matching_bars = [bar for bar in bars 
                                 if datetime.fromisoformat(bar["timestamp"]) == current_time]
                
                if matching_bars:
                    current_prices[symbol] = matching_bars[0]["close"]
            
            # Update position prices with current market data
            self.update_position_prices(current_prices)
            
            # Update metrics
            self.update_max_drawdown()
            
            # Call the strategy function to get trading decisions
            decisions = strategy_func(
                timestamp=current_time,
                current_prices=current_prices,
                positions=self.positions,
                balance=self.current_balance,
                equity=self.get_current_equity(),
                risk_manager=self.risk_manager
            )
            
            # Process trading decisions
            for decision in decisions:
                action = decision.get("action")
                
                if action == "open":
                    # Open a new position
                    self.execute_trade(
                        timestamp=current_time,
                        symbol=decision["symbol"],
                        direction=decision["direction"],
                        amount=decision["amount"],
                        entry_price=current_prices[decision["symbol"]],
                        apply_risk_limits=apply_risk_limits
                    )
                    
                elif action == "close":
                    # Close an existing position
                    self.close_position(
                        timestamp=current_time,
                        trade_id=decision["trade_id"],
                        exit_price=current_prices[decision["symbol"]]
                    )
        
        # Calculate final metrics
        self.metrics["final_balance"] = self.get_current_equity()
        self.metrics["return_pct"] = (self.metrics["final_balance"] / self.initial_balance - 1) * 100
        
        return {
            "status": "completed",
            "metrics": self.metrics,
            "trades_history": self.trades_history,
            "final_positions": self.positions
        }


def simple_strategy(
    timestamp: datetime,
    current_prices: Dict[str, float],
    positions: List[Dict[str, Any]],
    balance: float,
    equity: float,
    risk_manager: RiskManager
) -> List[Dict[str, Any]]:
    """
    A simple example strategy for demonstration purposes.
    This strategy makes random trades based on certain probabilities.
    
    In a real application, you would implement your actual trading strategy here.
    """
    decisions = []
    
    # Example: Get exposure summary from risk manager
    exposure_summary = risk_manager.get_exposure_summary()
    total_exposure = exposure_summary.get("total_exposure", 0)
    
    # Position sizing based on risk limits
    position_size = balance * 0.02  # 2% of balance per trade
    
    # Current positions by symbol
    positions_by_symbol = {pos["symbol"]: pos for pos in positions}
    
    # Simple strategy rules:
    # 1. With 5% probability, open a new random position if exposure < 50%
    if random.random() < 0.05 and total_exposure < 0.5:
        available_symbols = list(current_prices.keys())
        if available_symbols:
            symbol = random.choice(available_symbols)
            
            # Skip if we already have a position in this symbol
            if symbol not in positions_by_symbol:
                direction = random.choice(["buy", "sell"])
                
                decisions.append({
                    "action": "open",
                    "symbol": symbol,
                    "direction": direction,
                    "amount": position_size / current_prices[symbol]
                })
    
    # 2. With 10% probability, close a random position
    if positions and random.random() < 0.1:
        position_to_close = random.choice(positions)
        
        decisions.append({
            "action": "close",
            "trade_id": position_to_close["trade_id"],
            "symbol": position_to_close["symbol"]
        })
    
    return decisions


def export_backtest_results(results: Dict[str, Any], output_file: str) -> None:
    """Export backtest results to CSV file."""
    if not results.get("trades_history"):
        logger.warning("No trades to export")
        return
    
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ["timestamp", "symbol", "direction", "amount", 
                      "price", "status", "pnl", "trade_id"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for trade in results["trades_history"]:
            writer.writerow({field: trade.get(field, "") for field in fieldnames})
    
    logger.info(f"Exported backtest results to {output_file}")


def print_backtest_summary(results: Dict[str, Any]) -> None:
    """Print summary of backtest results."""
    if results["status"] != "completed":
        logger.error(f"Backtest failed: {results.get('reason', 'unknown error')}")
        return
    
    metrics = results["metrics"]
    
    print("\n" + "="*50)
    print("BACKTEST SUMMARY")
    print("="*50)
    print(f"Initial Balance: ${metrics['max_balance']:.2f}")
    print(f"Final Balance:   ${metrics['final_balance']:.2f}")
    print(f"Return:          {metrics['return_pct']:.2f}%")
    print(f"Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
    print("-"*50)
    print(f"Total Trades:    {metrics['total_trades']}")
    print(f"Winning Trades:  {metrics['winning_trades']} " +
          f"({metrics['winning_trades']/metrics['total_trades']*100:.1f}% win rate)" 
          if metrics['total_trades'] > 0 else "(no trades)")
    print(f"Losing Trades:   {metrics['losing_trades']}")
    print(f"Rejected Trades: {metrics['rejected_trades']}")
    print("="*50)


def main():
    """Main entry point for the backtest example."""
    # Load configuration
    config_path = "config/risk_config.yaml"
    config = load_config(config_path)
    
    # Create default config if it doesn't exist
    if not config:
        config = {
            "max_risk_per_trade": 0.02,  # 2% max risk per trade
            "max_asset_exposure": 0.1,   # 10% max exposure per asset
            "max_class_exposure": 0.25,  # 25% max exposure per asset class
            "max_global_exposure": 0.6,  # 60% max total exposure
            "circuit_breaker_enabled": True,
            "circuit_breaker_threshold": 0.05,  # 5% drawdown triggers circuit breaker
            "warning_threshold": 0.8,    # 80% of any limit triggers warning
            "danger_threshold": 0.95,    # 95% of any limit triggers danger
        }
    
    # Backtest parameters
    initial_balance = 10000.0  # $10,000
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 30)
    symbols = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"]
    
    # Generate sample price data
    logger.info("Generating sample price data...")
    price_data = generate_sample_price_data(
        start_date=start_date,
        end_date=end_date,
        symbols=symbols,
        interval_minutes=60  # 1-hour bars
    )
    
    # Initialize backtest simulator
    simulator = BacktestSimulator(
        initial_balance=initial_balance,
        params=config
    )
    
    # Run with risk management
    logger.info("Running backtest with risk management...")
    results_with_risk = simulator.run_backtest(
        price_data=price_data,
        strategy_func=simple_strategy,
        apply_risk_limits=True
    )
    
    # Print results
    print_backtest_summary(results_with_risk)
    
    # Optional: export results to CSV
    export_backtest_results(results_with_risk, "backtest_results_with_risk.csv")
    
    # Run a second backtest without risk management for comparison
    logger.info("Running backtest without risk management for comparison...")
    simulator_no_risk = BacktestSimulator(
        initial_balance=initial_balance
    )
    
    results_no_risk = simulator_no_risk.run_backtest(
        price_data=price_data,
        strategy_func=simple_strategy,
        apply_risk_limits=False
    )
    
    # Print comparison results
    print_backtest_summary(results_no_risk)
    
    # Compare the two approaches
    print("\n" + "="*50)
    print("RISK MANAGEMENT IMPACT")
    print("="*50)
    with_risk_return = results_with_risk["metrics"]["return_pct"]
    no_risk_return = results_no_risk["metrics"]["return_pct"]
    with_risk_drawdown = results_with_risk["metrics"]["max_drawdown"] * 100
    no_risk_drawdown = results_no_risk["metrics"]["max_drawdown"] * 100
    
    print(f"Return with risk management:    {with_risk_return:.2f}%")
    print(f"Return without risk management: {no_risk_return:.2f}%")
    print(f"Drawdown with risk management:    {with_risk_drawdown:.2f}%")
    print(f"Drawdown without risk management: {no_risk_drawdown:.2f}%")
    print("="*50)


if __name__ == "__main__":
    main() 