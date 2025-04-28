"""
Order validation module for the execution system.
"""
import abc
import logging
from typing import Dict, Any, Optional, List, Tuple, Type

from .execution.core.base import Order, OrderStatus

# Configure logger
logger = logging.getLogger(__name__)

class ValidationResult:
    """Class representing the result of a validation check."""
    
    def __init__(self, is_valid: bool, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize a validation result.
        
        Args:
            is_valid: Whether the validation passed
            message: Optional message explaining the result
            details: Optional details about the validation
        """
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}
        
    def __bool__(self) -> bool:
        """Return whether the validation passed."""
        return self.is_valid

class BaseValidator(abc.ABC):
    """Abstract base class for order validators."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize a validator.
        
        Args:
            name: Validator name
            config: Optional configuration
        """
        self.name = name
        self.config = config or {}
        logger.info(f"Initialized validator: {name}")
    
    @abc.abstractmethod
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate an order.
        
        Args:
            order: Order to validate
            context: Optional context information
            
        Returns:
            ValidationResult indicating whether the order is valid
        """
        pass
    
    def _create_result(self, is_valid: bool, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Create a validation result.
        
        Args:
            is_valid: Whether the validation passed
            message: Optional message explaining the result
            details: Optional details about the validation
            
        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid, message, details)
        
        if not is_valid:
            logger.warning(f"Validation failed: {self.name} - {message}")
        
        return result

class OrderValidator:
    """
    Composite validator that runs a chain of validation checks on an order.
    Uses the Chain of Responsibility pattern.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the order validator.
        
        Args:
            config: Optional configuration
        """
        self.validators: List[BaseValidator] = []
        self.config = config or {}
        logger.info("Initialized order validator")
    
    def add_validator(self, validator: BaseValidator) -> None:
        """
        Add a validator to the chain.
        
        Args:
            validator: Validator to add
        """
        self.validators.append(validator)
        logger.info(f"Added validator: {validator.name}")
    
    def validate(self, order: Order, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate an order using all registered validators.
        
        Args:
            order: Order to validate
            context: Optional context information
            
        Returns:
            Tuple of (is_valid, error_message, error_details)
        """
        context = context or {}
        
        logger.info(f"Validating order {order.client_order_id}")
        
        for validator in self.validators:
            result = validator.validate(order, context)
            
            if not result:
                order.update_status(OrderStatus.REJECTED)
                order.error = {
                    "validator": validator.name,
                    "message": result.message,
                    "details": result.details
                }
                
                return False, result.message, result.details
        
        # If all validations pass, update the order status
        order.update_status(OrderStatus.VALIDATED)
        
        return True, None, None 