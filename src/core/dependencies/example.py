"""
Example usage of the dependency checking system.

This module demonstrates how to use the dependency checking system
with various checks relevant to the trading environment.

To run this example:
    python -m src.core.dependencies.example
"""
import asyncio
import logging
import os
import yaml
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the dependency checking system
from .dependencies import (
    DependencyChecker,
    RedisCheck,
    PostgresCheck,
    BinanceApiCheck,
    FileSystemCheck,
    PortCheck
)


async def check_dependencies(config_path: str = None):
    """
    Run all dependency checks for the trading system.
    
    Args:
        config_path: Path to configuration file
    """
    # Load configuration if provided
    config = {}
    if config_path:
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_path}: {e}")
    
    # Create the dependency checker
    checker = DependencyChecker(config)
    
    # Register filesystem checks
    checker.register_check(
        FileSystemCheck(
            "data",
            check_type="directory",
            check_permissions="rw",
            create_if_missing=True
        )
    )
    checker.register_check(
        FileSystemCheck(
            "logs",
            check_type="directory",
            check_permissions="rw",
            create_if_missing=True
        )
    )
    
    # Register Redis check if configured
    redis_config = config.get("redis", {})
    if redis_config:
        checker.register_check(
            RedisCheck(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                password=redis_config.get("password"),
                db=redis_config.get("db", 0)
            )
        )
    else:
        # Register a basic Redis check as an example
        checker.register_check(
            RedisCheck(
                host="localhost",
                port=6379
            )
        )
    
    # Register PostgreSQL check if configured
    postgres_config = config.get("postgres", {})
    if postgres_config:
        checker.register_check(
            PostgresCheck(
                host=postgres_config.get("host", "localhost"),
                port=postgres_config.get("port", 5432),
                user=postgres_config.get("user", "postgres"),
                password=postgres_config.get("password"),
                database=postgres_config.get("database", "trading"),
                required_tables=postgres_config.get("required_tables", [])
            )
        )
    
    # Register Binance API check if configured
    binance_config = config.get("binance", {})
    if binance_config:
        checker.register_check(
            BinanceApiCheck(
                api_key=binance_config.get("api_key"),
                api_secret=binance_config.get("api_secret")
            )
        )
    else:
        # Register a basic Binance API check without authentication
        checker.register_check(
            BinanceApiCheck()
        )
    
    # Run all checks asynchronously
    logger.info("Running dependency checks...")
    summary = await checker.run_checks_async(verbose=True)
    
    # Print report
    checker.print_report()
    
    # Return overall status
    logger.info(
        f"Dependency checks completed: "
        f"{summary.successful}/{summary.total} checks passed "
        f"({summary.success_rate:.1%}), "
        f"{summary.warnings} warnings, "
        f"{summary.failures} failures"
    )
    
    return summary.failures == 0


async def main():
    """Run the example."""
    logger.info("Starting dependency check example")
    
    # Check for configuration file
    config_path = os.environ.get("CONFIG_PATH")
    if config_path:
        logger.info(f"Using configuration from {config_path}")
    else:
        logger.info("No configuration file specified, using defaults")
    
    # Run dependency checks
    success = await check_dependencies(config_path)
    
    if success:
        logger.info("All critical dependencies are available, system can start")
    else:
        logger.error("Some critical dependencies are not available, system cannot start")


if __name__ == "__main__":
    asyncio.run(main()) 