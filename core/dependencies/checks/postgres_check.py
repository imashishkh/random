"""
PostgreSQL dependency check for the Forex Trading system.

This module provides a dependency check that verifies PostgreSQL database
connectivity and validates the presence of required tables and schema.
"""

import asyncio
import asyncpg
from typing import Dict, Any, List, Set, Optional

from core.dependencies.checker import DependencyCheck, CheckResult, CheckStatus
from core.config import ConfigManager


class PostgresCheck(DependencyCheck):
    """
    Dependency check for PostgreSQL database connectivity and schema validation.
    
    This check validates that PostgreSQL is accessible, can be authenticated to,
    and contains the required tables for the Forex Trading system.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the PostgreSQL check with configuration.
        
        Args:
            config_manager: The configuration manager containing PostgreSQL settings.
        """
        super().__init__(
            name="postgres",
            description="Checks PostgreSQL connectivity and required tables",
            dependencies=[],  # PostgreSQL has no direct system dependencies
            priority=1  # High priority as other services will depend on database
        )
        self.config_manager = config_manager
    
    def _get_postgres_config(self) -> Dict[str, Any]:
        """
        Extract PostgreSQL configuration from the config manager.
        
        Returns:
            Dict containing PostgreSQL connection parameters.
        """
        postgres_config = self.config_manager.get("postgres", {})
        return {
            "host": postgres_config.get("host", "localhost"),
            "port": postgres_config.get("port", 5432),
            "user": postgres_config.get("user", "postgres"),
            "password": postgres_config.get("password", ""),
            "database": postgres_config.get("database", "forex_trading"),
            "required_tables": postgres_config.get("required_tables", [])
        }
    
    def run(self) -> CheckResult:
        """
        This is a synchronous placeholder that raises an exception.
        PostgreSQL checks should use the async version.
        
        Returns:
            CheckResult: Always returns a failure result.
        """
        return CheckResult(
            status=CheckStatus.FAILURE,
            message="PostgreSQL check must be run using the async interface."
        )
    
    async def run_async(self) -> CheckResult:
        """
        Run the PostgreSQL dependency check asynchronously.
        
        Checks:
        1. Connection to database
        2. Authentication success
        3. Presence of required tables
        
        Returns:
            CheckResult: The result of the PostgreSQL connectivity and validation check.
        """
        postgres_config = self._get_postgres_config()
        required_tables = set(postgres_config.pop("required_tables", []))
        
        try:
            # Create a connection to the database
            conn = await asyncpg.connect(
                host=postgres_config.get("host"),
                port=postgres_config.get("port"),
                user=postgres_config.get("user"),
                password=postgres_config.get("password"),
                database=postgres_config.get("database")
            )
            
            # Test the connection with a simple query
            await conn.execute("SELECT 1")
            
            # Check for required tables if specified
            missing_tables = set()
            if required_tables:
                existing_tables = await self._get_existing_tables(conn)
                missing_tables = required_tables - existing_tables
            
            # Close the connection
            await conn.close()
            
            # If there are missing required tables, return a failure
            if missing_tables:
                return CheckResult(
                    status=CheckStatus.FAILURE,
                    message="PostgreSQL is missing required tables.",
                    details={
                        "missing_tables": list(missing_tables),
                        "host": postgres_config.get("host"),
                        "database": postgres_config.get("database")
                    }
                )
            
            return CheckResult(
                status=CheckStatus.SUCCESS,
                message="PostgreSQL connection and schema validation successful.",
                details={
                    "host": postgres_config.get("host"),
                    "database": postgres_config.get("database")
                }
            )
            
        except asyncpg.exceptions.PostgresError as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"Failed to connect to PostgreSQL: {str(e)}",
                details={
                    "host": postgres_config.get("host"),
                    "port": postgres_config.get("port"),
                    "database": postgres_config.get("database"),
                    "error": str(e)
                }
            )
        except Exception as e:
            return CheckResult(
                status=CheckStatus.FAILURE,
                message=f"PostgreSQL check failed with an unexpected error: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _get_existing_tables(self, conn: asyncpg.Connection) -> Set[str]:
        """
        Get the set of existing tables in the database.
        
        Args:
            conn: The asyncpg connection to the database.
            
        Returns:
            Set of table names that exist in the database.
        """
        tables_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
        tables = await conn.fetch(tables_query)
        return {table['table_name'] for table in tables} 