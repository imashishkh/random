"""
Risk Manager Integration for Trading Agents

This module provides tools and extensions for integrating the Risk Manager
with trading agents, including a RiskAwareAgent mixin and Risk Manager tools.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Tuple, Callable
from functools import wraps

from langchain.agents.tools import Tool
from ..risk.client import RiskManagerClient
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RiskAwareAgent:
    """
    Mixin class for adding risk management capabilities to trading agents.
    
    This class provides methods for interacting with the Risk Manager,
    including registering with the risk manager, requesting trade approvals,
    and querying risk status.
    """
    
    def __init__(
        self,
        risk_client: Optional[RiskManagerClient] = None,
        base_url: str = "http://localhost:5000",
        api_key: Optional[str] = None,
        auto_register: bool = True,
        max_risk_per_trade: float = 1.0,
        max_total_risk: float = 5.0,
        allowed_symbols: Optional[List[str]] = None,
        *args,
        **kwargs
    ):
        """
        Initialize the risk-aware agent mixin.
        
        Args:
            risk_client: Existing RiskManagerClient instance (created if not provided)
            base_url: Base URL of the Risk Manager API (if creating a new client)
            api_key: API key for authentication (if creating a new client)
            auto_register: Whether to automatically register with the risk manager
            max_risk_per_trade: Maximum risk percentage per trade
            max_total_risk: Maximum total risk percentage
            allowed_symbols: List of symbols the agent is allowed to trade
            *args, **kwargs: Additional arguments passed to parent class
        """
        # Initialize parent class if this is a mixin
        super().__init__(*args, **kwargs)
        
        # Save risk parameters
        self.max_risk_per_trade = max_risk_per_trade
        self.max_total_risk = max_total_risk
        self.allowed_symbols = allowed_symbols or []
        
        # Create or use the provided risk client
        if risk_client:
            self.risk_client = risk_client
        else:
            # Ensure agent_id is available
            agent_id = getattr(self, 'agent_id', None)
            if not agent_id:
                raise ValueError("Agent ID is required for risk integration")
                
            agent_name = getattr(self, 'agent_name', f"Agent-{agent_id}")
            agent_type = getattr(self, 'agent_type', "trading")
            
            # Create agent info for registration
            agent_info = None
            if auto_register:
                agent_info = {
                    'agent_name': agent_name,
                    'agent_type': agent_type,
                    'max_risk_per_trade': max_risk_per_trade,
                    'max_total_risk': max_total_risk,
                    'allowed_symbols': self.allowed_symbols
                }
            
            # Create the risk client
            self.risk_client = RiskManagerClient(
                base_url=base_url,
                api_key=api_key,
                agent_id=agent_id,
                auto_register=auto_register,
                agent_info=agent_info
            )
        
        # Add risk management tools if the agent supports tools
        if hasattr(self, 'add_tools') and callable(getattr(self, 'add_tools')):
            self.add_risk_tools()
            
        logger.info(f"Risk management integration initialized for agent {self.risk_client.agent_id}")
    
    def add_risk_tools(self):
        """Add risk management tools to the agent."""
        risk_tools = [
            Tool(
                name="check_risk_status",
                func=self.check_risk_status,
                description="Check the current risk status, including portfolio risk and position limits."
            ),
            Tool(
                name="request_trade_approval",
                func=self.request_trade_approval,
                description="Request approval for a trade from the risk manager."
            )
        ]
        
        self.add_tools(risk_tools)
        logger.info(f"Added risk management tools to agent {self.risk_client.agent_id}")
    
    def check_risk_status(self) -> str:
        """
        Check the current risk status.
        
        Returns:
            String representation of the risk status
        """
        try:
            risk_status = self.risk_client.get_risk_status()
            
            # Format the risk status as a string
            status_str = "Current Risk Status:\n"
            status_str += f"- Account Equity: ${risk_status.get('account_equity', 0):,.2f}\n"
            status_str += f"- Current Portfolio Risk: {risk_status.get('current_portfolio_risk_percent', 0):.2f}%\n"
            status_str += f"- Max Portfolio Risk: {risk_status.get('max_portfolio_risk_percent', 0):.2f}%\n"
            status_str += f"- Max Asset Risk: {risk_status.get('max_asset_risk_percent', 0):.2f}%\n"
            
            # Add current positions
            current_positions = risk_status.get('current_positions', {})
            if current_positions:
                status_str += "\nCurrent Positions:\n"
                for symbol, pos in current_positions.items():
                    direction = "LONG" if pos.get('metadata', {}).get('is_long', True) else "SHORT"
                    status_str += f"- {symbol} ({direction}): Size={pos.get('size', 0):.2f}, Value=${pos.get('value', 0):,.2f}, Risk={pos.get('risk_percent', 0):.2f}%\n"
            else:
                status_str += "\nNo current positions.\n"
                
            return status_str
            
        except Exception as e:
            logger.error(f"Error checking risk status: {str(e)}")
            return f"Error checking risk status: {str(e)}"
    
    def request_trade_approval(
        self,
        symbol: str,
        entry_price: float,
        is_long: bool,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        sizer_type: Optional[str] = None,
        sizer_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Request approval for a trade from the risk manager.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            entry_price: Entry price for the trade
            is_long: Whether the trade is long (True) or short (False)
            stop_loss: Stop loss price
            take_profit: Take profit price
            sizer_type: Position sizer type (e.g., "fixed_percent")
            sizer_params: Position sizer parameters
            
        Returns:
            String representation of the approval result
        """
        try:
            approval_data = self.risk_client.request_trade_approval(
                symbol=symbol,
                entry_price=entry_price,
                is_long=is_long,
                stop_loss=stop_loss,
                take_profit=take_profit,
                sizer_type=sizer_type,
                sizer_params=sizer_params
            )
            
            # Format the approval result as a string
            if approval_data.get('approved', False):
                result_str = f"Trade APPROVED:\n"
                result_str += f"- Symbol: {symbol}\n"
                result_str += f"- Direction: {'LONG' if is_long else 'SHORT'}\n"
                result_str += f"- Entry Price: {entry_price}\n"
                if stop_loss:
                    result_str += f"- Stop Loss: {stop_loss}\n"
                if take_profit:
                    result_str += f"- Take Profit: {take_profit}\n"
                result_str += f"- Position Size: {approval_data.get('position_size', 0):.2f}\n"
                result_str += f"- Position Value: ${approval_data.get('position_value', 0):,.2f}\n"
                result_str += f"- Risk Amount: ${approval_data.get('risk_amount', 0):,.2f}\n"
                result_str += f"- Risk Percent: {approval_data.get('risk_percent', 0):.2f}%\n"
                result_str += f"- Approval ID: {approval_data.get('approval_id', 'N/A')}\n"
            else:
                result_str = f"Trade REJECTED:\n"
                result_str += f"- Symbol: {symbol}\n"
                result_str += f"- Direction: {'LONG' if is_long else 'SHORT'}\n"
                result_str += f"- Entry Price: {entry_price}\n"
                result_str += f"- Reason: {approval_data.get('rejection_reason', 'Unknown reason')}\n"
                
            return result_str
            
        except Exception as e:
            logger.error(f"Error requesting trade approval: {str(e)}")
            return f"Error requesting trade approval: {str(e)}"
    
    def execute_trade_with_approval(
        self,
        symbol: str,
        entry_price: float,
        is_long: bool,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        execution_function: Callable[[Dict[str, Any]], Any] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Request trade approval and execute the trade if approved.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            entry_price: Entry price for the trade
            is_long: Whether the trade is long (True) or short (False)
            stop_loss: Stop loss price
            take_profit: Take profit price
            execution_function: Function to call for trade execution if approved
                               (takes the approval_data dict as a parameter)
            
        Returns:
            Tuple of (executed, approval_data)
        """
        return self.risk_client.execute_trade_with_approval(
            symbol=symbol,
            entry_price=entry_price,
            is_long=is_long,
            stop_loss=stop_loss,
            take_profit=take_profit,
            execution_function=execution_function
        )


# Decorator for ensuring trades are approved by the risk manager
def require_risk_approval(f):
    """
    Decorator that ensures a trade function is only executed if approved by the risk manager.
    
    The decorated function must have a 'self' parameter (instance method) and the instance
    must be a RiskAwareAgent or have a risk_client attribute.
    
    The function must also have 'symbol', 'entry_price', and 'is_long' parameters,
    and may optionally have 'stop_loss' and 'take_profit' parameters.
    """
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        # Check if the instance has risk management capabilities
        if not hasattr(self, 'risk_client'):
            logger.error("Cannot apply risk approval: instance has no risk_client")
            raise ValueError("Risk management not initialized")
        
        # Extract parameters from args/kwargs
        # - First try to get them from kwargs
        symbol = kwargs.get('symbol')
        entry_price = kwargs.get('entry_price')
        is_long = kwargs.get('is_long')
        stop_loss = kwargs.get('stop_loss')
        take_profit = kwargs.get('take_profit')
        
        # - If not in kwargs, try to get them from args based on parameter names
        if symbol is None or entry_price is None or is_long is None:
            # Get parameter names from the function
            import inspect
            sig = inspect.signature(f)
            param_names = list(sig.parameters.keys())
            
            # Skip 'self'
            if param_names and param_names[0] == 'self':
                param_names = param_names[1:]
            
            # Map positional args to parameter names
            for i, arg in enumerate(args):
                if i >= len(param_names):
                    break
                    
                param_name = param_names[i]
                if param_name == 'symbol' and symbol is None:
                    symbol = arg
                elif param_name == 'entry_price' and entry_price is None:
                    entry_price = arg
                elif param_name == 'is_long' and is_long is None:
                    is_long = arg
                elif param_name == 'stop_loss' and stop_loss is None:
                    stop_loss = arg
                elif param_name == 'take_profit' and take_profit is None:
                    take_profit = arg
        
        # Ensure required parameters are present
        if symbol is None or entry_price is None or is_long is None:
            logger.error("Cannot apply risk approval: missing required parameters")
            raise ValueError("Missing required parameters for risk approval: symbol, entry_price, is_long")
        
        # Request trade approval
        approval_data = self.risk_client.request_trade_approval(
            symbol=symbol,
            entry_price=entry_price,
            is_long=is_long,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        # Execute the function if approved
        if approval_data.get('approved', False):
            # Add approval data to kwargs
            kwargs['approval_data'] = approval_data
            return f(self, *args, **kwargs)
        else:
            # Log rejection and return None
            reason = approval_data.get('rejection_reason', 'unknown reason')
            logger.warning(f"Trade rejected: {symbol} {'LONG' if is_long else 'SHORT'} at {entry_price} ({reason})")
            return None
    
    return wrapper


class RiskAwareBaseAgent(RiskAwareAgent, BaseAgent):
    """
    Base agent class with integrated risk management capabilities.
    
    This class combines the BaseAgent class with the RiskAwareAgent mixin,
    providing a ready-to-use agent with risk management capabilities.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_type: str = "trading",
        agent_name: str = "Trading Assistant",
        risk_client: Optional[RiskManagerClient] = None,
        base_url: str = "http://localhost:5000",
        api_key: Optional[str] = None,
        auto_register: bool = True,
        max_risk_per_trade: float = 1.0,
        max_total_risk: float = 5.0,
        allowed_symbols: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize the risk-aware base agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type of agent (e.g., "technical", "fundamental", "hybrid")
            agent_name: Human-readable name for the agent
            risk_client: Existing RiskManagerClient instance (created if not provided)
            base_url: Base URL of the Risk Manager API (if creating a new client)
            api_key: API key for authentication (if creating a new client)
            auto_register: Whether to automatically register with the risk manager
            max_risk_per_trade: Maximum risk percentage per trade
            max_total_risk: Maximum total risk percentage
            allowed_symbols: List of symbols the agent is allowed to trade
            **kwargs: Additional arguments passed to BaseAgent
        """
        # Initialize BaseAgent first
        BaseAgent.__init__(
            self,
            agent_id=agent_id,
            agent_type=agent_type,
            agent_name=agent_name,
            **kwargs
        )
        
        # Then initialize RiskAwareAgent
        RiskAwareAgent.__init__(
            self,
            risk_client=risk_client,
            base_url=base_url,
            api_key=api_key,
            auto_register=auto_register,
            max_risk_per_trade=max_risk_per_trade,
            max_total_risk=max_total_risk,
            allowed_symbols=allowed_symbols
        )
        
        logger.info(f"Initialized risk-aware agent: {agent_name} ({agent_id})")


def create_example_risk_aware_agent(
    agent_id: str,
    agent_name: str = "Example Risk-Aware Agent",
    base_url: str = "http://localhost:5000",
    api_key: Optional[str] = None,
    allowed_symbols: Optional[List[str]] = None
) -> RiskAwareBaseAgent:
    """
    Create an example risk-aware agent for testing.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_name: Human-readable name for the agent
        base_url: Base URL of the Risk Manager API
        api_key: API key for authentication
        allowed_symbols: List of symbols the agent is allowed to trade
        
    Returns:
        Initialized RiskAwareBaseAgent instance
    """
    # Create a basic risk-aware agent
    agent = RiskAwareBaseAgent(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type="example",
        agent_role="Example trading agent with risk management",
        agent_description="This agent demonstrates the integration of risk management with trading agents.",
        base_url=base_url,
        api_key=api_key,
        auto_register=True,
        max_risk_per_trade=1.0,
        max_total_risk=3.0,
        allowed_symbols=allowed_symbols or ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        model_name="gpt-3.5-turbo",
        verbose=True
    )
    
    # Add some additional tools specific to this agent
    agent.add_tools([
        Tool(
            name="analyze_market",
            func=lambda symbol: f"Market analysis for {symbol}: The trend is bullish with strong momentum.",
            description="Analyze the market for a given symbol and return a summary."
        ),
        Tool(
            name="get_current_price",
            func=lambda symbol: f"Current price for {symbol}: {1.0 + float(hash(symbol) % 100) / 1000:.4f}",
            description="Get the current price for a given symbol."
        )
    ])
    
    return agent 