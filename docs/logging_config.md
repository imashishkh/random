# Forex Trading Dashboard - Logging and Configuration System

This document explains the logging and configuration system for the Forex Trading Dashboard.

## Configuration Management

The Forex Trading Dashboard uses a flexible configuration management system that supports:

- Default configuration
- Environment-specific configuration
- User-specific configuration
- Runtime configuration changes

### Configuration Structure

The configuration system uses a layered approach, with each layer overriding the previous one:

1. **Default Configuration** - Base configuration with sensible defaults
2. **Environment Configuration** - Settings specific to the current environment (development, testing, production)
3. **User Configuration** - User-specific settings that persist across restarts
4. **Runtime Configuration** - Temporary settings that apply only for the current session

### Configuration Files

Configuration files are stored in the `config` directory and use YAML format:

- `config.yaml` - Default configuration
- `config.{environment}.yaml` - Environment-specific configuration (e.g., `config.development.yaml`)
- `user_config.yaml` - User-specific configuration

### Using the Configuration Manager

```python
from src.utils.config_manager import config_manager

# Initialize the configuration system
config_manager.initialize()

# Get configuration values
log_level = config_manager.get_config('logging.level', 'INFO')
database_config = config_manager.get_config('database')

# Change configuration values at runtime
config_manager.set_config('logging.level', 'DEBUG')

# Persist configuration changes
config_manager.set_config('ui.theme', 'dark', persist=True)

# Register a callback for configuration changes
def config_changed(section, value):
    print(f"Configuration changed: {section} = {value}")

config_manager.register_callback('logging', config_changed)

# Switch environments
current_env = config_manager.get_environment()
config_manager.set_environment('production')
```

### Main Configuration Sections

- `general` - General application settings
- `api` - API connection settings
- `database` - Database connection settings
- `logging` - Logging configuration
- `trading` - Trading parameters and settings
- `ui` - User interface settings
- `notifications` - Notification settings
- `security` - Security settings

## Logging System

The Forex Trading Dashboard uses a comprehensive logging system that supports:

- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Multiple output destinations (console, file, JSON)
- Structured logging with components, tags, and extra data
- In-memory log storage with filtering capabilities
- Configuration-based setup

### Log Levels

- `DEBUG` - Detailed information for debugging
- `INFO` - General information about application operation
- `WARNING` - Warning messages about potential issues
- `ERROR` - Error messages about operations that failed
- `CRITICAL` - Critical errors that require immediate attention

### Logging to Multiple Destinations

The logging system can output to multiple destinations:

- **Console** - Output to the terminal
- **File** - Output to a text log file
- **JSON** - Output to a structured JSON log file
- **Memory** - Store logs in memory for later retrieval

### Using the Logger

```python
from src.utils.logger import logger, info, debug, warning, error, critical

# Basic logging
debug("Debug message")
info("Information message")
warning("Warning message")
error("Error message")
critical("Critical error message")

# Structured logging with component and tags
info("User logged in", component="Authentication", tags=["user", "login"])

# Logging with extra data
info(
    "Order executed",
    component="Trading",
    tags=["order", "execution"],
    extra={
        "order_id": "ORD123456",
        "symbol": "EUR/USD",
        "amount": 1000,
        "price": 1.0932
    }
)

# Retrieving logs from memory
all_logs = logger.get_logs()
error_logs = logger.get_logs(level="ERROR")
auth_logs = logger.get_logs(component="Authentication")
login_logs = logger.get_logs(tag="login")
```

### Configuration Integration

The logging system is integrated with the configuration system. When logging settings change in the configuration, the logger automatically reconfigures itself.

```python
# Change log level through configuration
config_manager.set_config('logging.level', 'DEBUG')

# Logger will automatically reconfigure
debug("This debug message will now appear")
```

## Setup and Initialization

To set up the configuration and logging systems:

1. Run the setup script:

```bash
# Set up with default environment (development)
python src/utils/setup.py

# Set up with specific environment
python src/utils/setup.py --env production

# Set up all environments
python src/utils/setup.py --setup-all-envs
```

2. The script will:
   - Create necessary directories
   - Create default configuration files
   - Create environment-specific configuration files
   - Initialize the logging system

## Testing the Integration

To test the integration between the configuration and logging systems:

```bash
python src/utils/test_logging_config.py
```

This script demonstrates:
- Logging at different levels
- Structured logging with components, tags, and extra data
- In-memory log storage and filtering
- Runtime configuration changes
- Environment switching 