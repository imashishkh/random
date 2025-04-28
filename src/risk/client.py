#!/usr/bin/env python3
"""
Risk Manager Client Library

Provides a convenient interface for trading agents to interact with the Risk Manager API,
including methods for:
- Registering agents
- Getting risk status
- Requesting trade approval
- Managing positions
- Handling API authentication
"""

import json
import uuid
import logging
import requests
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

# Setup logging
logger = logging.getLogger(__name__)

@dataclass
class RiskManagerConfig:
    """Configuration for RiskManagerClient"""
    api_url: str = "http://localhost:5000/risk"
    api_key: Optional[str] = None
    timeout: int = 10
    verify_ssl: bool = True
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class RiskManagerClient:
    """
    Client for interacting with the Risk Manager API.
    
    This client provides methods to access all Risk Manager functionality,
    including trade approval, position management, and risk status.
    """
    
    def __init__(self, config: Union[RiskManagerConfig, Dict[str, Any]]):
        """
        Initialize the Risk Manager client.
        
        Args:
            config: Configuration for the client, either as a RiskManagerConfig object
                   or a dictionary with configuration values
        """
        if isinstance(config, dict):
            self.config = RiskManagerConfig(**config)
        else:
            self.config = config
            
        self.api_url = self.config.api_url.rstrip('/')
        self.api_key = self.config.api_key
        self.agent_id = self.config.agent_id
        
        self.http_client = requests.Session()
        self.http_client.verify = self.config.verify_ssl
        
        # Set default headers if API key is provided
        if self.api_key:
            self.http_client.headers.update({
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            })
            
        logger.info(f"Risk Manager client initialized for API at {self.api_url}")
        
        # Register the agent if ID not provided but name is
        if not self.agent_id and self.config.agent_name:
            self._register_agent()
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Risk Manager API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            data: Optional data to send in the request body
            params: Optional query parameters
            
        Returns:
            Dict with API response
            
        Raises:
            Exception: If the API request fails
        """
        url = f"{self.api_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.http_client.get(
                    url, 
                    params=params, 
                    timeout=self.config.timeout
                )
            elif method.upper() == 'POST':
                response = self.http_client.post(
                    url, 
                    json=data, 
                    params=params, 
                    timeout=self.config.timeout
                )
            elif method.upper() == 'PUT':
                response = self.http_client.put(
                    url, 
                    json=data, 
                    params=params, 
                    timeout=self.config.timeout
                )
            elif method.upper() == 'DELETE':
                response = self.http_client.delete(
                    url, 
                    json=data, 
                    params=params, 
                    timeout=self.config.timeout
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            # Raise exception for HTTP errors
            response.raise_for_status()
            
            # Parse JSON response
            if response.content:
                return response.json()
            return {}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling Risk Manager API: {str(e)}")
            raise
    
    def _register_agent(self) -> None:
        """
        Register this client as an agent with the Risk Manager.
        Only executed if agent_id is not provided but agent_name is.
        """
        if not self.config.agent_name:
            logger.warning("Cannot register agent: agent_name not provided")
            return
            
        agent_data = {
            "agent_id": str(uuid.uuid4()),
            "name": self.config.agent_name,
            "type": self.config.agent_type or "trading",
            "metadata": self.config.metadata
        }
        
        try:
            result = self._make_request("POST", "/agents", data=agent_data)
            self.agent_id = result.get("agent_id")
            logger.info(f"Agent registered with ID: {self.agent_id}")
        except Exception as e:
            logger.error(f"Failed to register agent: {str(e)}")
    
    def get_risk_status(self) -> Dict[str, Any]:
        """
        Get the current risk status from the Risk Manager.
        
        Returns:
            Dict with risk status information
        """
        return self._make_request("GET", "/status")
    
    def get_risk_config(self) -> Dict[str, Any]:
        """
        Get the current risk configuration.
        
        Returns:
            Dict with risk configuration
        """
        return self._make_request("GET", "/config")
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate appropriate position size based on risk parameters.
        
        Args:
            symbol: Trading instrument symbol
            entry_price: Entry price of the trade
            stop_loss: Stop loss price
            risk_percent: Optional percentage of account to risk (defaults to max allowed)
            
        Returns:
            Dict with position size details
        """
        data = {
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss": stop_loss
        }
        
        if risk_percent is not None:
            data["risk_percent"] = risk_percent
            
        return self._make_request("POST", "/calculate", data=data)
    
    def request_trade_approval(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
        units: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Request approval for a trade.
        
        Args:
            symbol: Trading instrument symbol
            direction: Trade direction ('long' or 'short')
            entry_price: Entry price of the trade
            stop_loss: Stop loss price
            risk_percent: Optional percentage of account to risk
            units: Optional number of units for the position
            metadata: Optional additional metadata for the trade
            
        Returns:
            Dict with approval result
        """
        data = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "agent_id": self.agent_id,
            "metadata": metadata or {}
        }
        
        # Include risk percent or units, but not both
        if risk_percent is not None:
            data["risk_percent"] = risk_percent
        elif units is not None:
            data["units"] = units
            
        return self._make_request("POST", "/trades/approve", data=data)
    
    def add_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        position_id: Optional[str] = None,
        risk_percent: Optional[float] = None,
        units: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a new position to the Risk Manager.
        
        Args:
            symbol: Trading instrument symbol
            direction: Position direction ('long' or 'short')
            entry_price: Entry price of the position
            stop_loss: Stop loss price
            position_id: Optional position ID (generated if not provided)
            risk_percent: Optional percentage of account risked
            units: Optional number of units for the position
            metadata: Optional additional metadata for the position
            
        Returns:
            Dict with the added position details
        """
        data = {
            "position_id": position_id or str(uuid.uuid4()),
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "agent_id": self.agent_id,
            "metadata": metadata or {}
        }
        
        # Include risk percent or units, but not both
        if risk_percent is not None:
            data["risk_percent"] = risk_percent
        elif units is not None:
            data["units"] = units
            
        return self._make_request("POST", "/positions", data=data)
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions from the Risk Manager.
        
        Returns:
            List of position dictionaries
        """
        result = self._make_request("GET", "/positions")
        return result.get("positions", [])
    
    def get_position(self, position_id: str) -> Dict[str, Any]:
        """
        Get a specific position by ID.
        
        Args:
            position_id: ID of the position to retrieve
            
        Returns:
            Dict with position details
        """
        return self._make_request("GET", f"/positions/{position_id}")
    
    def remove_position(self, position_id: str) -> bool:
        """
        Remove a position from the Risk Manager.
        
        Args:
            position_id: ID of the position to remove
            
        Returns:
            Boolean indicating success
        """
        result = self._make_request("DELETE", f"/positions/{position_id}")
        return result.get("success", False)
    
    def get_agents(self) -> List[Dict[str, Any]]:
        """
        Get all registered agents.
        
        Returns:
            List of agent dictionaries
        """
        result = self._make_request("GET", "/agents")
        return result.get("agents", [])
    
    def get_agent(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a specific agent by ID.
        
        Args:
            agent_id: ID of the agent to retrieve (defaults to this client's agent_id)
            
        Returns:
            Dict with agent details
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("No agent_id provided or set in client")
            
        return self._make_request("GET", f"/agents/{agent_id}")
    
    def update_agent(
        self,
        updates: Dict[str, Any],
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an agent's details.
        
        Args:
            updates: Dictionary of fields to update
            agent_id: ID of the agent to update (defaults to this client's agent_id)
            
        Returns:
            Dict with updated agent details
        """
        agent_id = agent_id or self.agent_id
        if not agent_id:
            raise ValueError("No agent_id provided or set in client")
            
        return self._make_request("PUT", f"/agents/{agent_id}", data=updates)


# Example usage
if __name__ == "__main__":
    # Create client
    client = RiskManagerClient(
        config={
            "api_url": "http://localhost:5000/risk",
            "api_key": "your_api_key",
            "agent_name": "Example Forex Agent",
            "agent_type": "forex"
        }
    )
    
    # Register agent
    registration = client.register_agent(
        name="Example Forex Agent",
        agent_type="forex",
        description="An example trading agent for testing",
        risk_limits={
            "max_risk_per_trade": 1.0,
            "max_concurrent_trades": 5
        }
    )
    
    # Get risk status
    status = client.get_risk_status()
    print(f"Risk status: {json.dumps(status, indent=2)}")
    
    # Request trade approval
    approval = client.request_trade_approval(
        symbol="EURUSD",
        direction="long",
        entry_price=1.1850,
        stop_loss=1.1800,
        risk_percent=1.0
    )
    
    print(f"Trade approval: {json.dumps(approval, indent=2)}")
    
    # Add position if approved
    if approval.get('status') == 'approved':
        position = client.add_position(
            symbol="EURUSD",
            direction="long",
            entry_price=1.1850,
            stop_loss=1.1800,
            units=approval.get('position', {}).get('units')
        )
        
        position_id = position.get('position_id')
        print(f"Added position: {json.dumps(position, indent=2)}")
        
        # Remove position
        client.remove_position(position_id) 