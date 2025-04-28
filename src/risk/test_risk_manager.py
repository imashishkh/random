"""
Risk Manager Test Script

This script tests the RiskManager with mock position data to validate risk calculations
and position tracking functionality.
"""

import os
import time
import yaml
import logging
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

from .manager import RiskManager
from .position_fetcher import PositionDataFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/risk_config.yaml") -> Dict[str, Any]:
    """
    Load risk configuration from a YAML file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dictionary of configuration parameters
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return {}


def create_mock_positions() -> List[Dict[str, Any]]:
    """
    Create mock position data for testing.
    
    Returns:
        List of mock position dictionaries
    """
    return [
        {
            'symbol': 'BTCUSDT',
            'position_amount': 0.1,
            'entry_price': 45000.0,
            'mark_price': 46000.0,
            'unreal_pnl': 100.0,
            'liquidation_price': 40000.0,
            'leverage': 10,
            'notional_value': 4600.0,  # 0.1 * 46000
            'margin_type': 'isolated',
            'isolated_margin': 460.0,
            'is_auto_add_margin': False,
            'position_side': 'BOTH',
            'break_even_price': 45000.0,
            'timestamp': int(time.time() * 1000)
        },
        {
            'symbol': 'ETHUSDT',
            'position_amount': 1.5,
            'entry_price': 3000.0,
            'mark_price': 2950.0,
            'unreal_pnl': -75.0,
            'liquidation_price': 2700.0,
            'leverage': 5,
            'notional_value': 4425.0,  # 1.5 * 2950
            'margin_type': 'cross',
            'isolated_margin': 0.0,
            'is_auto_add_margin': False,
            'position_side': 'BOTH',
            'break_even_price': 3000.0,
            'timestamp': int(time.time() * 1000)
        },
        {
            'symbol': 'EURUSD',
            'position_amount': 10000.0,
            'entry_price': 1.08,
            'mark_price': 1.09,
            'unreal_pnl': 100.0,
            'liquidation_price': 1.05,
            'leverage': 20,
            'notional_value': 10900.0,  # 10000 * 1.09
            'margin_type': 'cross',
            'isolated_margin': 0.0,
            'is_auto_add_margin': False,
            'position_side': 'BOTH',
            'break_even_price': 1.08,
            'timestamp': int(time.time() * 1000)
        }
    ]


def print_position_summary(positions: List[Dict[str, Any]]) -> None:
    """
    Print a summary of mock positions.
    
    Args:
        positions: List of position dictionaries
    """
    if not positions:
        logger.info("No positions found")
        return
    
    print("\n=== MOCK POSITIONS ===")
    print(f"{'Symbol':<10} {'Size':<10} {'Entry':<10} {'Mark':<10} {'PnL':<10} {'Value':<10} {'Leverage':<8}")
    print("-" * 70)
    
    for pos in positions:
        print(f"{pos['symbol']:<10} {pos['position_amount']:<10g} {pos['entry_price']:<10g} "
              f"{pos['mark_price']:<10g} {pos['unreal_pnl']:<10g} "
              f"{pos['notional_value']:<10g} {pos['leverage']:<8g}")


def print_risk_summary(risk_manager: RiskManager) -> None:
    """
    Print a summary of risk metrics from the risk manager.
    
    Args:
        risk_manager: RiskManager instance
    """
    exposure_summary = risk_manager.get_exposure_summary()
    
    print("\n=== RISK EXPOSURE SUMMARY ===")
    print(f"Total Exposure: ${exposure_summary['total_exposure']:.2f} "
          f"({exposure_summary['total_exposure_ratio']:.2%} of equity)")
    
    print("\nAsset Exposure:")
    for symbol, exposure in exposure_summary['asset_exposure'].items():
        print(f"  {symbol}: ${exposure:.2f} ({exposure/risk_manager.account_balance:.2%} of equity)")
    
    print("\nAsset Class Exposure:")
    for asset_class, exposure in exposure_summary['class_exposure'].items():
        print(f"  {asset_class}: ${exposure:.2f} ({exposure/risk_manager.account_balance:.2%} of equity)")
    
    print(f"\nPosition Count: {exposure_summary['position_count']}")


def print_risk_violations(risk_limits: Dict[str, Any]) -> None:
    """
    Print risk violations.
    
    Args:
        risk_limits: Risk status from check_risk_limits
    """
    violations = risk_limits.get('violations', [])
    
    if not violations:
        print("\nNo risk violations detected")
        return
    
    print("\n=== RISK VIOLATIONS ===")
    for violation in violations:
        vtype = violation['type']
        severity = violation['severity'].upper()
        current = violation['current']
        limit = violation['limit']
        
        if vtype == "global_exposure":
            print(f"[{severity}] Global exposure {current:.2%} exceeds limit {limit:.2%}")
        elif vtype == "symbol_exposure":
            symbol = violation['symbol']
            print(f"[{severity}] {symbol} exposure {current:.2%} exceeds limit {limit:.2%}")


def test_risk_manager():
    """Test the RiskManager with mock position data."""
    # Load configuration
    config = load_config()
    
    # Create account balance (adjust as needed for testing)
    account_balance = 25000.0
    
    # Create RiskManager instance
    risk_manager = RiskManager(account_balance=account_balance, params=config)
    
    # Create mock positions
    mock_positions = create_mock_positions()
    
    # Print mock positions
    print_position_summary(mock_positions)
    
    # Mock the PositionDataFetcher
    with patch('src.risk.position_fetcher.PositionDataFetcher') as mock_fetcher_class:
        mock_fetcher_instance = MagicMock()
        mock_fetcher_instance.fetch_positions.return_value = mock_positions
        mock_fetcher_class.return_value = mock_fetcher_instance
        
        # Update risk manager with mock positions
        risk_manager._update_position_tracking(mock_positions)
        
        # Add positions to risk manager's tracking
        for pos in mock_positions:
            # Determine asset class based on symbol
            if pos['symbol'].endswith('USDT'):
                asset_class = 'crypto'
            elif len(pos['symbol']) == 6 and pos['symbol'][0:3] in ["EUR", "USD", "GBP", "JPY", "AUD", "NZD"]:
                asset_class = 'forex'
            else:
                asset_class = 'other'
            
            # Create position result dict
            position_result = {
                "size": pos['position_amount'],
                "value": pos['notional_value'],
                "risk_amount": pos['notional_value'] / pos['leverage'],
                "risk_percent": (pos['notional_value'] / pos['leverage']) / account_balance,
                "metadata": {
                    "symbol": pos['symbol'],
                    "entry_price": pos['entry_price'],
                    "current_price": pos['mark_price']
                }
            }
            
            # Add position to tracking
            risk_manager.add_position(pos['symbol'], position_result, asset_class)
        
        # Print risk summary
        print_risk_summary(risk_manager)
        
        # Check risk limits
        risk_limits = risk_manager.check_risk_limits(mock_positions)
        print_risk_violations(risk_limits)
        
        # Test adding a position that would exceed limits
        print("\n=== TESTING POSITION VALIDATION ===")
        
        # Create oversized position
        large_position_result = {
            "size": 1.0,
            "value": 50000.0,  # Much larger than our account balance
            "risk_amount": 5000.0,
            "risk_percent": 0.20,
            "metadata": {
                "symbol": "SOLUSDT",
                "entry_price": 100.0,
                "current_price": 100.0
            }
        }
        
        # Validate position (should be adjusted or rejected)
        validated_result = risk_manager.validate_position("SOLUSDT", large_position_result)
        
        print("\nOversized Position:")
        print(f"Original Size: {large_position_result['size']}, Value: ${large_position_result['value']:.2f}")
        print(f"Validated Size: {validated_result['size']}, Value: ${validated_result['value']:.2f}")
        
        if validated_result.get('metadata', {}).get('adjusted', False):
            print(f"Position was adjusted due to: {validated_result['metadata']['adjustment_reason']}")
            if 'adjustment_factor' in validated_result['metadata']:
                print(f"Adjustment factor: {validated_result['metadata']['adjustment_factor']:.2%}")


if __name__ == "__main__":
    test_risk_manager() 