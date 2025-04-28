#!/usr/bin/env python3
"""
Risk Manager Core

Core functionality of the Risk Manager, responsible for:
- Managing trading agents and their risk profiles
- Tracking and analyzing open positions
- Enforcing risk limits and trade approvals
- Calculating position sizes based on risk parameters
- Maintaining risk status and configuration
"""

import uuid
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
from dataclasses import dataclass, field, asdict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Position:
    """
    Represents a trading position, either actual or proposed.
    """
    position_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    units: Optional[float] = None
    risk_percent: Optional[float] = None
    agent_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create a Position from dictionary data."""
        return cls(**data)
    
    @property
    def risk_amount(self) -> float:
        """Calculate the risk amount in price points."""
        if self.direction == 'long':
            return self.entry_price - self.stop_loss
        else:  # short
            return self.stop_loss - self.entry_price
            
    @property
    def risk_amount_percentage(self) -> float:
        """Calculate the risk as a percentage of entry price."""
        return abs(self.risk_amount / self.entry_price * 100)
    
    @property
    def risk_value(self) -> Optional[float]:
        """Calculate the monetary risk value if units are known."""
        if self.units is None:
            return None
        return abs(self.risk_amount * self.units)

@dataclass
class Agent:
    """
    Represents a trading agent with associated risk limits.
    """
    agent_id: str
    name: str
    agent_type: str  # 'trading', 'risk', 'monitoring', etc.
    description: str = ""
    risk_limits: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registration_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Agent':
        """Create an Agent from dictionary data."""
        return cls(**data)

class RiskManager:
    """
    Core Risk Manager implementation that handles risk calculations, 
    position tracking, and trade approvals.
    """
    
    def __init__(self, initial_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Risk Manager with default or provided configuration.
        
        Args:
            initial_config: Optional initial configuration
        """
        # Default configuration
        self.config = {
            'account_balance': 10000.0,
            'max_risk_per_trade': 2.0,  # Max % of account per trade
            'max_daily_risk': 10.0,     # Max % of account per day
            'max_correlated_risk': 5.0, # Max % of account in correlated positions
            'max_open_positions': 10,   # Max number of concurrent positions
            'max_daily_drawdown': 5.0,  # Max % daily drawdown allowed
            'risk_free_rate': 0.0,      # Risk-free rate for calculations
            'correlation_threshold': 0.7, # Correlation threshold for grouping
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Apply provided configuration
        if initial_config:
            self.config.update(initial_config)
        
        # Initialize storage
        self.agents: Dict[str, Agent] = {}
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.risk_events: List[Dict[str, Any]] = []
        
        logger.info("Risk Manager initialized with balance: $%s", self.config['account_balance'])
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current risk status.
        
        Returns:
            Dict containing the current risk status
        """
        # Calculate current exposure
        total_risk = sum(p.risk_value or 0 for p in self.positions.values())
        total_risk_percent = (total_risk / self.config['account_balance']) * 100 if self.config['account_balance'] > 0 else 0
        
        # Count positions by direction
        long_positions = sum(1 for p in self.positions.values() if p.direction == 'long')
        short_positions = sum(1 for p in self.positions.values() if p.direction == 'short')
        
        # Group by symbols
        symbols = {}
        for pos in self.positions.values():
            if pos.symbol not in symbols:
                symbols[pos.symbol] = {'count': 0, 'risk': 0}
            symbols[pos.symbol]['count'] += 1
            symbols[pos.symbol]['risk'] += pos.risk_value or 0
        
        # Determine risk status
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
            'max_positions': self.config['max_open_positions'],
            'long_positions': long_positions,
            'short_positions': short_positions,
            'symbols': symbols
        }
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current risk configuration.
        
        Returns:
            Dict containing the current configuration
        """
        return self.config
    
    def update_account_balance(self, balance: float) -> None:
        """
        Update the account balance.
        
        Args:
            balance: New account balance
        """
        if balance <= 0:
            raise ValueError("Account balance must be positive")
            
        self.config['account_balance'] = float(balance)
        self.config['updated_at'] = datetime.utcnow().isoformat()
        logger.info(f"Account balance updated to ${balance}")
    
    def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the risk configuration.
        
        Args:
            new_config: Dictionary with configuration updates
            
        Returns:
            Updated configuration dictionary
        """
        # Validate numeric parameters
        for param in ['max_risk_per_trade', 'max_daily_risk', 'max_correlated_risk', 
                     'max_open_positions', 'max_daily_drawdown', 'correlation_threshold']:
            if param in new_config:
                value = new_config[param]
                if isinstance(value, (int, float)) and value > 0:
                    self.config[param] = float(value)
                else:
                    raise ValueError(f"Invalid value for {param}: must be a positive number")
        
        # Update other parameters
        for param, value in new_config.items():
            if param not in ['max_risk_per_trade', 'max_daily_risk', 'max_correlated_risk', 
                           'max_open_positions', 'max_daily_drawdown', 'correlation_threshold']:
                self.config[param] = value
        
        self.config['updated_at'] = datetime.utcnow().isoformat()
        logger.info(f"Risk configuration updated: {new_config}")
        return self.config
    
    def register_agent(self, agent: Agent) -> None:
        """
        Register a new trading agent.
        
        Args:
            agent: Agent object to register
        """
        if agent.agent_id in self.agents:
            raise ValueError(f"Agent with ID {agent.agent_id} already exists")
            
        self.agents[agent.agent_id] = agent
        logger.info(f"Agent registered: {agent.name} ({agent.agent_id})")
    
    def update_agent(self, agent: Agent) -> None:
        """
        Update an existing agent's information.
        
        Args:
            agent: Updated Agent object
        """
        if agent.agent_id not in self.agents:
            raise ValueError(f"Agent with ID {agent.agent_id} not found")
            
        self.agents[agent.agent_id] = agent
        logger.info(f"Agent updated: {agent.name} ({agent.agent_id})")
    
    def get_agents(self) -> List[Dict[str, Any]]:
        """
        Get all registered agents.
        
        Returns:
            List of agent dictionaries
        """
        return [agent.to_dict() for agent in self.agents.values()]
    
    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific agent by ID.
        
        Args:
            agent_id: ID of the agent to retrieve
            
        Returns:
            Agent dictionary or None if not found
        """
        agent = self.agents.get(agent_id)
        return agent.to_dict() if agent else None
    
    def add_position(self, position: Position) -> None:
        """
        Add a new position to tracking.
        
        Args:
            position: Position object to add
        """
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
            position.units = self.calculate_position_size(
                symbol=position.symbol,
                entry_price=position.entry_price,
                stop_loss=position.stop_loss,
                risk_percent=position.risk_percent
            )['units']
        
        # Add the position
        self.positions[position.position_id] = position
        logger.info(f"Position added: {position.symbol} {position.direction} ({position.position_id})")
    
    def get_positions(self, agent_id: Optional[str] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get positions with optional filtering.
        
        Args:
            agent_id: Optional agent ID to filter by
            symbol: Optional symbol to filter by
            
        Returns:
            List of position dictionaries
        """
        result = []
        
        for pos in self.positions.values():
            # Apply filters
            if agent_id and pos.agent_id != agent_id:
                continue
                
            if symbol and pos.symbol != symbol:
                continue
                
            result.append(pos.to_dict())
            
        return result
    
    def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific position by ID.
        
        Args:
            position_id: ID of the position to retrieve
            
        Returns:
            Position dictionary or None if not found
        """
        position = self.positions.get(position_id)
        return position.to_dict() if position else None
    
    def remove_position(self, position_id: str) -> bool:
        """
        Remove a position from tracking.
        
        Args:
            position_id: ID of the position to remove
            
        Returns:
            True if position was removed, False if not found
        """
        if position_id not in self.positions:
            return False
            
        # Store in history before removing
        position = self.positions[position_id]
        self.trade_history.append({
            'position': position.to_dict(),
            'action': 'closed',
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Remove position
        del self.positions[position_id]
        logger.info(f"Position removed: {position_id}")
        return True
    
    def approve_trade(self, position: Position) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate a proposed trade for risk compliance.
        
        Args:
            position: Position object representing the proposed trade
            
        Returns:
            Tuple of (approved, analysis_dict)
        """
        analysis = {
            'timestamp': datetime.utcnow().isoformat(),
            'account_balance': self.config['account_balance'],
            'checks': [],
            'risk_amount': position.risk_amount,
            'risk_percent': position.risk_amount_percentage
        }
        
        violations = []
        
        # Calculate position size if needed
        if position.units is None and position.risk_percent is not None:
            calc_result = self.calculate_position_size(
                symbol=position.symbol,
                entry_price=position.entry_price,
                stop_loss=position.stop_loss,
                risk_percent=position.risk_percent
            )
            position.units = calc_result['units']
            analysis['calculated_units'] = position.units
        
        # Check 1: Maximum number of open positions
        if len(self.positions) >= self.config['max_open_positions']:
            violations.append("Maximum number of open positions reached")
            analysis['checks'].append({
                'name': 'max_positions',
                'passed': False,
                'current': len(self.positions),
                'limit': self.config['max_open_positions']
            })
        else:
            analysis['checks'].append({
                'name': 'max_positions',
                'passed': True,
                'current': len(self.positions),
                'limit': self.config['max_open_positions']
            })
        
        # Check 2: Risk per trade
        position_risk_value = position.risk_value
        if position_risk_value is None:
            violations.append("Unable to calculate position risk")
        else:
            position_risk_percent = (position_risk_value / self.config['account_balance']) * 100
            if position_risk_percent > self.config['max_risk_per_trade']:
                violations.append(f"Trade exceeds maximum risk per trade ({position_risk_percent:.2f}% > {self.config['max_risk_per_trade']}%)")
                analysis['checks'].append({
                    'name': 'max_risk_per_trade',
                    'passed': False,
                    'current': position_risk_percent,
                    'limit': self.config['max_risk_per_trade']
                })
            else:
                analysis['checks'].append({
                    'name': 'max_risk_per_trade',
                    'passed': True,
                    'current': position_risk_percent,
                    'limit': self.config['max_risk_per_trade']
                })
        
        # Check 3: Total daily risk
        total_risk = sum(p.risk_value or 0 for p in self.positions.values())
        if position_risk_value is not None:
            total_risk += position_risk_value
        total_risk_percent = (total_risk / self.config['account_balance']) * 100
        
        if total_risk_percent > self.config['max_daily_risk']:
            violations.append(f"Trade would exceed maximum daily risk ({total_risk_percent:.2f}% > {self.config['max_daily_risk']}%)")
            analysis['checks'].append({
                'name': 'max_daily_risk',
                'passed': False,
                'current': total_risk_percent,
                'limit': self.config['max_daily_risk']
            })
        else:
            analysis['checks'].append({
                'name': 'max_daily_risk',
                'passed': True,
                'current': total_risk_percent,
                'limit': self.config['max_daily_risk']
            })
        
        # Check 4: Symbol concentration
        symbol_positions = [p for p in self.positions.values() if p.symbol == position.symbol]
        symbol_risk = sum(p.risk_value or 0 for p in symbol_positions)
        if position_risk_value is not None:
            symbol_risk += position_risk_value
        symbol_risk_percent = (symbol_risk / self.config['account_balance']) * 100
        
        if symbol_risk_percent > self.config['max_correlated_risk']:
            violations.append(f"Trade would exceed maximum risk for symbol {position.symbol}")
            analysis['checks'].append({
                'name': 'symbol_concentration',
                'passed': False,
                'current': symbol_risk_percent,
                'limit': self.config['max_correlated_risk']
            })
        else:
            analysis['checks'].append({
                'name': 'symbol_concentration',
                'passed': True,
                'current': symbol_risk_percent,
                'limit': self.config['max_correlated_risk']
            })
        
        # Check 5: Agent-specific limits if agent is specified
        if position.agent_id and position.agent_id in self.agents:
            agent = self.agents[position.agent_id]
            if 'max_risk_per_trade' in agent.risk_limits:
                agent_max_risk = agent.risk_limits['max_risk_per_trade']
                if position_risk_value is not None:
                    agent_risk_percent = (position_risk_value / self.config['account_balance']) * 100
                    if agent_risk_percent > agent_max_risk:
                        violations.append(f"Trade exceeds agent's maximum risk per trade")
                        analysis['checks'].append({
                            'name': 'agent_max_risk',
                            'passed': False,
                            'current': agent_risk_percent,
                            'limit': agent_max_risk
                        })
                    else:
                        analysis['checks'].append({
                            'name': 'agent_max_risk',
                            'passed': True,
                            'current': agent_risk_percent,
                            'limit': agent_max_risk
                        })
        
        # Final approval decision
        approved = len(violations) == 0
        
        analysis['approved'] = approved
        analysis['violations'] = violations
        
        # Log the approval result
        if approved:
            logger.info(f"Trade approved: {position.symbol} {position.direction}")
        else:
            logger.warning(f"Trade rejected: {position.symbol} {position.direction}. Violations: {violations}")
        
        return approved, analysis
    
    def calculate_position_size(self, symbol: str, entry_price: float, 
                               stop_loss: float, risk_percent: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate the position size based on risk parameters.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_percent: Risk percentage of account (defaults to max_risk_per_trade)
            
        Returns:
            Dictionary with calculation results
        """
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