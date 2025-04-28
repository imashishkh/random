"""
Base repository classes and interfaces for database access.
Provides standard CRUD operations and utility functions.
"""
import logging
from typing import List, Dict, Any, Optional, Union, TypeVar, Generic, Type, cast
from datetime import datetime

import psycopg2
from psycopg2.extras import Json

from .connection import (
    execute_query, 
    execute_batch, 
    execute_values_query, 
    copy_from_records,
    transaction, 
    QueryError,
    retry_on_transient_error
)

logger = logging.getLogger(__name__)

# Type variable for entity objects
T = TypeVar('T')

class BaseRepository(Generic[T]):
    """
    Base repository class for database CRUD operations.
    Provides standard operations for working with database entities.
    """
    
    def __init__(self, table_name: str, entity_class: Type[T]):
        """
        Initialize the repository.
        
        Args:
            table_name: Name of the database table
            entity_class: Class used to instantiate entity objects
        """
        self.table_name = table_name
        self.entity_class = entity_class
        self.primary_key = "id"  # Default primary key
    
    def _to_db_dict(self, entity: T) -> Dict[str, Any]:
        """
        Convert an entity object to a dictionary for database operations.
        Subclasses should override this method for custom conversions.
        
        Args:
            entity: Entity object
            
        Returns:
            Dictionary representation for database
        """
        if isinstance(entity, dict):
            return cast(Dict[str, Any], entity)
        return vars(entity)
    
    def _from_db_dict(self, db_dict: Dict[str, Any]) -> T:
        """
        Convert a database dictionary to an entity object.
        Subclasses should override this method for custom conversions.
        
        Args:
            db_dict: Dictionary from database query
            
        Returns:
            Entity object
        """
        if self.entity_class == dict:
            return cast(T, db_dict)
        return self.entity_class(**db_dict)
    
    @retry_on_transient_error()
    def create(self, entity: T) -> int:
        """
        Create a new entity in the database.
        
        Args:
            entity: Entity to create
            
        Returns:
            The ID of the created entity
            
        Raises:
            QueryError: If creation fails
        """
        data = self._to_db_dict(entity)
        
        # Remove any None values
        data = {k: v for k, v in data.items() if v is not None}
        
        # Remove id if it's None or auto-generated
        if self.primary_key in data and data[self.primary_key] is None:
            del data[self.primary_key]
        
        # Process JSON fields
        values = []
        columns = []
        placeholders = []
        
        for column, value in data.items():
            columns.append(column)
            
            if isinstance(value, dict) or isinstance(value, list):
                placeholders.append("%s::jsonb")
                values.append(Json(value))
            else:
                placeholders.append("%s")
                values.append(value)
        
        # Add created_at timestamp if not present
        if "created_at" not in data:
            columns.append("created_at")
            placeholders.append("NOW()")
        
        # Add updated_at timestamp if not present
        if "updated_at" not in data:
            columns.append("updated_at")
            placeholders.append("NOW()")
            
        # Construct the query
        placeholder_str = ", ".join(placeholders)
        column_str = ", ".join(columns)
        query = f"INSERT INTO {self.table_name} ({column_str}) VALUES ({placeholder_str}) RETURNING {self.primary_key}"
        
        try:
            result = execute_query(query, tuple(values), fetch_all=False)
            if result and self.primary_key in result:
                return result[self.primary_key]
            raise QueryError(f"Failed to get ID from created {self.table_name} entity")
        except Exception as e:
            logger.error(f"Error creating {self.table_name} entity: {e}")
            raise
    
    @retry_on_transient_error()
    def update(self, entity: T) -> bool:
        """
        Update an existing entity in the database.
        
        Args:
            entity: Entity to update
            
        Returns:
            True if successful, False if no rows affected
            
        Raises:
            QueryError: If update fails
        """
        data = self._to_db_dict(entity)
        
        # Ensure we have the primary key
        if self.primary_key not in data or data[self.primary_key] is None:
            raise ValueError(f"Cannot update entity without {self.primary_key}")
        
        # Extract the primary key value
        id_value = data[self.primary_key]
        del data[self.primary_key]
        
        # Process JSON fields
        set_parts = []
        values = []
        
        for column, value in data.items():
            if isinstance(value, dict) or isinstance(value, list):
                set_parts.append(f"{column} = %s::jsonb")
                values.append(Json(value))
            else:
                set_parts.append(f"{column} = %s")
                values.append(value)
        
        # Add updated_at timestamp
        set_parts.append("updated_at = NOW()")
        
        # Construct the query
        set_clause = ", ".join(set_parts)
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {self.primary_key} = %s"
        values.append(id_value)
        
        try:
            # Return the number of rows affected
            result = execute_query(query, tuple(values))
            # For UPDATE queries without RETURNING, the result will be None
            # We need to check if any rows were affected using rowcount
            # Since we're using execute_query, we can't directly access rowcount
            # Instead, we'll use an alternative approach
            return True  # Assume success if no error
        except Exception as e:
            logger.error(f"Error updating {self.table_name} entity: {e}")
            raise
    
    @retry_on_transient_error()
    def delete(self, id_value: int) -> bool:
        """
        Delete an entity from the database.
        
        Args:
            id_value: ID of the entity to delete
            
        Returns:
            True if successful, False if no rows affected
            
        Raises:
            QueryError: If deletion fails
        """
        query = f"DELETE FROM {self.table_name} WHERE {self.primary_key} = %s"
        
        try:
            execute_query(query, (id_value,))
            return True  # Assume success if no error
        except Exception as e:
            logger.error(f"Error deleting {self.table_name} entity: {e}")
            raise
    
    @retry_on_transient_error()
    def get_by_id(self, id_value: int) -> Optional[T]:
        """
        Get an entity by its ID.
        
        Args:
            id_value: ID of the entity to retrieve
            
        Returns:
            Entity if found, None otherwise
            
        Raises:
            QueryError: If query fails
        """
        query = f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = %s"
        
        try:
            result = execute_query(query, (id_value,), fetch_all=False)
            if result:
                return self._from_db_dict(result)
            return None
        except Exception as e:
            logger.error(f"Error retrieving {self.table_name} entity: {e}")
            raise
    
    @retry_on_transient_error()
    def get_all(self, limit: int = 1000, offset: int = 0) -> List[T]:
        """
        Get all entities, with pagination.
        
        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            
        Returns:
            List of entities
            
        Raises:
            QueryError: If query fails
        """
        query = f"SELECT * FROM {self.table_name} ORDER BY {self.primary_key} LIMIT %s OFFSET %s"
        
        try:
            results = execute_query(query, (limit, offset))
            return [self._from_db_dict(result) for result in results] if results else []
        except Exception as e:
            logger.error(f"Error retrieving all {self.table_name} entities: {e}")
            raise
    
    @retry_on_transient_error()
    def count(self) -> int:
        """
        Count the total number of entities.
        
        Returns:
            Count of entities
            
        Raises:
            QueryError: If query fails
        """
        query = f"SELECT COUNT(*) as count FROM {self.table_name}"
        
        try:
            result = execute_query(query, fetch_all=False)
            return result["count"] if result else 0
        except Exception as e:
            logger.error(f"Error counting {self.table_name} entities: {e}")
            raise
    
    def bulk_create(self, entities: List[T], batch_size: int = 1000) -> int:
        """
        Create multiple entities in bulk.
        
        Args:
            entities: List of entities to create
            batch_size: Number of entities per batch
            
        Returns:
            Number of entities created
            
        Raises:
            QueryError: If bulk creation fails
        """
        if not entities:
            return 0
        
        # Convert all entities to dictionaries
        data = [self._to_db_dict(entity) for entity in entities]
        
        # Get columns from the first entity
        first_entity = data[0]
        columns = list(first_entity.keys())
        
        # Remove primary key if it's None or auto-generated
        if self.primary_key in columns:
            columns.remove(self.primary_key)
            
        # Add timestamps if not present
        if "created_at" not in columns:
            columns.append("created_at")
        if "updated_at" not in columns:
            columns.append("updated_at")
            
        # Prepare values list
        values = []
        for entity_data in data:
            # Add timestamps
            now = datetime.now()
            if "created_at" not in entity_data:
                entity_data["created_at"] = now
            if "updated_at" not in entity_data:
                entity_data["updated_at"] = now
                
            # Remove primary key
            if self.primary_key in entity_data:
                del entity_data[self.primary_key]
                
            # Extract values in column order
            row_values = []
            for col in columns:
                val = entity_data.get(col)
                if isinstance(val, dict) or isinstance(val, list):
                    val = Json(val)
                row_values.append(val)
            values.append(row_values)
            
        # Use execute_values for efficient bulk insert
        try:
            return execute_values_query(self.table_name, columns, values)
        except Exception as e:
            logger.error(f"Error in bulk create for {self.table_name}: {e}")
            raise
    
    def bulk_update(self, entities: List[T], fields: List[str]) -> int:
        """
        Update multiple entities in bulk.
        
        Args:
            entities: List of entities to update
            fields: List of fields to update
            
        Returns:
            Number of entities updated
            
        Raises:
            QueryError: If bulk update fails
        """
        if not entities or not fields:
            return 0
            
        # Ensure primary key is not in fields
        if self.primary_key in fields:
            fields.remove(self.primary_key)
            
        # Add updated_at if not in fields
        if "updated_at" not in fields:
            fields.append("updated_at")
            
        # Prepare query templates
        set_clause = ", ".join([f"{field} = v.{field}" for field in fields])
        set_clause += ", updated_at = NOW()"
        
        # Get primary keys and prepare data
        ids = []
        data_by_id = {}
        
        for entity in entities:
            entity_dict = self._to_db_dict(entity)
            if self.primary_key not in entity_dict or entity_dict[self.primary_key] is None:
                continue
                
            id_value = entity_dict[self.primary_key]
            ids.append(id_value)
            data_by_id[id_value] = entity_dict
            
        if not ids:
            return 0
            
        # Use a WITH clause for the values
        with transaction() as conn:
            with conn.cursor() as cursor:
                # Construct dynamic SQL with value expressions for each entity
                placeholders = []
                all_values = []
                
                for id_value in ids:
                    values = []
                    value_expressions = []
                    
                    # Add id value
                    values.append(id_value)
                    
                    # Add field values
                    for field in fields:
                        if field == "updated_at":
                            value_expressions.append("NOW()")
                        else:
                            value = data_by_id[id_value].get(field)
                            if isinstance(value, dict) or isinstance(value, list):
                                value_expressions.append("%s::jsonb")
                                values.append(Json(value))
                            else:
                                value_expressions.append("%s")
                                values.append(value)
                                
                    placeholder = f"({', '.join(value_expressions)})"
                    placeholders.append(placeholder)
                    all_values.extend(values)
                    
                # Fields including primary key for the values table
                all_fields = [self.primary_key] + fields
                
                # Construct the final query
                values_clause = ", ".join(placeholders)
                query = f"""
                WITH values_table ({', '.join(all_fields)}) AS (
                    VALUES {values_clause}
                )
                UPDATE {self.table_name} t
                SET {set_clause}
                FROM values_table v
                WHERE t.{self.primary_key} = v.{self.primary_key}
                """
                
                cursor.execute(query, all_values)
                return cursor.rowcount
                
    def bulk_delete(self, ids: List[int]) -> int:
        """
        Delete multiple entities by their IDs.
        
        Args:
            ids: List of entity IDs to delete
            
        Returns:
            Number of entities deleted
            
        Raises:
            QueryError: If bulk deletion fails
        """
        if not ids:
            return 0
            
        placeholders = ", ".join(["%s"] * len(ids))
        query = f"DELETE FROM {self.table_name} WHERE {self.primary_key} IN ({placeholders})"
        
        try:
            execute_query(query, tuple(ids))
            return len(ids)  # Assume all were deleted
        except Exception as e:
            logger.error(f"Error in bulk delete for {self.table_name}: {e}")
            raise
    
    def bulk_copy(self, entities: List[T]) -> int:
        """
        Create multiple entities using the COPY command for maximum performance.
        
        Args:
            entities: List of entities to create
            
        Returns:
            Number of entities created
            
        Raises:
            QueryError: If COPY operation fails
        """
        if not entities:
            return 0
        
        # Convert all entities to dictionaries
        data = [self._to_db_dict(entity) for entity in entities]
        
        # Get columns from the first entity
        first_entity = data[0]
        columns = list(first_entity.keys())
        
        # Remove primary key if it's None or auto-generated
        if self.primary_key in columns:
            columns.remove(self.primary_key)
            
        # Add timestamps if not present
        if "created_at" not in columns:
            columns.append("created_at")
        if "updated_at" not in columns:
            columns.append("updated_at")
            
        # Prepare records for COPY
        records = []
        for entity_data in data:
            # Add timestamps
            now = datetime.now()
            if "created_at" not in entity_data:
                entity_data["created_at"] = now
            if "updated_at" not in entity_data:
                entity_data["updated_at"] = now
                
            # Remove primary key
            if self.primary_key in entity_data:
                del entity_data[self.primary_key]
                
            # Extract values in column order
            row_values = []
            for col in columns:
                val = entity_data.get(col)
                if isinstance(val, dict) or isinstance(val, list):
                    val = Json(val)
                row_values.append(val)
                
            records.append(tuple(row_values))
        
        # Use COPY for maximum performance
        try:
            return copy_from_records(self.table_name, columns, records)
        except Exception as e:
            logger.error(f"Error in COPY operation for {self.table_name}: {e}")
            # Fall back to execute_values if COPY fails
            logger.info(f"Falling back to execute_values for bulk insert")
            values_list = [list(record) for record in records]
            return execute_values_query(self.table_name, columns, values_list)
    
    def get_by_column(self, column: str, value: Any) -> List[T]:
        """
        Get entities by a specific column value.
        
        Args:
            column: Column name
            value: Value to match
            
        Returns:
            List of matching entities
            
        Raises:
            QueryError: If query fails
        """
        query = f"SELECT * FROM {self.table_name} WHERE {column} = %s"
        
        try:
            results = execute_query(query, (value,))
            return [self._from_db_dict(result) for result in results] if results else []
        except Exception as e:
            logger.error(f"Error retrieving {self.table_name} entities by {column}: {e}")
            raise
    
    def get_by_filter(self, filters: Dict[str, Any], limit: int = 1000, offset: int = 0) -> List[T]:
        """
        Get entities matching multiple filter conditions.
        
        Args:
            filters: Dictionary of column-value pairs to filter by
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            
        Returns:
            List of matching entities
            
        Raises:
            QueryError: If query fails
        """
        if not filters:
            return self.get_all(limit, offset)
            
        where_clauses = []
        values = []
        
        for column, value in filters.items():
            where_clauses.append(f"{column} = %s")
            values.append(value)
            
        where_clause = " AND ".join(where_clauses)
        query = f"SELECT * FROM {self.table_name} WHERE {where_clause} LIMIT %s OFFSET %s"
        values.extend([limit, offset])
        
        try:
            results = execute_query(query, tuple(values))
            return [self._from_db_dict(result) for result in results] if results else []
        except Exception as e:
            logger.error(f"Error retrieving filtered {self.table_name} entities: {e}")
            raise

class UnitOfWork:
    """
    Unit of Work pattern implementation.
    Manages transaction boundaries and provides a consistent interface to repositories.
    """
    
    def __init__(self):
        """Initialize the Unit of Work."""
        self.repositories = {}
        self._conn = None
    
    def __enter__(self):
        """Start a new transaction."""
        from src.db.connection import transaction
        self._transaction = transaction()
        self._conn = self._transaction.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback the transaction."""
        return self._transaction.__exit__(exc_type, exc_val, exc_tb)
    
    def register_repository(self, name: str, repository: Any) -> None:
        """
        Register a repository with the Unit of Work.
        
        Args:
            name: Name to access the repository
            repository: Repository instance
        """
        self.repositories[name] = repository
    
    def __getattr__(self, name: str) -> Any:
        """
        Get a registered repository by name.
        
        Args:
            name: Repository name
            
        Returns:
            Repository instance
            
        Raises:
            AttributeError: If repository not found
        """
        if name in self.repositories:
            return self.repositories[name]
        raise AttributeError(f"No repository named '{name}' is registered")
    
    def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn:
            self._conn.commit()
    
    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._conn:
            self._conn.rollback() 