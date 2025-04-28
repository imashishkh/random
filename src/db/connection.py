"""
Database connection module with connection pooling and retry mechanisms.

This module provides functionality for establishing and managing database connections,
including connection pooling, retry logic, and error handling.
"""

import logging
import os
import time
from typing import Optional, Callable, TypeVar, Any, List, Dict, Union, Tuple
import contextlib
from functools import wraps

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, execute_values, Json
from psycopg2.extensions import connection, cursor
from dotenv import load_dotenv

from .exceptions import ConnectionError, TransactionError

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Database connection parameters from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Connection pool configuration
MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "1"))
MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "10"))
MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "0.5"))
MOCK_DB = os.getenv("MOCK_DB", "false").lower() == "true"

# Connection metrics
connection_metrics = {
    "created": 0,
    "acquired": 0,
    "released": 0,
    "errors": 0,
    "retries": 0,
    "active": 0
}

# Custom exception classes
class DatabaseError(Exception):
    """Base class for database-related exceptions."""
    pass

class QueryError(DatabaseError):
    """Exception raised for query-related errors."""
    pass

# Type variable for generic return types
T = TypeVar('T')

class DatabaseConnectionManager:
    """Manages database connections with connection pooling and retry logic."""

    _instance = None
    _connection_pool = None
    _mock_mode = False

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super(DatabaseConnectionManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        dbname: str = None,
        user: str = None,
        password: str = None,
        host: str = None,
        port: str = None,
        min_connections: int = 1,
        max_connections: int = 10
    ):
        """
        Initialize the connection manager.

        Args:
            dbname: Database name
            user: Database user
            password: Database password
            host: Database host
            port: Database port
            min_connections: Minimum number of connections in the pool
            max_connections: Maximum number of connections in the pool
        """
        # Skip initialization if already initialized (singleton pattern)
        if self._initialized:
            return

        # Check for mock mode
        self._mock_mode = MOCK_DB
        if self._mock_mode:
            logger.info("Running in database mock mode. No actual database connections will be established.")
            self._initialized = True
            return

        # Use environment variables if parameters not provided
        self.dbname = dbname or os.environ.get("DB_NAME", "forexdb")
        self.user = user or os.environ.get("DB_USER", "postgres")
        self.password = password or os.environ.get("DB_PASSWORD", "postgres")
        self.host = host or os.environ.get("DB_HOST", "localhost")
        self.port = port or os.environ.get("DB_PORT", "5432")
        self.min_connections = min_connections
        self.max_connections = max_connections

        self._conn_params = {
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            "host": self.host,
            "port": self.port
        }

        self._initialize_pool()
        self._initialized = True

    def _initialize_pool(self) -> None:
        """
        Initialize the connection pool.

        Raises:
            ConnectionError: If the connection pool cannot be initialized
        """
        if self._mock_mode:
            logger.info("Skipping connection pool initialization in mock mode")
            return

        try:
            self._connection_pool = pool.ThreadedConnectionPool(
                self.min_connections,
                self.max_connections,
                **self._conn_params
            )
            logger.info(
                f"Initialized connection pool with {self.min_connections} to {self.max_connections} connections")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise ConnectionError(f"Failed to initialize connection pool: {e}")

    def get_connection(self) -> connection:
        """
        Get a connection from the pool.

        Returns:
            Database connection

        Raises:
            ConnectionError: If a connection cannot be obtained
        """
        if self._mock_mode:
            logger.debug("Returning mock connection in mock mode")
            return None

        if self._connection_pool is None:
            self._initialize_pool()

        try:
            conn = self._connection_pool.getconn()
            logger.debug("Obtained connection from pool")
            return conn
        except psycopg2.Error as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise ConnectionError(f"Failed to get connection from pool: {e}")

    def release_connection(self, conn: connection) -> None:
        """
        Release a connection back to the pool.

        Args:
            conn: The connection to release

        Raises:
            ConnectionError: If the connection cannot be released
        """
        if self._mock_mode or conn is None:
            logger.debug("Skipping connection release in mock mode")
            return

        if self._connection_pool is None:
            logger.warning("Attempting to release connection but pool is None")
            return

        try:
            self._connection_pool.putconn(conn)
            logger.debug("Released connection back to pool")
        except psycopg2.Error as e:
            logger.error(f"Failed to release connection: {e}")
            raise ConnectionError(f"Failed to release connection: {e}")

    def close_all_connections(self) -> None:
        """
        Close all connections in the pool.

        Raises:
            ConnectionError: If connections cannot be closed
        """
        if self._connection_pool is None:
            logger.warning("Attempting to close connections but pool is None")
            return

        try:
            self._connection_pool.closeall()
            logger.info("Closed all connections in the pool")
            self._connection_pool = None
        except psycopg2.Error as e:
            logger.error(f"Failed to close connections: {e}")
            raise ConnectionError(f"Failed to close connections: {e}")

    @contextlib.contextmanager
    def get_connection_context(self):
        """
        Context manager for database connections.

        Yields:
            Database connection that will be automatically released
        """
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn is not None:
                self.release_connection(conn)

    @contextlib.contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Yields:
            Database connection with active transaction that will be committed or rolled back
        """
        conn = None
        try:
            conn = self.get_connection()
            conn.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
            yield conn
            conn.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            if conn is not None:
                conn.rollback()
                logger.debug("Transaction rolled back")
            logger.error(f"Transaction error: {e}")
            raise TransactionError(f"Transaction failed: {e}")
        finally:
            if conn is not None:
                self.release_connection(conn)


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple = (psycopg2.OperationalError, psycopg2.InterfaceError)):
    """
    Retry decorator for database operations.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch and retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 1
            current_delay = delay
            last_exception = None

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {current_delay}s...")

                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    attempt += 1

            logger.error(
                f"All {max_attempts} attempts failed. Last error: {last_exception}")
            raise last_exception

        return wrapper
    return decorator


# Create a singleton instance for easy import
connection_manager = DatabaseConnectionManager()


def get_connection() -> connection:
    """
    Get a database connection.

    Returns:
        Database connection
    """
    return connection_manager.get_connection()


def release_connection(conn: connection) -> None:
    """
    Release a database connection.

    Args:
        conn: The connection to release
    """
    connection_manager.release_connection(conn)


@contextlib.contextmanager
def get_connection_context():
    """
    Context manager for database connections.

    Yields:
        Database connection that will be automatically released
    """
    with connection_manager.get_connection_context() as conn:
        yield conn


@contextlib.contextmanager
def transaction():
    """
    Context manager for database transactions.

    Yields:
        Database connection with active transaction that will be committed or rolled back
    """
    with connection_manager.transaction() as conn:
        yield conn


def get_db_connection_with_retry(max_retries: int = MAX_RETRIES, 
                                retry_delay: float = RETRY_DELAY) -> connection:
    """
    Get a database connection from the pool with retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries in seconds (will use exponential backoff)
    
    Returns:
        psycopg2.connection: Database connection
    
    Raises:
        ConnectionError: If connection fails after all retries
    """
    if connection_manager._connection_pool is None:
        connection_manager._initialize_pool()
    
    retries = 0
    last_exception = None
    
    while retries < max_retries:
        try:
            conn = connection_manager._connection_pool.getconn()
            connection_metrics["acquired"] += 1
            connection_metrics["active"] += 1
            logger.debug(f"Acquired database connection (active: {connection_metrics['active']})")
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_exception = e
            retries += 1
            connection_metrics["retries"] += 1
            logger.warning(f"Database connection attempt {retries}/{max_retries} failed: {e}")
            
            if retries < max_retries:
                # Exponential backoff
                sleep_time = retry_delay * (2 ** (retries - 1))
                logger.debug(f"Retrying in {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
    
    connection_metrics["errors"] += 1
    logger.error(f"Database connection failed after {max_retries} attempts")
    raise ConnectionError(f"Failed to connect to database: {last_exception}")


@contextlib.contextmanager
def get_db_connection() -> contextlib.contextmanager:
    """
    Get a database connection from the pool.
    
    Yields:
        Database connection that will be automatically closed
    """
    conn = None
    try:
        conn = get_db_connection_with_retry()
        yield conn
    except Exception as e:
        logger.error(f"Error in database connection context: {e}")
        raise
    finally:
        if conn is not None:
            connection_manager._connection_pool.putconn(conn)
            connection_metrics["released"] += 1
            connection_metrics["active"] -= 1
            logger.debug(f"Released database connection (active: {connection_metrics['active']})")


@contextlib.contextmanager
def get_db_cursor(cursor_factory=None) -> contextlib.contextmanager:
    """
    Get a database cursor within a connection context.
    
    Args:
        cursor_factory: Optional cursor factory class
        
    Yields:
        Database cursor that will be automatically closed
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error, rolling back transaction: {e}")
            raise QueryError(f"Database query failed: {e}")
        finally:
            cursor.close()


def execute_query(query: str, params: Optional[tuple] = None,
                 fetch_all: bool = True) -> Any:
    """
    Execute a database query and return the results.
    
    Args:
        query: SQL query string
        params: Query parameters
        fetch_all: Whether to fetch all results or just one
    
    Returns:
        Query results as list of dictionaries, single dictionary, or None
    
    Raises:
        QueryError: If query execution fails
    """
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            start_time = time.time()
            cursor.execute(query, params)
            
            if cursor.description is None:  # No results expected (INSERT, UPDATE, etc.)
                return None
                
            if fetch_all:
                result = cursor.fetchall()
            else:
                result = cursor.fetchone()
                
            query_time = time.time() - start_time
            if query_time > 1.0:  # Log slow queries
                logger.warning(f"Slow query ({query_time:.2f}s): {query[:100]}...")
            
            return result
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        logger.debug(f"Failed query: {query}")
        logger.debug(f"Parameters: {params}")
        raise QueryError(f"Database query failed: {e}")


def execute_batch(query: str, params_list: List[tuple]) -> int:
    """
    Execute a batch query with multiple parameter sets.
    
    Args:
        query: SQL query string
        params_list: List of parameter tuples
    
    Returns:
        Number of rows affected
    
    Raises:
        QueryError: If query execution fails
    """
    try:
        with get_db_cursor() as cursor:
            start_time = time.time()
            cursor.executemany(query, params_list)
            affected_rows = cursor.rowcount
            
            query_time = time.time() - start_time
            if query_time > 2.0:  # Log very slow batch operations
                logger.warning(f"Slow batch operation ({query_time:.2f}s, {len(params_list)} items): {query[:100]}...")
            
            return affected_rows
    except Exception as e:
        logger.error(f"Batch query execution failed: {e}")
        raise QueryError(f"Database batch query failed: {e}")


def execute_values_query(table: str, columns: List[str], values: List[List]) -> int:
    """
    Insert multiple rows of values into a table using execute_values.
    
    Args:
        table: Table name
        columns: Column names
        values: List of value lists
    
    Returns:
        Number of rows affected
    
    Raises:
        QueryError: If query execution fails
    """
    try:
        with get_db_cursor() as cursor:
            start_time = time.time()
            query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
            execute_values(cursor, query, values)
            affected_rows = cursor.rowcount
            
            query_time = time.time() - start_time
            if query_time > 2.0:  # Log very slow batch operations
                logger.warning(f"Slow execute_values ({query_time:.2f}s, {len(values)} items): {query[:100]}...")
            
            return affected_rows
    except Exception as e:
        logger.error(f"Execute values query failed: {e}")
        raise QueryError(f"Database execute_values failed: {e}")


def copy_from_records(table: str, columns: List[str], records: List[tuple]) -> int:
    """
    Insert multiple rows using COPY for maximum performance.
    
    Args:
        table: Table name
        columns: Column names
        records: List of record tuples
    
    Returns:
        Number of rows affected
    
    Raises:
        QueryError: If query execution fails
    """
    import io
    import csv
    
    try:
        with get_db_connection() as conn:
            # Create a file-like object
            output = io.StringIO()
            writer = csv.writer(output, delimiter='\t')
            
            # Write all records
            for record in records:
                writer.writerow(record)
                
            # Reset position to start
            output.seek(0)
            
            # Execute COPY
            start_time = time.time()
            with conn.cursor() as cursor:
                cursor.copy_from(
                    output,
                    table,
                    columns=columns,
                    null=''  # Empty strings represent NULL
                )
                affected_rows = cursor.rowcount
                
                query_time = time.time() - start_time
                if query_time > 2.0:  # Log very slow COPY operations
                    logger.warning(f"Slow COPY operation ({query_time:.2f}s, {len(records)} items)")
                
                return affected_rows
    except Exception as e:
        logger.error(f"COPY operation failed: {e}")
        raise QueryError(f"Database COPY operation failed: {e}")


def get_connection_metrics() -> Dict[str, int]:
    """Get current connection metrics."""
    return connection_metrics.copy()


def set_rls_context(conn: connection, agent_id: str) -> None:
    """
    Set row-level security context for a connection.
    
    Args:
        conn: Database connection
        agent_id: Agent ID for RLS
    """
    with conn.cursor() as cursor:
        cursor.execute("SET LOCAL forex.current_agent_id = %s", (agent_id,))


def close_connection(conn: connection) -> None:
    """
    Close a database connection manually.
    
    Args:
        conn: The connection to close
    """
    if conn is not None:
        conn.close()
        logger.debug("Closed database connection")


def init_db() -> bool:
    """
    Initialize the database, creating tables if they don't exist.
    
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    # In mock mode, just return success
    if MOCK_DB:
        logger.info("Mock mode enabled, skipping database initialization")
        return True
        
    try:
        conn = get_connection()
        
        # Execute initialization script
        with conn.cursor() as cursor:
            # Create tables if they don't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_states (
                    agent_id VARCHAR(50) PRIMARY KEY,
                    agent_name VARCHAR(100) NOT NULL,
                    current_balance NUMERIC(20, 8) NOT NULL,
                    available_balance NUMERIC(20, 8) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    last_heartbeat TIMESTAMP NOT NULL,
                    configuration JSONB NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS positions (
                    position_id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    entry_price NUMERIC(20, 8) NOT NULL,
                    current_price NUMERIC(20, 8) NOT NULL,
                    unrealized_pnl NUMERIC(20, 8) NOT NULL,
                    realized_pnl NUMERIC(20, 8) DEFAULT 0,
                    status VARCHAR(20) NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    exit_time TIMESTAMP,
                    agent_id VARCHAR(50) NOT NULL REFERENCES agent_states(agent_id),
                    metadata JSONB
                );
                
                CREATE TABLE IF NOT EXISTS trade_fills (
                    trade_fill_id SERIAL PRIMARY KEY,
                    trade_id VARCHAR(50) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    executed_at TIMESTAMP NOT NULL,
                    fee NUMERIC(20, 8) NOT NULL,
                    fee_asset VARCHAR(10) NOT NULL,
                    order_id VARCHAR(50) NOT NULL,
                    agent_id VARCHAR(50) NOT NULL REFERENCES agent_states(agent_id),
                    position_id INTEGER REFERENCES positions(position_id)
                );
                
                CREATE TABLE IF NOT EXISTS risk_alerts (
                    alert_id SERIAL PRIMARY KEY,
                    agent_id VARCHAR(50) NOT NULL REFERENCES agent_states(agent_id),
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    metadata JSONB
                );
            """)
            
        conn.commit()
        logger.info("Database initialized successfully")
        close_connection(conn)
        return True
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False


# Type variable for the retry decorator
T = TypeVar('T')

def retry_on_transient_error(
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY,
    transient_errors: tuple = (
        psycopg2.OperationalError,
        psycopg2.InterfaceError,
        psycopg2.extensions.TransactionRollbackError  # Handles deadlocks
    )
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying database operations that might fail due to transient errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries in seconds (will use exponential backoff)
        transient_errors: Tuple of exception types to retry on
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        import functools
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            retries = 0
            last_exception = None
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except transient_errors as e:
                    last_exception = e
                    retries += 1
                    connection_metrics["retries"] += 1
                    
                    logger.warning(
                        f"Retryable error in {func.__name__} (attempt {retries}/{max_retries}): {e}"
                    )
                    
                    if retries < max_retries:
                        # Exponential backoff
                        sleep_time = retry_delay * (2 ** (retries - 1))
                        logger.debug(f"Retrying in {sleep_time:.2f} seconds")
                        time.sleep(sleep_time)
            
            # If we get here, all retries failed
            connection_metrics["errors"] += 1
            logger.error(f"Operation {func.__name__} failed after {max_retries} retries")
            raise last_exception
            
        return wrapper
    return decorator 