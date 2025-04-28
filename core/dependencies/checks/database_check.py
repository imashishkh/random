"""
Database dependency check for the Forex Trading system.

This module provides a dependency check that verifies connectivity and
basic functionality of the database used by the system.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text, create_engine, Engine

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


logger = logging.getLogger(__name__)


class DatabaseCheck(DependencyCheck):
    """
    Dependency check for database connection and functionality.
    
    This check verifies connectivity to the database server and validates
    basic operations such as simple queries to ensure the database is
    functioning properly.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the database dependency check with configuration.
        
        Args:
            config_manager: The configuration manager containing database connection settings.
        """
        super().__init__(
            name="database",
            description="Checks connectivity and functionality of the database",
            dependencies=[],  # Database typically doesn't depend on other services
            priority=0  # Highest priority as most services depend on the database
        )
        self.config_manager = config_manager
    
    def _get_db_config(self) -> Dict[str, Any]:
        """
        Extract database configuration from the config manager.
        
        Returns:
            Dictionary containing database connection parameters.
        """
        db_config = self.config_manager.get("database", {})
        
        # Default database configuration if not specified
        default_config = {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "name": "forex",
            "user": "forex_user",
            "password": None,
            "ssl": False,
            "timeout": 5
        }
        
        # Merge provided config with defaults
        for key, default_value in default_config.items():
            if key not in db_config:
                db_config[key] = default_value
                
        return db_config
    
    def _build_connection_string(self, db_config: Dict[str, Any], async_mode: bool = False) -> str:
        """
        Build the database connection string based on configuration.
        
        Args:
            db_config: Database configuration dictionary
            async_mode: Whether to build an async connection string
            
        Returns:
            Database connection string
        """
        db_type = db_config["type"]
        
        # Prefix for async drivers
        if async_mode:
            if db_type == "postgresql":
                db_type = "postgresql+asyncpg"
            elif db_type == "mysql":
                db_type = "mysql+aiomysql"
            elif db_type == "sqlite":
                db_type = "sqlite+aiosqlite"
            else:
                logger.warning(f"Async mode requested for unsupported database type: {db_type}")
                # Fall back to synchronous for unsupported types
        
        # Build connection string based on database type
        if db_type == "sqlite" or db_type == "sqlite+aiosqlite":
            # For SQLite, the db_name is actually the file path
            return f"{db_type}:///{db_config['name']}"
        else:
            # For other database types
            user_part = f"{db_config['user']}"
            if db_config.get("password"):
                user_part += f":{db_config['password']}"
                
            host_part = f"{db_config['host']}"
            if db_config.get("port"):
                host_part += f":{db_config['port']}"
            
            db_name = db_config["name"]
            
            # Construct the connection string
            conn_str = f"{db_type}://{user_part}@{host_part}/{db_name}"
            
            # Add SSL mode if specified
            if db_config.get("ssl", False):
                conn_str += "?sslmode=require"
                
            return conn_str
    
    def _test_basic_query(self, engine: Engine) -> Tuple[bool, str]:
        """
        Test a basic SQL query to verify database functionality.
        
        Args:
            engine: SQLAlchemy engine connected to the database
            
        Returns:
            Tuple with success status and message
        """
        try:
            with engine.connect() as conn:
                # Test with a simple query that should work on any database
                result = conn.execute(text("SELECT 1"))
                row = result.fetchone()
                
                if row and row[0] == 1:
                    return True, "Basic query executed successfully"
                else:
                    return False, f"Basic query returned unexpected result: {row}"
        except Exception as e:
            return False, f"Error executing basic query: {str(e)}"
    
    async def _test_basic_query_async(self, engine: AsyncEngine) -> Tuple[bool, str]:
        """
        Test a basic SQL query asynchronously to verify database functionality.
        
        Args:
            engine: Async SQLAlchemy engine connected to the database
            
        Returns:
            Tuple with success status and message
        """
        try:
            async with engine.connect() as conn:
                # Test with a simple query that should work on any database
                result = await conn.execute(text("SELECT 1"))
                row = result.fetchone()
                
                if row and row[0] == 1:
                    return True, "Basic query executed successfully"
                else:
                    return False, f"Basic query returned unexpected result: {row}"
        except Exception as e:
            return False, f"Error executing basic query: {str(e)}"
    
    def run(self) -> CheckResult:
        """
        Run the database dependency check synchronously.
        
        Returns:
            CheckResult: The result of the database connectivity check.
        """
        db_config = self._get_db_config()
        
        # Create a configuration without password for logging
        log_config = db_config.copy()
        if "password" in log_config and log_config["password"]:
            log_config["password"] = "******"
        
        logger.debug(f"Checking database connection with config: {log_config}")
        
        # Build connection string
        connection_string = self._build_connection_string(db_config)
        
        try:
            # Create engine with timeout
            engine = create_engine(
                connection_string,
                connect_args={"connect_timeout": db_config.get("timeout", 5)},
                pool_pre_ping=True
            )
            
            # Test connection by performing a basic query
            query_success, query_message = self._test_basic_query(engine)
            
            if query_success:
                return CheckResult(
                    status=CheckStatus.SUCCESS,
                    message="Database connection successful and operations verified",
                    details={
                        "db_type": db_config["type"],
                        "host": db_config["host"],
                        "port": db_config["port"],
                        "database": db_config["name"],
                        "query_result": query_message
                    }
                )
            else:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message=f"Database connected but query test failed: {query_message}",
                    details={
                        "db_type": db_config["type"],
                        "host": db_config["host"],
                        "port": db_config["port"],
                        "database": db_config["name"]
                    }
                )
                
        except sqlalchemy.exc.OperationalError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Database operational error: {str(e)}",
                details={
                    "db_type": db_config["type"],
                    "host": db_config["host"],
                    "port": db_config["port"],
                    "database": db_config["name"],
                    "error": str(e)
                }
            )
        except sqlalchemy.exc.SQLAlchemyError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Database connection error: {str(e)}",
                details={
                    "db_type": db_config["type"],
                    "error": str(e)
                }
            )
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Unexpected error checking database: {str(e)}",
                details={"error": str(e)}
            )
    
    async def run_async(self) -> CheckResult:
        """
        Run the database dependency check asynchronously.
        
        Returns:
            CheckResult: The result of the database connectivity check.
        """
        db_config = self._get_db_config()
        
        # Create a configuration without password for logging
        log_config = db_config.copy()
        if "password" in log_config and log_config["password"]:
            log_config["password"] = "******"
        
        logger.debug(f"Checking database connection asynchronously with config: {log_config}")
        
        # Build connection string
        connection_string = self._build_connection_string(db_config, async_mode=True)
        
        try:
            # Create async engine with timeout
            engine = create_async_engine(
                connection_string,
                connect_args={"timeout": db_config.get("timeout", 5)},
                pool_pre_ping=True
            )
            
            # Test connection with a simple query
            query_success, query_message = await self._test_basic_query_async(engine)
            
            if query_success:
                return CheckResult(
                    status=CheckStatus.SUCCESS,
                    message="Database connection successful and operations verified",
                    details={
                        "db_type": db_config["type"],
                        "host": db_config["host"],
                        "port": db_config["port"],
                        "database": db_config["name"],
                        "query_result": query_message
                    }
                )
            else:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message=f"Database connected but query test failed: {query_message}",
                    details={
                        "db_type": db_config["type"],
                        "host": db_config["host"],
                        "port": db_config["port"],
                        "database": db_config["name"]
                    }
                )
                
        except sqlalchemy.exc.OperationalError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Database operational error: {str(e)}",
                details={
                    "db_type": db_config["type"],
                    "host": db_config["host"],
                    "port": db_config["port"],
                    "database": db_config["name"],
                    "error": str(e)
                }
            )
        except sqlalchemy.exc.SQLAlchemyError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Database connection error: {str(e)}",
                details={
                    "db_type": db_config["type"],
                    "error": str(e)
                }
            )
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Unexpected error checking database: {str(e)}",
                details={"error": str(e)}
            )
        finally:
            if 'engine' in locals():
                await engine.dispose() 