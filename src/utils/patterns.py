"""
Design Patterns

This module provides implementations of common design patterns
for use throughout the application.
"""

import threading
from typing import Dict, Any, Type


class Singleton(type):
    """
    Metaclass for implementing the Singleton pattern.
    
    This ensures that only one instance of a class is created and provides
    a global point of access to it.
    
    Example:
        class MyClass(metaclass=Singleton):
            pass
    """
    _instances: Dict[Type, Any] = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ThreadSafeSingleton(type):
    """
    Thread-safe implementation of the Singleton metaclass.
    
    This version ensures that only one instance of a class is created even in
    a multi-threaded environment.
    
    Example:
        class MyThreadSafeClass(metaclass=ThreadSafeSingleton):
            pass
    """
    _instances: Dict[Type, Any] = {}
    _lock = threading.RLock()
    
    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super(ThreadSafeSingleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def singleton(cls):
    """
    Singleton decorator for classes.
    
    An alternative to using metaclasses. This can be applied to any class
    to ensure only one instance is created.
    
    Example:
        @singleton
        class MyClass:
            pass
    """
    instances = {}
    
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance 