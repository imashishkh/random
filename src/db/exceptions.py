"""
Database-related exceptions.

This module defines custom exceptions for database operations.
"""

class DatabaseError(Exception):
    """Base exception for all database-related errors."""
    
    def __init__(self, message: str = "A database error occurred"):
        self.message = message
        super().__init__(self.message)


class ConnectionError(DatabaseError):
    """Exception raised for database connection errors."""
    
    def __init__(self, message: str = "Database connection error"):
        super().__init__(message)


class TransactionError(DatabaseError):
    """Exception raised for database transaction errors."""
    
    def __init__(self, message: str = "Database transaction error"):
        super().__init__(message)


class QueryError(DatabaseError):
    """Exception raised for database query errors."""
    
    def __init__(self, message: str = "Database query error"):
        super().__init__(message)


class EntityNotFoundError(DatabaseError):
    """Exception raised when an entity is not found."""
    
    def __init__(self, entity_type: str = "Entity", entity_id: str = None):
        message = f"{entity_type} not found"
        if entity_id:
            message += f" with ID: {entity_id}"
        super().__init__(message)


class EntityValidationError(DatabaseError):
    """Exception raised when entity validation fails."""
    
    def __init__(self, message: str = "Entity validation error"):
        super().__init__(message)


class DuplicateEntityError(DatabaseError):
    """Exception raised when attempting to create a duplicate entity."""
    
    def __init__(self, entity_type: str = "Entity", field: str = None, value: str = None):
        message = f"Duplicate {entity_type}"
        if field and value:
            message += f" with {field}: {value}"
        super().__init__(message)


class RepositoryError(DatabaseError):
    """Exception raised for repository-specific errors."""
    
    def __init__(self, message: str = "Repository operation error"):
        super().__init__(message)


class MappingError(DatabaseError):
    """Exception raised when entity mapping fails."""
    
    def __init__(self, message: str = "Entity mapping error"):
        super().__init__(message) 