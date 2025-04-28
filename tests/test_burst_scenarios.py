import pytest
import asyncio
import logging
from typing import Dict, Any

from harness.generators.burst_scenarios import (
    SuddenBurstScenario,
    RampBurstScenario, 
    OscillatingBurstScenario,
    MarketEventBurstScenario,
    AIReactiveBurstScenario,
    create_burst_scenario
)
from harness.data_types import MarketData

# Configure logging for tests
logger = logging.getLogger("test_burst_scenarios")
logging.basicConfig(level=logging.INFO)

# Base configuration for tests
@pytest.fixture
def base_config() -> Dict[str, Any]:
    return {
        'symbols': ['EURUSD', 'GBPUSD', 'USDJPY'],
        'order_type_distribution': {'market': 0.6, 'limit': 0.3, 'stop': 0.1},
        'burst_interval_min': 5,
        'burst_interval_max': 15,
        'burst_size_min': 5,
        'burst_size_max': 20,
        'burst_duration_min': 0.5,
        'burst_duration_max': 3.0,
        'cancellation_probability': 0.3,
        'modification_probability': 0.2,
    }

# Specific configurations for different scenario types
@pytest.fixture
def sudden_config(base_config) -> Dict[str, Any]:
    config = base_config.copy()
    config.update({
        'sudden_intensity': 0.7
    })
    return config

@pytest.fixture
def ramp_config(base_config) -> Dict[str, Any]:
    config = base_config.copy()
    config.update({
        'ramp_duration_min': 5.0,
        'ramp_duration_max': 20.0
    })
    return config

@pytest.fixture
def oscillating_config(base_config) -> Dict[str, Any]:
    config = base_config.copy()
    config.update({
        'oscillation_period_min': 5.0,
        'oscillation_period_max': 15.0,
        'oscillation_intensity': 0.8
    })
    return config

@pytest.fixture
def market_event_config(base_config) -> Dict[str, Any]:
    config = base_config.copy()
    config.update({
        'trigger_conditions': ['price_change', 'spread_widening', 'volume_spike'],
        'price_change_threshold': 0.002,
        'spread_threshold': 0.0005,
        'volume_threshold': 2.0,
        'cooldown_period': 10.0,
        'response_delay_min': 0.1,
        'response_delay_max': 0.5
    })
    return config

@pytest.fixture
def ai_reactive_config(base_config) -> Dict[str, Any]:
    config = base_config.copy()
    config.update({
        'prediction_window': 10,
        'prediction_confidence_threshold': 0.65,
        'ai_sophistication': 0.7,
        'ai_aggression': 0.5,
        'ai_coordination': 0.3,
        'ai_reaction_time': 0.15,
        'market_data_history': 30,
        'prediction_interval': 1.0
    })
    return config

@pytest.fixture
def sample_market_data() -> MarketData:
    return MarketData(
        symbol="EURUSD",
        price=1.0950,
        bid=1.0949,
        ask=1.0951,
        volume=10000,
        timestamp=1623456789.0
    )

# Factory function test
def test_create_burst_scenario(base_config):
    # Test valid scenario types
    assert isinstance(create_burst_scenario('sudden', base_config, logger), SuddenBurstScenario)
    assert isinstance(create_burst_scenario('ramp', base_config, logger), RampBurstScenario)
    assert isinstance(create_burst_scenario('oscillating', base_config, logger), OscillatingBurstScenario)
    assert isinstance(create_burst_scenario('market_event', base_config, logger), MarketEventBurstScenario)
    assert isinstance(create_burst_scenario('ai_reactive', base_config, logger), AIReactiveBurstScenario)
    
    # Test invalid scenario type
    with pytest.raises(ValueError):
        create_burst_scenario('invalid_type', base_config, logger)

# Test individual scenario classes
@pytest.mark.asyncio
async def test_sudden_burst_scenario(sudden_config):
    generator = SuddenBurstScenario(sudden_config, logger)
    assert generator.sudden_intensity == 0.7
    assert set(generator.symbols) == set(['EURUSD', 'GBPUSD', 'USDJPY'])
    
    # Start and stop
    await generator.start()
    assert generator._running
    await generator.stop()
    assert not generator._running

@pytest.mark.asyncio
async def test_ramp_burst_scenario(ramp_config):
    generator = RampBurstScenario(ramp_config, logger)
    assert generator.ramp_duration_min == 5.0
    assert generator.ramp_duration_max == 20.0
    
    # Start and stop
    await generator.start()
    assert generator._running
    await generator.stop()
    assert not generator._running

@pytest.mark.asyncio
async def test_oscillating_burst_scenario(oscillating_config):
    generator = OscillatingBurstScenario(oscillating_config, logger)
    assert generator.oscillation_period_min == 5.0
    assert generator.oscillation_period_max == 15.0
    assert generator.oscillation_intensity == 0.8
    
    # Start and stop
    await generator.start()
    assert generator._running
    await generator.stop()
    assert not generator._running

@pytest.mark.asyncio
async def test_market_event_burst_scenario(market_event_config, sample_market_data):
    generator = MarketEventBurstScenario(market_event_config, logger)
    assert set(generator.trigger_conditions) == set(['price_change', 'spread_widening', 'volume_spike'])
    assert generator.price_change_threshold == 0.002
    
    # Start and update market data
    await generator.start()
    assert generator._running
    
    # Test market data update
    generator.update_market_data(sample_market_data)
    assert generator.market_data['EURUSD'].price == 1.0950
    
    await generator.stop()
    assert not generator._running

@pytest.mark.asyncio
async def test_ai_reactive_burst_scenario(ai_reactive_config, sample_market_data):
    generator = AIReactiveBurstScenario(ai_reactive_config, logger)
    
    # Check configuration parameters
    assert generator.prediction_window == 10
    assert generator.prediction_confidence_threshold == 0.65
    assert generator.ai_sophistication == 0.7
    assert generator.ai_aggression == 0.5
    assert generator.ai_coordination == 0.3
    
    # Start generator
    await generator.start()
    assert generator._running
    
    # Update with market data
    generator.update_market_data(sample_market_data)
    assert 'EURUSD' in generator.market_data_buffer
    assert generator.market_data_buffer['EURUSD'][0]['price'] == 1.0950
    
    # Test sufficient market data check - should be false with just one data point
    assert not generator._has_sufficient_market_data('EURUSD')
    
    # Update with more market data points
    for i in range(5):
        updated_data = MarketData(
            symbol="EURUSD",
            price=1.0950 + (i * 0.0001),
            bid=1.0949 + (i * 0.0001),
            ask=1.0951 + (i * 0.0001),
            volume=10000 + (i * 100),
            timestamp=1623456789.0 + i
        )
        generator.update_market_data(updated_data)
    
    # Should have enough data now
    assert generator._has_sufficient_market_data('EURUSD')
    
    # Test AI prediction generation
    prediction = generator._generate_ai_prediction('EURUSD')
    assert prediction is not None
    assert 'symbol' in prediction
    assert 'type' in prediction
    assert 'confidence' in prediction
    assert 'direction' in prediction
    assert prediction['symbol'] == 'EURUSD'
    
    # Test reaction time calculation
    reaction_time = generator._calculate_ai_reaction_time('momentum')
    assert 0.05 <= reaction_time <= 1.0  # Should be within reasonable bounds
    
    # Test random burst generation
    await generator._generate_burst()
    
    # Clean up
    await generator.stop()
    assert not generator._running

# Test order generation
@pytest.mark.asyncio
async def test_order_generation(ai_reactive_config):
    generator = AIReactiveBurstScenario(ai_reactive_config, logger)
    
    # Test basic order generation
    order = await generator._generate_order('EURUSD')
    assert order.symbol == 'EURUSD'
    assert order.side in ['buy', 'sell']
    assert order.order_type in ['market', 'limit', 'stop']
    
    # Test order generation with specific price target
    target_price = 1.1000
    order = await generator._generate_order('EURUSD', price_target=target_price)
    assert order.symbol == 'EURUSD'
    
    # Stop generator
    await generator.stop() 