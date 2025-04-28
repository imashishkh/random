"""
Base repository for database operations.

This module provides a base repository with common database operations that can be
extended for specific entity types.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

import psycopg2
from psycopg2 import sql

from .connection import get_connection, ConnectionContext, TransactionContext
from .exceptions import EntityNotFoundError, QueryError, RepositoryError

# Type variable representing an entity model
T = TypeVar('T')

logger = logging.getLogger(__name__)


class BaseRepository(Generic[T], ABC):
    """
    Base class for all repositories providing common database operations.
    
    This abstract class should be extended for each entity type, providing
    type-safe operations and consistent error handling.
    """
    
    def __init__(self, table_name: str, entity_class: Type[T]):
        """
        Initialize the repository with the table name and entity class.
        
        Args:
            table_name: The name of the database table
            entity_class: The entity class to use for object mapping
        """
        self.table_name = table_name
        self.entity_class = entity_class
    
    @abstractmethod
    def map_to_entity(self, row: Dict[str, Any]) -> T:
        """
        Map a database row to an entity object.
        
        Args:
            row: Database row as a dictionary
            
        Returns:
            An instance of the entity class
        """
        pass
    
    @abstractmethod
    def map_to_db_dict(self, entity: T) -> Dict[str, Any]:
        """
        Map an entity object to a dictionary for database operations.
        
        Args:
            entity: The entity to map
            
        Returns:
            A dictionary with keys corresponding to database columns
        """
        pass
    
    def get_by_id(self, entity_id: Union[int, str], id_column: str = "id") -> T:
        """
        Retrieve an entity by its ID.
        
        Args:
            entity_id: The ID of the entity to retrieve
            id_column: The name of the ID column (default: "id")
            
        Returns:
            The entity if found
            
        Raises:
            EntityNotFoundError: If the entity with the given ID is not found
        """
        try:
            with ConnectionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = sql.SQL("SELECT * FROM {} WHERE {} = %s").format(
                        sql.Identifier(self.table_name),
                        sql.Identifier(id_column)
                    )
                    cursor.execute(query, (entity_id,))
                    row = cursor.fetchone()
                    
                    if row is None:
                        raise EntityNotFoundError(
                            entity_type=self.entity_class.__name__,
                            entity_id=str(entity_id)
                        )
                    
                    return self.map_to_entity(dict(row))
        except psycopg2.Error as e:
            logger.error(f"Database error in get_by_id: {e}")
            raise QueryError(f"Error retrieving {self.entity_class.__name__}: {e}")
    
    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[T]:
        """
        Retrieve all entities with optional pagination.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of entities
        """
        try:
            with ConnectionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query_parts = [
                        sql.SQL("SELECT * FROM {}").format(sql.Identifier(self.table_name))
                    ]
                    
                    params = []
                    
                    if limit is not None:
                        query_parts.append(sql.SQL("LIMIT %s"))
                        params.append(limit)
                    
                    if offset is not None:
                        query_parts.append(sql.SQL("OFFSET %s"))
                        params.append(offset)
                    
                    query = sql.SQL(" ").join(query_parts)
                    cursor.execute(query, params)
                    
                    return [self.map_to_entity(dict(row)) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Database error in get_all: {e}")
            raise QueryError(f"Error retrieving all {self.entity_class.__name__}s: {e}")
    
    def create(self, entity: T) -> T:
        """
        Create a new entity in the database.
        
        Args:
            entity: The entity to create
            
        Returns:
            The created entity with any database-generated values (like ID)
        """
        db_dict = self.map_to_db_dict(entity)
        
        # Remove None values
        db_dict = {k: v for k, v in db_dict.items() if v is not None}
        
        if not db_dict:
            raise RepositoryError("Cannot create entity with empty data")
        
        columns = list(db_dict.keys())
        values = list(db_dict.values())
        
        try:
            with TransactionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # Build the query
                    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                        sql.Identifier(self.table_name),
                        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                        sql.SQL(", ").join(sql.Placeholder() for _ in values)
                    )
                    
                    cursor.execute(query, values)
                    result = cursor.fetchone()
                    
                    if result is None:
                        raise RepositoryError(f"Failed to create {self.entity_class.__name__}")
                    
                    return self.map_to_entity(dict(result))
        except psycopg2.Error as e:
            logger.error(f"Database error in create: {e}")
            raise QueryError(f"Error creating {self.entity_class.__name__}: {e}")
    
    def update(self, entity: T, id_column: str = "id") -> T:
        """
        Update an existing entity in the database.
        
        Args:
            entity: The entity to update
            id_column: The name of the ID column (default: "id")
            
        Returns:
            The updated entity
        """
        db_dict = self.map_to_db_dict(entity)
        
        # Ensure we have an ID
        if id_column not in db_dict or db_dict[id_column] is None:
            raise RepositoryError(f"Cannot update {self.entity_class.__name__} without ID")
        
        entity_id = db_dict.pop(id_column)
        
        # Remove None values
        db_dict = {k: v for k, v in db_dict.items() if v is not None}
        
        if not db_dict:
            raise RepositoryError("Cannot update entity with empty data")
        
        try:
            with TransactionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # Build the update query
                    query = sql.SQL("UPDATE {} SET {} WHERE {} = %s RETURNING *").format(
                        sql.Identifier(self.table_name),
                        sql.SQL(", ").join(
                            sql.SQL("{} = %s").format(sql.Identifier(column))
                            for column in db_dict.keys()
                        ),
                        sql.Identifier(id_column)
                    )
                    
                    # Execute the query with all values plus the ID
                    cursor.execute(query, list(db_dict.values()) + [entity_id])
                    result = cursor.fetchone()
                    
                    if result is None:
                        raise EntityNotFoundError(
                            entity_type=self.entity_class.__name__,
                            entity_id=str(entity_id)
                        )
                    
                    return self.map_to_entity(dict(result))
        except psycopg2.Error as e:
            logger.error(f"Database error in update: {e}")
            raise QueryError(f"Error updating {self.entity_class.__name__}: {e}")
    
    def delete(self, entity_id: Union[int, str], id_column: str = "id") -> bool:
        """
        Delete an entity from the database.
        
        Args:
            entity_id: The ID of the entity to delete
            id_column: The name of the ID column (default: "id")
            
        Returns:
            True if the entity was deleted, False otherwise
        """
        try:
            with TransactionContext() as conn:
                with conn.cursor() as cursor:
                    query = sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                        sql.Identifier(self.table_name),
                        sql.Identifier(id_column)
                    )
                    
                    cursor.execute(query, (entity_id,))
                    
                    if cursor.rowcount == 0:
                        raise EntityNotFoundError(
                            entity_type=self.entity_class.__name__,
                            entity_id=str(entity_id)
                        )
                    
                    return True
        except psycopg2.Error as e:
            logger.error(f"Database error in delete: {e}")
            raise QueryError(f"Error deleting {self.entity_class.__name__}: {e}")
    
    def count(self, where_clause: Optional[str] = None, params: Optional[List[Any]] = None) -> int:
        """
        Count entities in the database, optionally with a WHERE clause.
        
        Args:
            where_clause: Optional WHERE clause (without the 'WHERE' keyword)
            params: Parameters for the WHERE clause
            
        Returns:
            The count of entities
        """
        try:
            with ConnectionContext() as conn:
                with conn.cursor() as cursor:
                    if where_clause:
                        query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(
                            sql.Identifier(self.table_name),
                            sql.SQL(where_clause)
                        )
                        cursor.execute(query, params or [])
                    else:
                        query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                            sql.Identifier(self.table_name)
                        )
                        cursor.execute(query)
                    
                    result = cursor.fetchone()
                    return result[0] if result else 0
        except psycopg2.Error as e:
            logger.error(f"Database error in count: {e}")
            raise QueryError(f"Error counting {self.entity_class.__name__}s: {e}")
    
    def exists(self, entity_id: Union[int, str], id_column: str = "id") -> bool:
        """
        Check if an entity exists.
        
        Args:
            entity_id: The ID of the entity to check
            id_column: The name of the ID column (default: "id")
            
        Returns:
            True if the entity exists, False otherwise
        """
        try:
            with ConnectionContext() as conn:
                with conn.cursor() as cursor:
                    query = sql.SQL("SELECT EXISTS(SELECT 1 FROM {} WHERE {} = %s)").format(
                        sql.Identifier(self.table_name),
                        sql.Identifier(id_column)
                    )
                    
                    cursor.execute(query, (entity_id,))
                    result = cursor.fetchone()
                    
                    return result[0] if result else False
        except psycopg2.Error as e:
            logger.error(f"Database error in exists: {e}")
            raise QueryError(f"Error checking if {self.entity_class.__name__} exists: {e}")
    
    def bulk_create(self, entities: List[T]) -> List[T]:
        """
        Create multiple entities in a single transaction.
        
        Args:
            entities: List of entities to create
            
        Returns:
            List of created entities with database-generated values
        """
        if not entities:
            return []
        
        try:
            created_entities = []
            
            with TransactionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    for entity in entities:
                        db_dict = self.map_to_db_dict(entity)
                        
                        # Remove None values
                        db_dict = {k: v for k, v in db_dict.items() if v is not None}
                        
                        if not db_dict:
                            continue
                        
                        columns = list(db_dict.keys())
                        values = list(db_dict.values())
                        
                        # Build the query
                        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                            sql.Identifier(self.table_name),
                            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                            sql.SQL(", ").join(sql.Placeholder() for _ in values)
                        )
                        
                        cursor.execute(query, values)
                        result = cursor.fetchone()
                        
                        if result:
                            created_entities.append(self.map_to_entity(dict(result)))
            
            return created_entities
        except psycopg2.Error as e:
            logger.error(f"Database error in bulk_create: {e}")
            raise QueryError(f"Error bulk creating {self.entity_class.__name__}s: {e}")
    
    def execute_query(self, query: sql.Composed, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a custom SQL query.
        
        Args:
            query: The SQL query to execute
            params: Parameters for the query
            
        Returns:
            List of dictionaries representing the query results
        """
        try:
            with ConnectionContext() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(query, params or [])
                    
                    if cursor.description:
                        return [dict(row) for row in cursor.fetchall()]
                    return []
        except psycopg2.Error as e:
            logger.error(f"Database error in execute_query: {e}")
            raise QueryError(f"Error executing custom query: {e}") 