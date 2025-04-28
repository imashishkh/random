import os
import json
import unittest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch
from src.market_adaptation.adaptation_strategy import AdaptationStrategy


class TestAdaptationStrategy(unittest.TestCase):
    """Test cases for the AdaptationStrategy class"""
    
    def setUp(self):
        """Set up test environment before each test case"""
        # Create a temporary rules file for testing
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        self.rules_file = self.temp_file.name
        
        # Sample rules for testing
        self.test_rules = {
            "cooldown_period": 1800,  # 30 minutes
            "risk_adjustment": {
                "regimes": [
                    {"regime_id": 0, "name": "low_risk", "risk_factor": 1.2},
                    {"regime_id": 1, "name": "normal", "risk_factor": 1.0},
                    {"regime_id": 2, "name": "high_risk", "risk_factor": 0.7}
                ]
            },
            "volatility_adjustment": {
                "baseline_volatility": 0.01,
                "high_volatility_adjustments": {
                    "stop_loss": 0.05,
                    "take_profit": 0.08,
                    "entry_threshold": 0.006
                },
                "low_volatility_adjustments": {
                    "stop_loss": 0.02,
                    "take_profit": 0.04,
                    "entry_threshold": 0.003
                }
            },
            "trend_adjustment": {
                "uptrend": {
                    "position_size_factor": 1.1,
                    "take_profit_factor": 1.2,
                    "stop_loss_factor": 0.9
                },
                "downtrend": {
                    "position_size_factor": 0.9,
                    "take_profit_factor": 0.8,
                    "stop_loss_factor": 1.1
                },
                "ranging": {
                    "position_size_factor": 0.8,
                    "take_profit_factor": 0.9,
                    "stop_loss_factor": 0.9
                }
            },
            "time_based_adjustment": {
                "hours": {
                    "0-6": {"factor": 0.8, "description": "Overnight hours"},
                    "7-15": {"factor": 1.1, "description": "Active hours"},
                    "16-23": {"factor": 0.9, "description": "Evening hours"}
                },
                "days": {
                    "monday": {"factor": 0.9, "description": "Start of week"},
                    "friday": {"factor": 0.9, "description": "End of week"}
                }
            },
            "regime_specific_settings": {
                "regime_0": {
                    "position_size": 0.05,
                    "entry_threshold": 0.003
                },
                "regime_1": {
                    "position_size": 0.03,
                    "entry_threshold": 0.004
                },
                "regime_2": {
                    "position_size": 0.02,
                    "entry_threshold": 0.006
                }
            },
            "parameter_bounds": {
                "position_size": {"min": 0.01, "max": 0.1},
                "entry_threshold": {"min": 0.002, "max": 0.01},
                "stop_loss": {"min": 0.01, "max": 0.1},
                "take_profit": {"min": 0.02, "max": 0.2}
            }
        }
        
        # Write the rules to the temporary file
        with open(self.rules_file, 'w') as f:
            json.dump(self.test_rules, f)
        
        # Create the strategy instance with the temporary rules file
        self.strategy = AdaptationStrategy(rules_file=self.rules_file)
    
    def tearDown(self):
        """Clean up after each test case"""
        # Close and remove the temporary file
        if os.path.exists(self.rules_file):
            os.unlink(self.rules_file)
    
    def test_initialization(self):
        """Test if AdaptationStrategy initializes correctly with rules"""
        self.assertEqual(self.strategy.rules["cooldown_period"], 1800)
        self.assertEqual(len(self.strategy.rules["risk_adjustment"]["regimes"]), 3)
        self.assertEqual(self.strategy.rules["volatility_adjustment"]["baseline_volatility"], 0.01)
        
        # Test initialization without a rules file
        # This should use the default rules file which may not exist in a test environment
        # So we expect it might raise an exception
        try:
            strategy_default = AdaptationStrategy()
            self.assertIsNotNone(strategy_default.rules)
        except FileNotFoundError:
            # This is acceptable if the default rules file doesn't exist
            pass
    
    def test_adapt_strategy_parameters(self):
        """Test adapting strategy parameters based on market data"""
        # Initial parameters
        params = {
            "position_size": 0.04,
            "take_profit": 0.05,
            "stop_loss": 0.03,
            "entry_threshold": 0.004
        }
        
        # Market data for testing
        market_data = {
            "strategy_id": "test_strategy",
            "current_regime": 0,
            "current_volatility": 0.015,  # High volatility
            "baseline_volatility": 0.01,
            "current_trend": "uptrend"
        }
        
        # Adapt parameters
        adapted_params = self.strategy.adapt_strategy_parameters(params, market_data)
        
        # Check that parameters were changed
        self.assertNotEqual(params, adapted_params)
        self.assertEqual(adapted_params["position_size"], 0.05)  # From regime-specific setting
        self.assertEqual(adapted_params["entry_threshold"], 0.003)  # From regime-specific settings
        
        # Check adaptation stats
        stats = self.strategy.get_adaptation_stats()
        self.assertEqual(stats["risk_adjustments"], 1)
        self.assertEqual(stats["volatility_adjustments"], 1)
        self.assertEqual(stats["trend_adjustments"], 1)
        self.assertEqual(stats["time_based_adjustments"], 1)
        self.assertEqual(stats["regime_specific_adjustments"], 1)
    
    def test_apply_risk_adjustment(self):
        """Test the application of risk adjustment"""
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03}
        market_data = {"current_regime": 0}  # Low risk regime
        
        adjusted_params = self.strategy.apply_risk_adjustment(params, market_data)
        
        # Position size should be adjusted by risk factor 1.2
        expected_position_size = 0.05 * 1.2
        self.assertAlmostEqual(adjusted_params["position_size"], expected_position_size, places=10)
        self.assertEqual(adjusted_params["take_profit"], 0.05)  # Unchanged
        self.assertEqual(adjusted_params["stop_loss"], 0.03)    # Unchanged
    
    def test_apply_volatility_adjustment(self):
        """Test the application of volatility adjustment"""
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03, "entry_threshold": 0.004}
        
        # Test high volatility
        market_data = {"current_volatility": 0.02, "baseline_volatility": 0.01}
        adjusted_params = self.strategy.apply_volatility_adjustment(params, market_data)
        
        self.assertEqual(adjusted_params["stop_loss"], 0.05)  # Max of original and high volatility setting
        self.assertEqual(adjusted_params["take_profit"], 0.08)  # Max of original and high volatility setting
        self.assertEqual(adjusted_params["entry_threshold"], 0.006)  # Max of original and high volatility setting
        
        # Test low volatility
        market_data = {"current_volatility": 0.005, "baseline_volatility": 0.01}
        adjusted_params = self.strategy.apply_volatility_adjustment(params, market_data)
        
        self.assertEqual(adjusted_params["stop_loss"], 0.02)  # Min of original and low volatility setting
        self.assertEqual(adjusted_params["take_profit"], 0.04)  # Min of original and low volatility setting
        self.assertEqual(adjusted_params["entry_threshold"], 0.003)  # Min of original and low volatility setting
    
    def test_apply_trend_adjustment(self):
        """Test the application of trend adjustment"""
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03}
        
        # Test uptrend adjustment
        market_data = {"current_trend": "uptrend"}
        adjusted_params = self.strategy.apply_trend_adjustment(params, market_data)
        
        # Use almostEqual for floating point comparisons to handle precision issues
        expected_position_size = 0.05 * 1.1
        expected_take_profit = 0.05 * 1.2
        expected_stop_loss = 0.03 * 0.9
        
        self.assertAlmostEqual(adjusted_params["position_size"], expected_position_size, places=10)
        self.assertAlmostEqual(adjusted_params["take_profit"], expected_take_profit, places=10)
        self.assertAlmostEqual(adjusted_params["stop_loss"], expected_stop_loss, places=10)
        
        # Test downtrend adjustment
        market_data = {"current_trend": "downtrend"}
        adjusted_params = self.strategy.apply_trend_adjustment(params, market_data)
        
        expected_position_size = 0.05 * 0.9
        expected_take_profit = 0.05 * 0.8
        expected_stop_loss = 0.03 * 1.1
        
        self.assertAlmostEqual(adjusted_params["position_size"], expected_position_size, places=10)
        self.assertAlmostEqual(adjusted_params["take_profit"], expected_take_profit, places=10)
        self.assertAlmostEqual(adjusted_params["stop_loss"], expected_stop_loss, places=10)
    
    def test_apply_time_based_adjustment(self):
        """Test the application of time-based adjustment"""
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03}
        
        # Mock time for testing - Monday at 9 AM
        mock_time = datetime(2023, 5, 1, 9, 0)  # Monday at 9 AM
        
        # Use patch to mock the get_current_time method
        with patch.object(self.strategy, 'get_current_time', return_value=mock_time):
            adjusted_params = self.strategy.apply_time_based_adjustment(params)
            
            # Factor should be 1.1 (from hours) * 0.9 (from Monday) = 0.99
            expected_position_size = 0.05 * 0.99
            self.assertAlmostEqual(adjusted_params["position_size"], expected_position_size, places=10)
    
    def test_apply_regime_specific_adjustment(self):
        """Test the application of regime-specific adjustment"""
        params = {"position_size": 0.05, "entry_threshold": 0.004, "take_profit": 0.05, "stop_loss": 0.03}
        
        # Test regime 1 adjustment
        market_data = {"current_regime": 1}
        adjusted_params = self.strategy.apply_regime_specific_adjustment(params, market_data)
        
        self.assertEqual(adjusted_params["position_size"], 0.03)  # From regime-specific settings
        self.assertEqual(adjusted_params["entry_threshold"], 0.004)  # Unchanged since original value is kept when not in settings
        self.assertEqual(adjusted_params["take_profit"], 0.05)  # Unchanged
        self.assertEqual(adjusted_params["stop_loss"], 0.03)  # Unchanged
    
    def test_enforce_parameter_bounds(self):
        """Test enforcing parameter bounds"""
        # Parameters outside of bounds
        params = {
            "position_size": 0.2,  # Above max of 0.1
            "take_profit": 0.01,   # Below min of 0.02
            "stop_loss": 0.005,    # Below min of 0.01
            "entry_threshold": 0.015  # Above max of 0.01
        }
        
        bounded_params = self.strategy.enforce_parameter_bounds(params)
        
        self.assertEqual(bounded_params["position_size"], 0.1)  # Capped at max
        self.assertEqual(bounded_params["take_profit"], 0.02)  # Raised to min
        self.assertEqual(bounded_params["stop_loss"], 0.01)    # Raised to min
        self.assertEqual(bounded_params["entry_threshold"], 0.01)  # Capped at max
        
        # Check that bounds enforcement was counted
        self.assertEqual(self.strategy.adaptation_stats["parameter_bounds_enforced"], 4)
    
    def test_get_adaptation_stats(self):
        """Test getting adaptation statistics"""
        # Initial stats should be all zeros
        stats = self.strategy.get_adaptation_stats()
        self.assertEqual(stats["risk_adjustments"], 0)
        self.assertEqual(stats["volatility_adjustments"], 0)
        self.assertEqual(stats["trend_adjustments"], 0)
        self.assertEqual(stats["total_adaptations"], 0)
        
        # Apply some adaptations to change stats
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03}
        market_data = {"current_regime": 0, "current_trend": "uptrend"}
        
        self.strategy.apply_risk_adjustment(params, market_data)
        self.strategy.apply_trend_adjustment(params, market_data)
        
        # Check updated stats
        stats = self.strategy.get_adaptation_stats()
        self.assertEqual(stats["risk_adjustments"], 1)
        self.assertEqual(stats["trend_adjustments"], 1)
    
    def test_reset_adaptation_stats(self):
        """Test resetting adaptation statistics"""
        # Apply some adaptations to change stats
        params = {"position_size": 0.05, "take_profit": 0.05, "stop_loss": 0.03}
        market_data = {"current_regime": 0, "current_trend": "uptrend"}
        
        self.strategy.apply_risk_adjustment(params, market_data)
        self.strategy.apply_trend_adjustment(params, market_data)
        
        # Confirm stats were updated
        stats = self.strategy.get_adaptation_stats()
        self.assertEqual(stats["risk_adjustments"], 1)
        self.assertEqual(stats["trend_adjustments"], 1)
        
        # Reset stats
        self.strategy.reset_adaptation_stats()
        
        # Check that stats were reset to zero
        stats = self.strategy.get_adaptation_stats()
        self.assertEqual(stats["risk_adjustments"], 0)
        self.assertEqual(stats["trend_adjustments"], 0)
        self.assertEqual(stats["total_adaptations"], 0)
    
    def test_cooldown_period_respected(self):
        """Test that the cooldown period between adaptations is respected"""
        params = {
            "position_size": 0.04,
            "take_profit": 0.05,
            "stop_loss": 0.03,
            "entry_threshold": 0.004
        }
        
        market_data = {
            "strategy_id": "test_strategy",
            "current_regime": 0,
            "current_volatility": 0.015,
            "baseline_volatility": 0.01,
            "current_trend": "uptrend"
        }
        
        # First adaptation should apply changes
        adapted_params1 = self.strategy.adapt_strategy_parameters(params, market_data)
        self.assertNotEqual(params, adapted_params1)
        
        # Second adaptation within cooldown period should return original params
        adapted_params2 = self.strategy.adapt_strategy_parameters(params, market_data)
        self.assertEqual(params, adapted_params2)
        
        # Manually set last adaptation time to be outside the cooldown period
        self.strategy.last_adaptation_time["test_strategy"] = datetime.now() - timedelta(seconds=2000)
        
        # Now adaptation should occur
        adapted_params3 = self.strategy.adapt_strategy_parameters(params, market_data)
        self.assertNotEqual(params, adapted_params3)


if __name__ == '__main__':
    unittest.main() 