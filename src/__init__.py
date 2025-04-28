"""
Forex Trading Bot - Top-level package for the application.

This file helps Python recognize the directory structure as a proper package,
allowing both direct imports and installation via pip.

Example:
    Import a module directly:
    >>> from src.utils import config

    Or after installation:
    >>> from forex_trading_bot.utils import config
"""

# Version information
__version__ = "0.1.0"
__author__ = "Forex Trading Team"

# Make key modules available at the package level
from . import utils
from . import core
from . import exchange
from . import risk
from . import agents 