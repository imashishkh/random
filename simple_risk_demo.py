#!/usr/bin/env python3
"""
Simple Risk Manager Demo

This script demonstrates the core functionality of the Risk Manager
without relying on complex dependencies.
"""

import json
import uuid
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple Position class
class Position:
    def __init__(self, position_id, symbol, direction, entry_price, stop_loss, risk_percent=None, units=None):
        self.position_id = position_id or str(uuid.uuid4())
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.risk_percent = risk_percent
        self.units = units
        self.timestamp = datetime.utcnow().isoformat()
        self.metadata = {}
    
    def to_dict(self):
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "risk_percent": self.risk_percent,
            "units": self.units,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

# Simple Agent class
class Agent:
    def __init__(self, agent_id, name, agent_type="trading", description="", risk_limits=None):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self.risk_limits = risk_limits or {}
        self.metadata = {}
        self.registration_time = datetime.utcnow().isoformat()
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "name": self.name, 
            "agent_type": self.agent_type,
            "description": self.description,
            "risk_limits": self.risk_limits,
            "metadata": self.metadata,
            "registration_time": self.registration_time
        }

# Simple Risk Manager class
class SimpleRiskManager:
    def __init__(self, account_balance=10000.0):
        self.config = {
            'account_balance': account_balance,
            'max_risk_per_trade': 2.0,
            'max_daily_risk': 10.0,
            'max_correlated_risk': 5.0,
            'max_open_positions': 10,
            'max_daily_drawdown': 5.0,
            'correlation_threshold': 0.7,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        self.agents = {}
        self.positions = {}
        logger.info(f"Simple Risk Manager initialized with balance: ${account_balance:.2f}")
    
    def get_status(self):
        total_risk = sum(self.calculate_position_risk(p) for p in self.positions.values())
        total_risk_percent = (total_risk / self.config['account_balance']) * 100 if self.config['account_balance'] > 0 else 0
        
        risk_level = 'low'
        if total_risk_percent > self.config['max_daily_risk'] * 0.7:
            risk_level = 'high'
        elif total_risk_percent > self.config['max_daily_risk'] * 0.4:
            risk_level = 'medium'
        
        return {
            'risk_level': risk_level,
            'timestamp': datetime.utcnow().isoformat(),
            'account_balance': self.config['account_balance'],
            'total_risk_amount': total_risk,
            'total_risk_percent': total_risk_percent,
            'max_daily_risk': self.config['max_daily_risk'],
            'max_risk_per_trade': self.config['max_risk_per_trade'],
            'position_count': len(self.positions),
            'max_positions': self.config['max_open_positions']
        }
    
    def calculate_position_risk(self, position):
        if not hasattr(position, 'units') or position.units is None:
            return 0
        
        risk_amount = abs(position.entry_price - position.stop_loss)
        return risk_amount * position.units
    
    def register_agent(self, agent):
        self.agents[agent.agent_id] = agent
        logger.info(f"Agent registered: {agent.name} ({agent.agent_id})")
        return agent.to_dict()
    
    def get_agent(self, agent_id):
        agent = self.agents.get(agent_id)
        return agent.to_dict() if agent else None
    
    def update_agent(self, agent):
        if agent.agent_id not in self.agents:
            raise ValueError(f"Agent with ID {agent.agent_id} not found")
        
        self.agents[agent.agent_id] = agent
        logger.info(f"Agent updated: {agent.name} ({agent.agent_id})")
        return agent.to_dict()
    
    def add_position(self, position):
        # Validate position data
        if position.direction not in ['long', 'short']:
            raise ValueError("Direction must be 'long' or 'short'")
        
        if position.entry_price <= 0:
            raise ValueError("Entry price must be positive")
        
        if position.stop_loss <= 0:
            raise ValueError("Stop loss must be positive")
        
        # Validate stop loss placement
        if position.direction == 'long' and position.stop_loss >= position.entry_price:
            raise ValueError("For long positions, stop loss must be below entry price")
        
        if position.direction == 'short' and position.stop_loss <= position.entry_price:
            raise ValueError("For short positions, stop loss must be above entry price")
        
        # If units not specified but risk percent is, calculate units
        if position.units is None and position.risk_percent is not None:
            result = self.calculate_position_size(
                symbol=position.symbol,
                entry_price=position.entry_price,
                stop_loss=position.stop_loss,
                risk_percent=position.risk_percent
            )
            position.units = result['units']
        
        self.positions[position.position_id] = position
        logger.info(f"Position added: {position.symbol} {position.direction} ({position.position_id})")
        return position.to_dict()
    
    def get_position(self, position_id):
        position = self.positions.get(position_id)
        return position.to_dict() if position else None
    
    def get_positions(self):
        return [p.to_dict() for p in self.positions.values()]
    
    def remove_position(self, position_id):
        if position_id not in self.positions:
            return False
        
        del self.positions[position_id]
        logger.info(f"Position removed: {position_id}")
        return True
    
    def approve_trade(self, position):
        analysis = {
            'timestamp': datetime.utcnow().isoformat(),
            'account_balance': self.config['account_balance'],
            'checks': [],
            'violations': []
        }
        
        # Check 1: Maximum number of open positions
        if len(self.positions) >= self.config['max_open_positions']:
            analysis['violations'].append("Maximum number of open positions reached")
        
        # Check 2: Calculate risk if units or risk_percent is provided
        position_risk = 0
        risk_percent = 0
        
        if position.units is not None:
            position_risk = self.calculate_position_risk(position)
            risk_percent = (position_risk / self.config['account_balance']) * 100
        elif position.risk_percent is not None:
            risk_percent = position.risk_percent
            position_risk = (risk_percent / 100) * self.config['account_balance']
        
        # Check if risk exceeds maximum per trade
        if risk_percent > self.config['max_risk_per_trade']:
            analysis['violations'].append(f"Trade exceeds maximum risk per trade ({risk_percent:.2f}% > {self.config['max_risk_per_trade']}%)")
        
        # Check 3: Total daily risk
        total_risk = sum(self.calculate_position_risk(p) for p in self.positions.values())
        total_risk += position_risk
        total_risk_percent = (total_risk / self.config['account_balance']) * 100
        
        if total_risk_percent > self.config['max_daily_risk']:
            analysis['violations'].append(f"Trade would exceed maximum daily risk ({total_risk_percent:.2f}% > {self.config['max_daily_risk']}%)")
        
        approved = len(analysis['violations']) == 0
        analysis['approved'] = approved
        
        if approved:
            logger.info(f"Trade approved: {position.symbol} {position.direction}")
        else:
            logger.warning(f"Trade rejected: {position.symbol} {position.direction}. Violations: {analysis['violations']}")
        
        return approved, analysis
    
    def calculate_position_size(self, symbol, entry_price, stop_loss, risk_percent=None):
        # Default to max risk per trade if not specified
        if risk_percent is None:
            risk_percent = self.config['max_risk_per_trade']
        
        # Calculate risk amount in price points
        risk_amount = abs(entry_price - stop_loss)
        
        # Calculate the risk in dollars
        risk_dollars = (risk_percent / 100) * self.config['account_balance']
        
        # Calculate the position size in units
        units = risk_dollars / risk_amount if risk_amount > 0 else 0
        
        # Calculate other metrics
        notional_value = entry_price * units
        leverage = notional_value / self.config['account_balance']
        
        return {
            'symbol': symbol,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'risk_amount': risk_amount,
            'risk_percentage': risk_percent,
            'risk_dollars': risk_dollars,
            'units': units,
            'notional_value': notional_value,
            'account_balance': self.config['account_balance'],
            'leverage': leverage
        }

def run_demo():
    """Run the simple Risk Manager demonstration."""
    logger.info("Starting Simple Risk Manager Demo")
    
    # Create the risk manager
    risk_manager = SimpleRiskManager(account_balance=20000.0)
    
    # Step 1: Get initial risk status
    logger.info("Getting initial risk status")
    status = risk_manager.get_status()
    logger.info(f"Risk level: {status['risk_level']}")
    logger.info(f"Account balance: ${status['account_balance']}")
    logger.info(f"Position count: {status['position_count']}")
    
    # Step 2: Register a trading agent
    logger.info("Registering a trading agent")
    agent = Agent(
        agent_id=str(uuid.uuid4()),
        name="Demo Trading Agent",
        agent_type="trend_following",
        description="Agent for testing risk management",
        risk_limits={"max_risk_per_trade": 1.0, "max_positions": 5}
    )
    agent_result = risk_manager.register_agent(agent)
    logger.info(f"Agent registered with ID: {agent_result['agent_id']}")
    
    # Step 3: Calculate position size
    logger.info("Calculating position size for EUR/USD trade")
    position_calc = risk_manager.calculate_position_size(
        symbol="EURUSD",
        entry_price=1.1200,
        stop_loss=1.1150,
        risk_percent=1.0
    )
    logger.info(f"Calculated position size: {position_calc['units']} units")
    logger.info(f"Risk dollars: ${position_calc['risk_dollars']}")
    logger.info(f"Notional value: ${position_calc['notional_value']}")
    
    # Step 4: Request trade approval
    logger.info("Requesting trade approval")
    position = Position(
        position_id=None,  # Will be auto-generated
        symbol="EURUSD",
        direction="long",
        entry_price=1.1200,
        stop_loss=1.1150,
        risk_percent=1.0
    )
    approved, analysis = risk_manager.approve_trade(position)
    
    if approved:
        logger.info("Trade approved!")
        
        # Step 5: Add position
        logger.info("Adding position")
        added_position = risk_manager.add_position(position)
        logger.info(f"Position added with ID: {added_position['position_id']}")
        position_id = added_position['position_id']
        
        # Step 6: Get positions
        logger.info("Getting all positions")
        positions = risk_manager.get_positions()
        logger.info(f"Found {len(positions)} positions")
        
        for pos in positions:
            logger.info(f"Position: {pos['symbol']} {pos['direction']} - ID: {pos['position_id']}")
        
        # Step 7: Get position details
        logger.info(f"Getting position details for ID: {position_id}")
        position_details = risk_manager.get_position(position_id)
        if position_details:
            logger.info(f"Position details: {json.dumps(position_details, indent=2)}")
        
        # Step 8: Remove position
        logger.info(f"Removing position with ID: {position_id}")
        result = risk_manager.remove_position(position_id)
        if result:
            logger.info(f"Position {position_id} removed successfully")
    else:
        logger.warning("Trade rejected!")
        for violation in analysis['violations']:
            logger.warning(f"Violation: {violation}")
    
    # Step 9: Get final risk status
    logger.info("Getting final risk status")
    final_status = risk_manager.get_status()
    logger.info(f"Final risk level: {final_status['risk_level']}")
    logger.info(f"Final position count: {final_status['position_count']}")
    
    logger.info("Simple Risk Manager Demo completed")

if __name__ == "__main__":
    run_demo() 