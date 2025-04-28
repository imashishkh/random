# Forex Trading AI System: Comprehensive User Guide

## 1. Environment Setup

### 1.1 Operating System Requirements

The system is compatible with:
- Linux (Ubuntu 20.04+ recommended)
- macOS (10.15+ Catalina or newer)
- Windows 10/11 with WSL2 enabled

### 1.2 Required Software

Install the following prerequisites:

```bash
# For Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm docker.io docker-compose curl wget git build-essential

# For macOS
brew update
brew install python3 node docker docker-compose wget git

# For Windows (using WSL2 with Ubuntu)
wsl --install -d Ubuntu
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm docker.io docker-compose curl wget git build-essential
```

### 1.3 Specific Version Requirements

Ensure these specific versions:
- Python 3.9+ (3.10 recommended)
- Node.js 18+
- Docker 20.10+
- Docker Compose 2.0+

### 1.4 Installing TA-Lib (Technical Analysis Library)

TA-Lib is required for technical indicators:

```bash
# For Ubuntu/Debian
sudo apt install -y build-essential
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
pip install ta-lib

# For macOS
brew install ta-lib

# For Windows (WSL2)
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
```

## 2. Codebase Initialization

### 2.1 Clone the Repository

```bash
git clone https://github.com/your-repo/forex-trading-ai-system.git
cd forex-trading-ai-system
```

### 2.2 Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 2.3 Install Node.js Dependencies

```bash
npm install
```

### 2.4 Create and Configure Environment Variables

```bash
cp .env.example .env
```

Edit the `.env` file with your specific configuration values:

```
# Required API Keys
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
OPENAI_API_KEY=your_openai_api_key  # Needed for LLM-based agent features
API_MASTER_KEY=your_master_encryption_key  # Generate with: openssl rand -base64 32

# Trading Configuration
TRADING_MODE=paper  # 'paper' or 'live'
RISK_PERCENTAGE=1.0  # % of capital to risk per trade
MAX_OPEN_POSITIONS=5
DEFAULT_LEVERAGE=1  # No leverage by default
```

### 2.5 Initialize Database Schemas

The system uses multiple databases that need to be initialized:

```bash
# Set up database schemas
docker-compose up -d postgres mongodb redis
python -m src.tools.db_init
```

## 3. API Configuration

### 3.1 Setting Up Binance API Keys

1. Register for a Binance account at https://www.binance.com
2. Enable 2FA for your account (required for API access)
3. Navigate to API Management (under your profile)
4. Create a new API key with these permissions:
   - Spot & Margin Trading: Enabled
   - Futures Trading: Optional
   - Withdrawals: Disabled (for security)
   - Reading data: Enabled
5. Make sure to restrict API access to specific IPs for added security
6. Save the generated `API Key` and `Secret Key`

### 3.2 Securely Storing API Credentials

Add your Binance credentials to the `.env` file:

```
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_key_here
```

For production environments, consider using Docker secrets or a secure key vault service.

### 3.3 Testing API Connectivity

```bash
# Test Binance API connection
python -m src.tools.test_binance_connection
```

You should see:
```
Binance API Connection Test: SUCCESS
Server Time: YYYY-MM-DD HH:MM:SS
Account Status: Active
```

## 4. Running the System

### 4.1 Using Docker Compose (Recommended)

The simplest way to run the entire system is with Docker Compose:

```bash
# Start all services
docker-compose up -d

# Check container status
docker-compose ps

# View logs
docker-compose logs -f
```

This will start:
- API server (FastAPI) on port 8000
- PostgreSQL database on port 5432
- MongoDB on port 27017
- Redis on port 6379
- Celery workers for background tasks
- Celery beat for scheduled tasks

### 4.2 Running Core Components Individually

For development or custom configurations, you can run components separately:

```bash
# Main API server
python -m src.main

# Celery worker for background tasks
celery -A src.worker.celery worker --loglevel=info

# Scheduled tasks
celery -A src.worker.celery beat --loglevel=info

# Web dashboard (Flask)
python app.py
```

### 4.3 Launching the AI Agent Swarm

The AI trading agents can be launched using the CLI tools:

```bash
# Start the agent swarm in paper trading mode
python -m src.cli.agent_launcher --mode paper --pairs EURUSD,GBPUSD,USDJPY --count 5

# Check agent status
python -m src.cli.agent_status
```

The `agent_launcher` arguments:
- `--mode`: 'paper' (simulated) or 'live' (real trading)
- `--pairs`: Comma-separated list of currency pairs to trade
- `--count`: Number of trading agents to deploy per pair
- `--strategies`: Optional comma-separated list of strategies (default: all available)

### 4.4 Dashboard Access

Access the trading dashboard at:
- http://localhost:8000/ (FastAPI endpoints)
- http://localhost:5000/ (Flask dashboard)

## 5. Monitoring & Logging

### 5.1 Accessing Logs

Logs are stored in the `logs/` directory by default, with rotating files:

```bash
# View real-time logs
tail -f logs/api.log
tail -f logs/agents.log
tail -f logs/trades.log
```

### 5.2 Health Checks and System Status

The system provides multiple health endpoints:

```bash
# API health check
curl http://localhost:8000/health

# Agent health metrics
curl http://localhost:8000/api/agents/health -H "X-API-Key: your-api-key"

# For a specific agent
curl http://localhost:8000/api/agents/health/agent-123 -H "X-API-Key: your-api-key"
```

### 5.3 Trade Performance Monitoring

Access trading performance through:

1. Dashboard UI: http://localhost:5000/performance
2. API endpoint: http://localhost:8000/api/performance
3. Command Line: `python -m src.cli.performance_report`

### 5.4 Setting Up Alerts

Configure email/SMS alerts for critical events:

```bash
# Edit the alerts configuration file
nano config/alerts.json

# Test the alert system
python -m src.tools.test_alerts
```

Sample alerts configuration:
```json
{
  "email": {
    "enabled": true,
    "recipients": ["your-email@example.com"],
    "alert_on": ["critical_error", "margin_call", "profit_target"]
  },
  "sms": {
    "enabled": false,
    "phone_numbers": ["+1234567890"],
    "alert_on": ["critical_error", "margin_call"]
  }
}
```

## 6. Best Practices & Automation

### 6.1 Setting Up Cron Jobs

For reliable operation, set up cron jobs to monitor and restart services if needed:

```bash
# Edit crontab
crontab -e

# Add these lines
@reboot cd /path/to/forex-trading-ai-system && docker-compose up -d
*/5 * * * * cd /path/to/forex-trading-ai-system && python -m src.tools.system_health_check
0 0 * * * cd /path/to/forex-trading-ai-system && python -m src.tools.daily_cleanup
```

### 6.2 Safe Shutdown Procedure

Always use the controlled shutdown process to prevent data loss:

```bash
# Graceful shutdown
python -m src.cli.safe_shutdown

# Alternatively with Docker
docker-compose down
```

The `safe_shutdown` script:
1. Signals all trading agents to close positions or transition to safe state
2. Waits for all transactions to complete
3. Securely stores state for next startup
4. Stops all services in the correct order

### 6.3 Data Backup Strategy

Implement regular backups of essential data:

```bash
# Manual backup
python -m src.tools.backup --type full

# Scheduled incremental backups (add to crontab)
0 */6 * * * cd /path/to/forex-trading-ai-system && python -m src.tools.backup --type incremental
```

Backups include:
- Database dumps (PostgreSQL, MongoDB)
- Agent state and configuration
- Trading history and performance metrics
- System configuration and environment variables (encrypted)

### 6.4 Security Best Practices

1. **API Key Protection**:
   - Never share API keys
   - Use IP restrictions on Binance API access
   - Rotate keys monthly

2. **Network Security**:
   - Deploy behind a reverse proxy (Nginx/Caddy)
   - Use SSL/TLS encryption
   - Implement firewall rules

3. **Access Control**:
   - Use the built-in authentication system
   - Implement 2FA for admin access
   - Follow the principle of least privilege

### 6.5 Resource Scaling

As your trading volume increases:

1. Increase resources in `docker-compose.yml`:
   ```yaml
   api:
     deploy:
       resources:
         limits:
           cpus: '2'
           memory: 4G
   ```

2. Add more worker processes:
   ```yaml
   celery_worker:
     deploy:
       replicas: 3
   ```

3. Consider distributed deployment for high-frequency trading

## 7. Troubleshooting Common Issues

### 7.1 Binance API Connectivity

If you encounter API connection issues:

```bash
# Check API status
python -m src.tools.api_health_check

# Verify rate limits
python -m src.tools.check_rate_limits
```

Common solutions:
- Verify API key permissions on Binance dashboard
- Check network connectivity/firewall issues
- Ensure correct time synchronization (Binance requires ±1000ms accuracy)

### 7.2 Agent Performance Issues

If agents are underperforming:

```bash
# Agent performance analysis
python -m src.tools.agent_performance --detailed

# Reset specific agent
python -m src.cli.reset_agent --agent-id agent-123
```

Common solutions:
- Adjust risk parameters in `.env`
- Review strategy configuration
- Check for market condition changes

### 7.3 Database Issues

For database connection problems:

```bash
# Database health check
python -m src.tools.db_health_check

# Database repair utility
python -m src.tools.db_repair
```

### 7.4 System Resource Monitoring

Monitor system resource usage:

```bash
# Resource utilization report
python -m src.tools.resource_monitor

# Memory leak detection
python -m src.tools.memory_profiler
```

## 8. Advanced Configuration

### 8.1 Adding Custom Trading Strategies

Create custom strategies in the `src/strategies/` directory:

```bash
# Generate strategy template
python -m src.tools.generate_strategy --name MyCustomStrategy

# Test strategy with historical data
python -m src.backtesting.backtest --strategy MyCustomStrategy --pair EURUSD --period 30d
```

### 8.2 LLM Integration Configuration

For LLM-enhanced decision making:

```bash
# Configure OpenAI integration
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.7

# Test LLM integration
python -m src.tools.test_llm_integration
```

### 8.3 Risk Management Settings

Fine-tune risk parameters:

```bash
# In .env file
RISK_PERCENTAGE=1.0
MAX_DRAWDOWN_PERCENTAGE=5.0
STOP_LOSS_MULTIPLIER=2.0
TAKE_PROFIT_MULTIPLIER=3.0
```

## 9. Conclusion

You've now set up the Forex Trading AI System that uses autonomous agents to trade on Binance. Remember to:

1. Start with paper trading and smaller position sizes
2. Monitor system performance regularly
3. Keep API keys secure
4. Stay updated with Binance API changes
5. Follow regulatory requirements in your jurisdiction

For ongoing support, refer to the documentation in the `docs/` directory or raise issues on the GitHub repository.

## 10. Additional Resources

- [Binance API Documentation](https://binance-docs.github.io/apidocs/)
- [Technical Analysis Indicators Guide](https://www.investopedia.com/technical-analysis-4689657)
- [Reinforcement Learning for Trading](https://arxiv.org/abs/1911.10107)
- [Risk Management Best Practices](https://www.investopedia.com/articles/forex/08/forex-risk-management.asp) 