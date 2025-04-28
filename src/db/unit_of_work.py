"""
Unit of Work pattern implementation for managing database transactions.
This ensures that multiple operations across different repositories
are executed within a single transaction.
"""
from typing import Optional, Dict, Any, TypeVar, Type, Set
import logging
from abc import ABC, abstractmethod

from .connection import ConnectionContext, TransactionContext
from .exceptions import TransactionError

logger = logging.getLogger(__name__)

class UnitOfWork(ABC):
    """
    Abstract Unit of Work interface that defines the contract
    for concrete Unit of Work implementations.
    """
    
    @abstractmethod
    def __enter__(self):
        """Begin a transaction."""
        pass
        
    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the transaction by committing or rolling back."""
        pass
        
    @abstractmethod
    def commit(self):
        """Commit the current transaction."""
        pass
        
    @abstractmethod
    def rollback(self):
        """Roll back the current transaction."""
        pass


class DatabaseUnitOfWork(UnitOfWork):
    """
    Implements the Unit of Work pattern to manage database transactions.
    
    This class coordinates work across multiple repositories ensuring that
    all operations are executed within a single transaction that can be
    committed or rolled back as a unit.
    """
    
    def __init__(self, repositories: Optional[Dict[str, Any]] = None):
        """
        Initialize the unit of work.
        
        Args:
            repositories: Optional dictionary of repositories to register
        """
        self._connection = None
        self._repositories = {}
        self._is_transaction_active = False
        
        # Register repositories if provided
        if repositories:
            for name, repo in repositories.items():
                self.register_repository(name, repo)
        
    def __enter__(self):
        """Begin a transaction by acquiring a database connection."""
        try:
            # Start transaction context
            self._transaction_context = TransactionContext()
            self._connection = self._transaction_context.__enter__()
            self._is_transaction_active = True
            
            # Make the connection available to all repositories
            self._set_repository_connections()
            
            logger.debug("Transaction started")
            return self
            
        except Exception as e:
            logger.error(f"Failed to start transaction: {str(e)}")
            if self._connection is not None:
                self.__exit__(Exception, e, None)
            raise TransactionError(f"Failed to start transaction: {str(e)}")
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the transaction by committing or rolling back."""
        if not self._is_transaction_active:
            return
            
        try:
            # Allow the transaction context to handle commit/rollback
            result = self._transaction_context.__exit__(exc_type, exc_val, exc_tb)
            self._is_transaction_active = False
            self._connection = None
            
            if exc_type is not None:
                logger.error(f"Transaction rolled back due to error: {exc_val}")
            else:
                logger.debug("Transaction committed successfully")
                
            return result
            
        except Exception as e:
            logger.error(f"Error ending transaction: {str(e)}")
            self._is_transaction_active = False
            self._connection = None
            raise TransactionError(f"Error ending transaction: {str(e)}")
                
    def commit(self):
        """
        Commit the current transaction.
        
        Raises:
            TransactionError: If there is no active transaction
        """
        if not self._is_transaction_active or self._connection is None:
            raise TransactionError("No active transaction to commit")
            
        try:
            self._connection.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            logger.error(f"Error committing transaction: {str(e)}")
            raise TransactionError(f"Error committing transaction: {str(e)}")
            
    def rollback(self):
        """
        Roll back the current transaction.
        
        Raises:
            TransactionError: If there is no active transaction
        """
        if not self._is_transaction_active or self._connection is None:
            raise TransactionError("No active transaction to roll back")
            
        try:
            self._connection.rollback()
            logger.debug("Transaction rolled back")
        except Exception as e:
            logger.error(f"Error rolling back transaction: {str(e)}")
            raise TransactionError(f"Error rolling back transaction: {str(e)}")
    
    def register_repository(self, name: str, repository: Any) -> None:
        """
        Register a repository with this unit of work.
        
        Args:
            name: Name to access the repository by
            repository: Repository instance
        """
        if name in self._repositories:
            logger.warning(f"Repository '{name}' already registered, overwriting")
            
        self._repositories[name] = repository
        
        # If we're in an active transaction, set the connection
        if self._is_transaction_active and self._connection is not None:
            self._set_repository_connection(repository)
            
    def _set_repository_connections(self) -> None:
        """Set the current connection on all registered repositories."""
        if not self._connection:
            return
            
        for repo in self._repositories.values():
            self._set_repository_connection(repo)
            
    def _set_repository_connection(self, repository: Any) -> None:
        """
        Set the current connection on a repository.
        
        Args:
            repository: Repository instance
        """
        # Check if repository has a _set_connection method
        if hasattr(repository, '_set_connection') and callable(getattr(repository, '_set_connection')):
            repository._set_connection(self._connection)
            
    def __getattr__(self, name: str) -> Any:
        """
        Allow direct access to repositories as attributes.
        
        Args:
            name: Name of the repository to access
            
        Returns:
            The repository
            
        Raises:
            AttributeError: If the repository is not registered
        """
        if name in self._repositories:
            return self._repositories[name]
            
        raise AttributeError(f"Repository '{name}' not registered with this unit of work")


class TradeAnalyticsUnitOfWork(DatabaseUnitOfWork):
    """
    Specific Unit of Work implementation for the trade analytics module.
    
    Automatically registers all the trade analytics repositories.
    """
    
    def __init__(self):
        """Initialize with trade analytics repositories."""
        from src.db.repositories import (
            SymbolRepository, TradeRepository, TradeMetricRepository,
            TradingSessionRepository, TradeTagRepository, PriceDataRepository,
            TradingStrategyRepository
        )
        
        # Create repositories
        repositories = {
            'symbols': SymbolRepository(),
            'trades': TradeRepository(),
            'trade_metrics': TradeMetricRepository(),
            'trading_sessions': TradingSessionRepository(),
            'trade_tags': TradeTagRepository(),
            'price_data': PriceDataRepository(),
            'trading_strategies': TradingStrategyRepository()
        }
        
        super().__init__(repositories) 