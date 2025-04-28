import unittest
from unittest.mock import patch, MagicMock
import json
import os
import datetime
import pandas as pd
import numpy as np

from src.market_adaptation.adaptation_strategy import AdaptationStrategy


class TestAdaptationStrategy(unittest.TestCase):
    
    def setUp(self):
        # Create a sample rules file path
        self.rules_file = "src/market_adaptation/sample_adaptation_rules.json"
        
        # Sample parameters dictionary
        self.strategy_params = {
            "position_size": 0.1,
            "stop_loss": 0.02,
            "take_profit": 0.03,
            "entry_threshold": 0.001,
            "exit_threshold": 0.002
        }
        
        # Create adaptation strategy instance
        self.adaptation = AdaptationStrategy(rules_file=self.rules_file)
        
    def test_initialization(self):
        """Test proper initialization of the AdaptationStrategy class"""
        self.assertIsNotNone(self.adaptation.rules)
        self.assertIsInstance(self.adaptation.rules, dict)
        self.assertIn('risk_adjustment', self.adaptation.rules)
        self.assertIn('volatility_adjustment', self.adaptation.rules)
        self.assertIn('trend_adjustment', self.adaptation.rules)
        self.assertIn('time_based_adjustment', self.adaptation.rules)
        self.assertIn('regime_specific_settings', self.adaptation.rules)
        
    def test_apply_risk_adjustment(self):
        """Test risk adjustment based on market regime"""
        # Test for regime 0 (high volatility/bearish)
        params = self.strategy_params.copy()
        adjusted_params = self.adaptation.apply_risk_adjustment(params, current_regime=0)
        
        # Risk factor for regime 0 should be 0.5 according to our sample rules
        self.assertAlmostEqual(adjusted_params["position_size"], params["position_size"] * 0.5)
        
        # Test for regime 2 (low volatility/bullish)
        params = self.strategy_params.copy()
        adjusted_params = self.adaptation.apply_risk_adjustment(params, current_regime=2)
        
        # Risk factor for regime 2 should be 1.2 according to our sample rules
        self.assertAlmostEqual(adjusted_params["position_size"], params["position_size"] * 1.2)
        
    def test_apply_volatility_adjustment(self):
        """Test volatility-based parameter adjustments"""
        params = self.strategy_params.copy()
        current_volatility = 0.02  # Higher than baseline 0.01
        
        adjusted_params = self.adaptation.apply_volatility_adjustment(
            params, current_volatility=current_volatility
        )
        
        # Should apply high volatility adjustments
        self.assertNotEqual(adjusted_params["stop_loss"], params["stop_loss"])
        self.assertNotEqual(adjusted_params["take_profit"], params["take_profit"])
        
    def test_apply_trend_adjustment(self):
        """Test trend-based parameter adjustments"""
        params = self.strategy_params.copy()
        
        # Test uptrend adjustment
        adjusted_params = self.adaptation.apply_trend_adjustment(params, trend="uptrend")
        self.assertAlmostEqual(adjusted_params["position_size"], params["position_size"] * 1.2)
        self.assertAlmostEqual(adjusted_params["take_profit"], params["take_profit"] * 1.3)
        
        # Test downtrend adjustment
        params = self.strategy_params.copy()
        adjusted_params = self.adaptation.apply_trend_adjustment(params, trend="downtrend")
        self.assertAlmostEqual(adjusted_params["position_size"], params["position_size"] * 0.8)
        
    def test_apply_time_based_adjustment(self):
        """Test time-based parameter adjustments"""
        params = self.strategy_params.copy()
        
        # Mock datetime to simulate a Monday at 9am
        mock_datetime = MagicMock()
        mock_datetime.now.return_value.hour = 9
        mock_datetime.now.return_value.weekday.return_value = 0  # Monday
        
        with patch('src.market_adaptation.adaptation_strategy.datetime', mock_datetime):
            adjusted_params = self.adaptation.apply_time_based_adjustment(params)
            
            # Should apply both hour-based (9am) and day-based (Monday) adjustments
            # Hour adjustment: factor 1.1, Day adjustment: factor 0.8
            # Combined effect: 1.1 * 0.8 = 0.88
            self.assertAlmostEqual(
                adjusted_params["position_size"], 
                params["position_size"] * 1.1 * 0.8
            )
    
    def test_apply_regime_specific_adjustment(self):
        """Test regime-specific parameter adjustments"""
        params = self.strategy_params.copy()
        
        # Test for regime 0
        adjusted_params = self.adaptation.apply_regime_specific_adjustment(params, current_regime=0)
        
        # Should apply regime 0 specific settings
        self.assertEqual(adjusted_params["entry_threshold"], 0.002)
        self.assertEqual(adjusted_params["exit_threshold"], 0.005)
        self.assertEqual(adjusted_params["stop_loss"], 0.015)
        self.assertEqual(adjusted_params["take_profit"], 0.02)
        
    def test_adapt_strategy_parameters(self):
        """Test the full adaptation process with all adjustments"""
        params = self.strategy_params.copy()
        
        market_data = {
            "current_regime": 1,
            "volatility": 0.008,
            "trend": "uptrend"
        }
        
        # Mock datetime
        mock_datetime = MagicMock()
        mock_datetime.now.return_value.hour = 10
        mock_datetime.now.return_value.weekday.return_value = 2  # Wednesday
        
        with patch('src.market_adaptation.adaptation_strategy.datetime', mock_datetime):
            adapted_params = self.adaptation.adapt_strategy_parameters(params, market_data)
            
            # Verify adaptation has been applied
            self.assertNotEqual(adapted_params, params)
            
            # Check statistics
            stats = self.adaptation.get_adaptation_statistics()
            self.assertEqual(stats["num_adaptations"], 1)
            self.assertIsNotNone(stats["last_adaptation_time"])
    
    def test_enforce_parameter_bounds(self):
        """Test enforcing parameter bounds"""
        params = {
            "position_size": 0.5,  # This will exceed max bound
            "stop_loss": 0.001,    # This will be below min bound
            "take_profit": 0.03
        }
        
        bounds = {
            "position_size": {"min": 0.01, "max": 0.3},
            "stop_loss": {"min": 0.005, "max": 0.05},
            "take_profit": {"min": 0.01, "max": 0.1}
        }
        
        bounded_params = self.adaptation.enforce_parameter_bounds(params, bounds)
        
        # Should be capped at bounds
        self.assertEqual(bounded_params["position_size"], 0.3)
        self.assertEqual(bounded_params["stop_loss"], 0.005)
        self.assertEqual(bounded_params["take_profit"], 0.03)  # Unchanged
        
    def test_reset_adaptation_statistics(self):
        """Test resetting adaptation statistics"""
        # First adapt to generate statistics
        params = self.strategy_params.copy()
        market_data = {"current_regime": 1, "volatility": 0.01, "trend": "uptrend"}
        self.adaptation.adapt_strategy_parameters(params, market_data)
        
        # Verify statistics are populated
        stats_before = self.adaptation.get_adaptation_statistics()
        self.assertEqual(stats_before["num_adaptations"], 1)
        
        # Reset statistics
        self.adaptation.reset_adaptation_statistics()
        
        # Verify statistics are reset
        stats_after = self.adaptation.get_adaptation_statistics()
        self.assertEqual(stats_after["num_adaptations"], 0)
        self.assertIsNone(stats_after["last_adaptation_time"])


if __name__ == "__main__":
    unittest.main() 