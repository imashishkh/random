# Forex Trading Bot

A comprehensive Forex trading system designed for automated trading with risk management, technical analysis, and real-time market data integration.

## Key Features

- Advanced risk management system with position sizing and circuit breakers
- Technical and fundamental analysis agents
- Real-time market data collection from various exchanges
- Backtesting capabilities with performance metrics
- Dashboard for monitoring trading performance and positions
- Command-line interface for managing the bot
- Extensible architecture supporting custom strategies

## Project Structure

The project is organized into modular components:

- `src/agents`: Trading agents for market analysis and signal generation
- `src/risk`: Risk management tools and position sizing
- `src/exchange`: Exchange connectivity and market data handling
- `src/analytics`: Trading performance analysis and reporting
- `src/backtesting`: Backtesting tools and historical data management
- `src/dashboard`: Performance monitoring and visualization
- `src/core`: Core system components and orchestration

## Getting Started

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure exchange API keys in the configuration files
4. Run the bot: `python src/main.py`

## Documentation

For detailed documentation on using the Forex Trading Bot, refer to the following:

- `README-dashboard.md`: Dashboard usage guide
- `README-airflow-grafana.md`: Integration with Airflow and Grafana
- `README-task-master.md`: Task management system documentation
- `UserGuide.md`: Comprehensive user guide

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
