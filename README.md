# Forex Trading Risk Manager

A comprehensive risk management system for forex trading that helps control risk exposure, enforce position sizing rules, and provide trade approval based on predefined risk parameters.

## Features

- **Risk Calculation**: Calculate position sizes based on account balance, risk tolerance, and stop loss placement
- **Position Tracking**: Monitor open positions and their risk exposure
- **Agent Management**: Register and manage trading agents with custom risk profiles
- **Trade Approval**: Validate trade requests against risk rules before execution
- **Risk Status Monitoring**: Get real-time risk status and exposure metrics
- **REST API**: Full-featured API for integration with trading systems and external applications
- **Python Client Library**: Easy-to-use client library for interacting with the Risk Manager API
- **Docker Support**: Full Dockerized stack with all necessary services
- **Environment Management**: Secure management of environment variables and secrets

## System Components

The Risk Manager consists of the following components:

1. **Core Logic** (`src/risk/manager.py`): The core risk management functionality
2. **REST API** (`src/risk/api.py`): Flask-based API that exposes the risk management functionality
3. **Client Library** (`src/risk/client.py`): Python client library for interacting with the API
4. **Demo Examples** (`examples/`): Example scripts demonstrating usage
5. **Docker Configuration** (`docker-compose.yml`): Docker Compose configuration for all services
6. **Environment Management** (`docs/secrets-management.md`): Documentation on managing environment variables and secrets

## Network Architecture

The FX-Swarm application uses a multi-network architecture to ensure proper service isolation and security:

- **Frontend Network**: External-facing services accessible from outside
- **Backend Network**: Internal application services, not accessible from outside
- **Data Network**: Database and data storage services, highly restricted
- **Monitoring Network**: Metrics and monitoring services

This architecture ensures that:
- Database services are not directly accessible from the internet
- Internal services communicate over private networks
- Only necessary services are exposed to the frontend

## Installation

### Requirements

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/forex-trading-risk-manager.git
   cd forex-trading-risk-manager
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

The Risk Manager API can be configured through environment variables:

- `RISK_MANAGER_API_KEYS`: Comma-separated list of valid API keys (default: "test_key")
- `SECRET_KEY`: Secret key for Flask application (default: "dev_key_change_in_production")
- `PORT`: Port to run the API server on (default: 5000)
- `DEBUG`: Enable debug mode, "true" or "false" (default: "false")

See the [Environment Variables and Secrets Management](#environment-variables-and-secrets-management) section for more details on configuring the Dockerized stack.

## Deployment Options

### Development Environment

For local development with full debug capabilities:

```bash
./scripts/deploy-dev.sh
```

This configuration:
- Exposes all services on localhost for easy access
- Mounts code directories for live reloading
- Enables debug logging and development tools

### Staging Environment

For testing in a production-like environment:

```bash
./scripts/deploy-staging.sh
```

This configuration:
- Uses production-like settings but with staging data
- Enables some debug capabilities
- Uses similar resource constraints to production

### Production Environment

For deploying to production with full security:

```bash
./scripts/deploy-production.sh
```

This configuration:
- Uses Docker secrets for sensitive information
- Restricts network access to internal services
- Applies strict resource limits
- Disables debug features

## Running the Risk Manager

### Start the API Server

```bash
python -m src.risk.api
```

The API will be available at `http://localhost:5000` by default.

### Using the Client Library

Import the client library and create a client instance:

```python
from src.risk.client import RiskManagerClient, RiskManagerConfig

# Create configuration
config = RiskManagerConfig(
    api_url="http://localhost:5000",
    api_key="test_key",
    agent_id="your-agent-id",  # Optional, for agent-specific operations
    agent_name="Your Agent Name",  # Optional
    agent_type="trading"  # Optional
)

# Create client
client = RiskManagerClient(config)

# Use the client
status = client.get_risk_status()
print(f"Current risk level: {status['risk_level']}")
```

### Running the Demo

The repository includes a demo script that shows how to use the Risk Manager:

```bash
python examples/risk_manager_demo.py
```

Make sure the API server is running before executing the demo.

## API Endpoints

The Risk Manager API provides the following endpoints:

- `/health`: Health check endpoint
- `/risk/status`: Get current risk status
- `/risk/config`: Get or update risk configuration
- `/risk/agents`: Get all agents or register a new agent
- `/risk/agents/<agent_id>`: Get or update a specific agent
- `/risk/positions`: Get all positions or add a new position
- `/risk/positions/<position_id>`: Get or remove a specific position
- `/risk/trades/approve`: Request approval for a trade
- `/risk/calculate`: Calculate position size based on risk parameters

All API requests (except for `/health`) require an API key to be provided in the `X-API-Key` header.

## Usage Examples

### Calculate Position Size

```python
position_size = client.calculate_position_size(
    symbol="EURUSD",
    entry_price=1.1200,
    stop_loss=1.1150,
    risk_percent=1.0
)

print(f"Position size: {position_size['units']} units")
print(f"Risk amount: ${position_size['risk_dollars']}")
```

### Request Trade Approval

```python
approval = client.request_trade_approval(
    symbol="EURUSD",
    direction="long",
    entry_price=1.1200,
    stop_loss=1.1150,
    risk_percent=1.0,
    metadata={"strategy": "trend_following"}
)

if approval["approved"]:
    print("Trade approved!")
    # Execute trade
else:
    print("Trade rejected!")
    for violation in approval["analysis"]["violations"]:
        print(f"Violation: {violation}")
```

### Add a Position

```python
position = client.add_position(
    symbol="EURUSD",
    direction="long",
    entry_price=1.1200,
    stop_loss=1.1150,
    risk_percent=1.0,
    metadata={"strategy": "trend_following"}
)

print(f"Position added with ID: {position['position_id']}")
```

### Get Risk Status

```python
status = client.get_risk_status()
print(f"Account balance: ${status['account_balance']}")
print(f"Risk level: {status['risk_level']}")
print(f"Open positions: {status['position_count']}")
print(f"Total risk exposure: {status['total_risk_percent']}%")
```

## Troubleshooting

### Network Connectivity Issues

**Symptom: Service cannot connect to database**
- Check network assignments in docker-compose.yml
- Verify both services are on the same network
- Check container logs for connection errors

**Symptom: Cannot access service from host**
- Verify port mappings in docker-compose.yml
- Check if service is on the frontend network
- Ensure the service is healthy with `./scripts/health-check.sh`

### Common Docker Issues

**Symptom: Container fails to start**
- Check logs: `docker-compose logs service_name`
- Verify environment variables in .env file
- Check for port conflicts on host machine

**Symptom: Services unhealthy**
- Run health check: `./scripts/health-check.sh`
- Check specific service health: `docker inspect service_name`
- View logs during startup: `docker-compose logs --follow service_name`

## Integrating with Trading Systems

The Risk Manager is designed to be integrated with trading systems through its API. Here's a typical workflow:

1. Register your trading agent with the Risk Manager
2. Before executing a trade, request approval from the Risk Manager
3. If approved, execute the trade and add the position to the Risk Manager
4. Monitor risk status and adjust trading behavior accordingly
5. When closing a position, remove it from the Risk Manager

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Environment Variables and Secrets Management

The project includes a comprehensive environment variables and secrets management system:

### Environment Files

- `.env.development` - Development environment settings
- `.env.staging` - Staging environment settings
- `.env.production` - Production environment settings with Docker secrets
- `.env-example` - Example template with documentation

To set up your environment, copy the appropriate file:

```bash
# For development
cp .env.development .env

# For production
cp .env.production .env
```

### Docker Secrets

For production environments, sensitive information is stored using Docker secrets in the `docker/secrets/` directory. See `docs/secrets-management.md` for detailed information on:

- How to manage secrets in different environments
- Best practices for secure operations
- Secret rotation procedures
- Environment file management

### Environment Validation

A validation script is provided to ensure your environment is correctly configured:

```bash
# Validate the current environment
./scripts/validate-env-config.sh

# Validate a specific environment file
./scripts/validate-env-config.sh .env.production
```

## Running with Docker

To run the full stack using Docker Compose, use the appropriate deployment script:

### Development

```bash
./scripts/deploy-dev.sh
```

### Staging

```bash
./scripts/deploy-staging.sh
```

### Production

```bash
./scripts/deploy-production.sh
```

### Scaling Services

For information on scaling services horizontally or vertically, see [docs/scaling.md](docs/scaling.md).
