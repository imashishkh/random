"""
Unit tests for the SignalSynthesizer module.
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from src.agents.signal_synthesizer import SignalSynthesizer
from src.agents.signal_synthesizer.models import SignalStrength, TradingSignal, TimeFrame


@pytest.fixture
def mock_trend_agent():
    """Create a mock trend analysis agent."""
    agent = MagicMock()
    agent.agent_id = "trend-agent"
    agent.agent_type = "technical"
    agent.agent_subtype = "trend"
    agent.analyze = MagicMock(return_value={
        "direction": "bullish",
        "confidence": 0.75,
        "timeframe": "medium",
        "signal_strength": "strong"
    })
    return agent


@pytest.fixture
def mock_momentum_agent():
    """Create a mock momentum analysis agent."""
    agent = MagicMock()
    agent.agent_id = "momentum-agent"
    agent.agent_type = "technical"
    agent.agent_subtype = "momentum"
    agent.analyze = MagicMock(return_value={
        "direction": "bullish",
        "confidence": 0.65,
        "timeframe": "short",
        "signal_strength": "moderate"
    })
    return agent


@pytest.fixture
def mock_news_agent():
    """Create a mock news analysis agent."""
    agent = MagicMock()
    agent.agent_id = "news-agent"
    agent.agent_type = "fundamental"
    agent.agent_subtype = "news"
    agent.analyze = MagicMock(return_value={
        "direction": "bearish",
        "confidence": 0.80,
        "timeframe": "medium",
        "signal_strength": "strong",
        "news_impact": "high"
    })
    return agent


@pytest.fixture
def synthesizer():
    """Create a SignalSynthesizer instance."""
    return SignalSynthesizer()


class TestSignalSynthesizer:
    """Tests for the SignalSynthesizer class."""

    def test_initialization(self, synthesizer):
        """Test that SignalSynthesizer initializes correctly."""
        assert isinstance(synthesizer.agents, dict)
        assert len(synthesizer.agents) == 0
        assert isinstance(synthesizer.weights, dict)
        assert synthesizer.default_weight == 1.0
        assert synthesizer.weights["technical"] == 1.0
        assert synthesizer.weights["fundamental"] == 1.0
        assert synthesizer.weights["technical.trend"] == 1.0
        assert synthesizer.weights["technical.momentum"] == 1.0
        assert synthesizer.weights["fundamental.news"] == 1.0

    def test_register_agent(self, synthesizer, mock_trend_agent):
        """Test registering an agent."""
        synthesizer.register_agent(
            agent=mock_trend_agent,
            agent_type="technical",
            agent_subtype="trend"
        )
        
        # Verify the agent was registered
        assert "trend-agent" in synthesizer.agents
        agent_info = synthesizer.agents["trend-agent"]
        assert agent_info["agent"] == mock_trend_agent
        assert agent_info["type"] == "technical"
        assert agent_info["subtype"] == "trend"

    def test_register_agent_with_custom_weight(self, synthesizer, mock_trend_agent):
        """Test registering an agent with a custom weight."""
        synthesizer.register_agent(
            agent=mock_trend_agent,
            agent_type="technical",
            agent_subtype="trend",
            weight=1.5
        )
        
        # Verify the agent was registered with custom weight
        assert "trend-agent" in synthesizer.agents
        agent_info = synthesizer.agents["trend-agent"]
        assert agent_info["weight"] == 1.5

    def test_set_weights(self, synthesizer):
        """Test setting weights for agent types and subtypes."""
        # Set weights for various agent types
        synthesizer.set_weights({
            "technical": 1.2,
            "fundamental": 0.8,
            "technical.trend": 1.5,
            "fundamental.news": 0.7
        })
        
        # Verify weights were set
        assert synthesizer.weights["technical"] == 1.2
        assert synthesizer.weights["fundamental"] == 0.8
        assert synthesizer.weights["technical.trend"] == 1.5
        assert synthesizer.weights["fundamental.news"] == 0.7
        
        # Verify other weights remained at default
        assert synthesizer.weights["technical.momentum"] == 1.0

    def test_get_agent_weight(self, synthesizer, mock_trend_agent, mock_news_agent):
        """Test getting the effective weight for an agent."""
        # Set different weights
        synthesizer.set_weights({
            "technical": 1.2,
            "technical.trend": 1.5,
            "fundamental": 0.8
        })
        
        # Register agents
        synthesizer.register_agent(
            agent=mock_trend_agent,
            agent_type="technical",
            agent_subtype="trend"
        )
        
        synthesizer.register_agent(
            agent=mock_news_agent,
            agent_type="fundamental",
            agent_subtype="news"
        )
        
        # Get weights
        trend_weight = synthesizer._get_agent_weight("trend-agent")
        news_weight = synthesizer._get_agent_weight("news-agent")
        
        # Verify weights
        # Trend weight = technical_weight * technical.trend_weight = 1.2 * 1.5 = 1.8
        assert trend_weight == 1.8
        # News weight = fundamental_weight * 1.0 (default subtype weight) = 0.8 * 1.0 = 0.8
        assert news_weight == 0.8

    def test_get_agent_weight_with_custom_agent_weight(self, synthesizer, mock_trend_agent):
        """Test that agent-specific weights override type/subtype weights."""
        # Set different weights
        synthesizer.set_weights({
            "technical": 1.2,
            "technical.trend": 1.5
        })
        
        # Register agent with custom weight
        synthesizer.register_agent(
            agent=mock_trend_agent,
            agent_type="technical",
            agent_subtype="trend",
            weight=2.0  # This should override the calculated weight
        )
        
        # Get weight
        trend_weight = synthesizer._get_agent_weight("trend-agent")
        
        # Verify weight (should use the agent-specific weight)
        assert trend_weight == 2.0

    def test_normalize_signal_strengths(self, synthesizer):
        """Test normalizing signal strengths."""
        strengths = {
            "weak": 0.3,
            "moderate": 0.6,
            "strong": 0.9,
            "very_strong": 1.0
        }
        
        # Test weak
        assert synthesizer._normalize_signal_strength("weak") == strengths["weak"]
        
        # Test moderate
        assert synthesizer._normalize_signal_strength("moderate") == strengths["moderate"]
        
        # Test strong
        assert synthesizer._normalize_signal_strength("strong") == strengths["strong"]
        
        # Test very strong
        assert synthesizer._normalize_signal_strength("very_strong") == strengths["very_strong"]
        
        # Test unknown
        assert synthesizer._normalize_signal_strength("unknown") == 0.5  # Default

    def test_aggregate_signals_weighted_average(self, synthesizer, mock_trend_agent, mock_momentum_agent, mock_news_agent):
        """Test aggregating signals with weighted average."""
        # Register agents
        synthesizer.register_agent(
            agent=mock_trend_agent,
            agent_type="technical",
            agent_subtype="trend"
        )
        synthesizer.register_agent(
            agent=mock_momentum_agent,
            agent_type="technical",
            agent_subtype="momentum"
        )
        synthesizer.register_agent(
            agent=mock_news_agent,
            agent_type="fundamental",
            agent_subtype="news"
        )
        
        # Set weights
        synthesizer.set_weights({
            "technical": 1.0,
            "technical.trend": 1.5,
            "technical.momentum": 1.0,
            "fundamental": 2.0,
            "fundamental.news": 1.0
        })
        
        # Mock agent outputs
        mock_trend_agent.analyze.return_value = {
            "direction": "bullish",
            "confidence": 0.75,
            "timeframe": "medium",
            "signal_strength": "strong"
        }
        
        mock_momentum_agent.analyze.return_value = {
            "direction": "bullish",
            "confidence": 0.65,
            "timeframe": "short",
            "signal_strength": "moderate"
        }
        
        mock_news_agent.analyze.return_value = {
            "direction": "bearish",
            "confidence": 0.80,
            "timeframe": "medium",
            "signal_strength": "very_strong"
        }
        
        # Generate signals
        signals = synthesizer._generate_signals("EUR/USD")
        
        # Verify signals
        assert len(signals) == 3
        
        # Aggregate signals using weighted average
        aggregate = synthesizer._aggregate_signals_weighted_average(signals)
        
        # Calculate expected values
        # Weights: trend=1.5, momentum=1.0, news=2.0
        # Direction values: bullish=1, bearish=-1
        # Weighted sum: (1.5*1 + 1.0*1 + 2.0*(-1)) = 0.5
        # Total weight: 1.5 + 1.0 + 2.0 = 4.5
        # Normalized direction: 0.5 / 4.5 = 0.111 (positive means bullish)
        # Signal strengths: trend=0.9, momentum=0.6, news=1.0
        # Weighted strength: (1.5*0.9 + 1.0*0.6 + 2.0*1.0) / 4.5 = 0.867
        # Confidence values: trend=0.75, momentum=0.65, news=0.80
        # Weighted confidence: (1.5*0.75 + 1.0*0.65 + 2.0*0.80) / 4.5 = 0.75
        
        # Verify aggregate values
        assert aggregate["direction"] == "bullish"  # Small positive value rounds to bullish
        assert abs(aggregate["direction_value"] - 0.111) < 0.01
        assert abs(aggregate["signal_strength"] - 0.867) < 0.01
        assert abs(aggregate["confidence"] - 0.75) < 0.01
        assert aggregate["timeframe"] == "medium"  # Most frequent time frame

    def test_aggregate_signals_voting(self, synthesizer, mock_trend_agent, mock_momentum_agent, mock_news_agent):
        """Test aggregating signals with voting."""
        # Register agents
        synthesizer.register_agent(mock_trend_agent, "technical", "trend")
        synthesizer.register_agent(mock_momentum_agent, "technical", "momentum")
        synthesizer.register_agent(mock_news_agent, "fundamental", "news")
        
        # Mock agent outputs
        mock_trend_agent.analyze.return_value = {
            "direction": "bullish",
            "confidence": 0.75,
            "timeframe": "medium",
            "signal_strength": "strong"
        }
        
        mock_momentum_agent.analyze.return_value = {
            "direction": "bullish",
            "confidence": 0.65,
            "timeframe": "short",
            "signal_strength": "moderate"
        }
        
        mock_news_agent.analyze.return_value = {
            "direction": "bearish",
            "confidence": 0.80,
            "timeframe": "medium",
            "signal_strength": "very_strong"
        }
        
        # Generate signals
        signals = synthesizer._generate_signals("EUR/USD")
        
        # Aggregate signals using voting
        aggregate = synthesizer._aggregate_signals_voting(signals)
        
        # Verify aggregate values
        # Direction: 2 bullish, 1 bearish => bullish wins
        assert aggregate["direction"] == "bullish"
        assert aggregate["timeframe"] == "medium"  # Most frequent timeframe
        
        # Confidence and strength should be average of winners
        bullish_signals = [s for s in signals if s["direction"] == "bullish"]
        avg_confidence = sum(s["confidence"] for s in bullish_signals) / len(bullish_signals)
        avg_strength = sum(synthesizer._normalize_signal_strength(s["signal_strength"]) for s in bullish_signals) / len(bullish_signals)
        
        assert abs(aggregate["confidence"] - avg_confidence) < 0.01
        assert abs(aggregate["signal_strength"] - avg_strength) < 0.01

    def test_generate_trading_signal_weighted(self, synthesizer, mock_trend_agent, mock_momentum_agent, mock_news_agent):
        """Test generating a trading signal with weighted resolution."""
        # Register agents
        synthesizer.register_agent(mock_trend_agent, "technical", "trend")
        synthesizer.register_agent(mock_momentum_agent, "technical", "momentum")
        synthesizer.register_agent(mock_news_agent, "fundamental", "news")
        
        # Generate trading signal
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            resolution_method="weighted"
        )
        
        # Verify the signal
        assert isinstance(signal, TradingSignal)
        assert signal.currency_pair == "EUR/USD"
        assert signal.timeframe == TimeFrame.MEDIUM
        
        # Check that all agents were called with correct parameters
        mock_trend_agent.analyze.assert_called_once_with(
            currency_pair="EUR/USD",
            timeframe="medium",
            additional_context=None
        )
        mock_momentum_agent.analyze.assert_called_once_with(
            currency_pair="EUR/USD",
            timeframe="medium",
            additional_context=None
        )
        mock_news_agent.analyze.assert_called_once_with(
            currency_pair="EUR/USD",
            timeframe="medium",
            additional_context=None
        )

    def test_generate_trading_signal_voting(self, synthesizer, mock_trend_agent, mock_momentum_agent, mock_news_agent):
        """Test generating a trading signal with voting resolution."""
        # Register agents
        synthesizer.register_agent(mock_trend_agent, "technical", "trend")
        synthesizer.register_agent(mock_momentum_agent, "technical", "momentum")
        synthesizer.register_agent(mock_news_agent, "fundamental", "news")
        
        # Generate trading signal
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            resolution_method="voting"
        )
        
        # Verify the signal
        assert isinstance(signal, TradingSignal)
        assert signal.currency_pair == "EUR/USD"
        assert signal.timeframe == TimeFrame.MEDIUM

    def test_generate_trading_signal_with_additional_context(self, synthesizer, mock_trend_agent):
        """Test generating a trading signal with additional context."""
        # Register agent
        synthesizer.register_agent(mock_trend_agent, "technical", "trend")
        
        # Additional context
        additional_context = {
            "market_volatility": "high",
            "recent_news": "Central bank announcement"
        }
        
        # Generate trading signal
        synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            resolution_method="weighted",
            additional_context=additional_context
        )
        
        # Verify agent was called with the additional context
        mock_trend_agent.analyze.assert_called_once_with(
            currency_pair="EUR/USD",
            timeframe="medium",
            additional_context=additional_context
        )

    def test_generate_trading_signal_no_agents(self, synthesizer):
        """Test generating a trading signal with no registered agents."""
        # Generate trading signal
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium"
        )
        
        # Verify the signal indicates no action
        assert signal.action == "no_action"
        assert signal.confidence == 0.0
        assert signal.signal_strength == SignalStrength.WEAK

    def test_generate_trading_signal_with_minimum_consensus(self, synthesizer, mock_trend_agent, mock_momentum_agent, mock_news_agent):
        """Test generating a trading signal with minimum consensus threshold."""
        # Register agents
        synthesizer.register_agent(mock_trend_agent, "technical", "trend")
        synthesizer.register_agent(mock_momentum_agent, "technical", "momentum")
        synthesizer.register_agent(mock_news_agent, "fundamental", "news")
        
        # Set all agents to have a bearish signal
        mock_trend_agent.analyze.return_value = {
            "direction": "bearish",
            "confidence": 0.75,
            "timeframe": "medium",
            "signal_strength": "strong"
        }
        
        mock_momentum_agent.analyze.return_value = {
            "direction": "bearish",
            "confidence": 0.65,
            "timeframe": "medium",
            "signal_strength": "moderate"
        }
        
        mock_news_agent.analyze.return_value = {
            "direction": "bearish",
            "confidence": 0.80,
            "timeframe": "medium",
            "signal_strength": "strong"
        }
        
        # Generate trading signal with 100% consensus requirement
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            minimum_consensus=1.0  # Require 100% agreement
        )
        
        # Verify the signal reflects consensus
        assert signal.action == "sell"  # All bearish => sell
        
        # Change one agent to be bullish
        mock_trend_agent.analyze.return_value = {
            "direction": "bullish",
            "confidence": 0.75,
            "timeframe": "medium",
            "signal_strength": "strong"
        }
        
        # Generate trading signal with 100% consensus requirement again
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            minimum_consensus=1.0  # Require 100% agreement
        )
        
        # Verify that with no consensus, we get no_action
        assert signal.action == "no_action"
        
        # Try with lower consensus requirement (66%)
        signal = synthesizer.generate_trading_signal(
            currency_pair="EUR/USD",
            timeframe="medium",
            minimum_consensus=0.66  # Require 66% agreement
        )
        
        # Verify that with 66% consensus (2/3 bearish), we get a sell signal
        assert signal.action == "sell" 