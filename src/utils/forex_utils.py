"""
Forex utility functions.

This module provides utility functions for working with forex data,
including currency pair extraction and validation.
"""

import re
from typing import List, Set


# Common forex currency pairs
MAJOR_PAIRS = {
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD", "NZD/USD"
}

MINOR_PAIRS = {
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD", "GBP/NZD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD", "AUD/NZD",
    "NZD/JPY", "NZD/CHF", "NZD/CAD",
    "CAD/JPY", "CAD/CHF",
    "CHF/JPY"
}

EXOTIC_PAIRS = {
    "USD/SGD", "USD/HKD", "USD/TRY", "USD/SEK", "USD/NOK", "USD/DKK", "USD/ZAR",
    "EUR/TRY", "EUR/SEK", "EUR/NOK", "EUR/DKK", "EUR/ZAR",
    "GBP/TRY", "GBP/SEK", "GBP/NOK", "GBP/DKK", "GBP/ZAR"
}

# All forex pairs combined
ALL_FOREX_PAIRS = MAJOR_PAIRS.union(MINOR_PAIRS).union(EXOTIC_PAIRS)

# Dictionary of currency symbols
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CHF": "Fr",
    "CAD": "C$",
    "AUD": "A$",
    "NZD": "NZ$"
}

# Regex patterns for matching forex pairs
# Standard forex notation (EUR/USD)
STANDARD_PAIR_PATTERN = r'\b([A-Z]{3})/([A-Z]{3})\b'

# No separator notation (EURUSD)
NO_SEPARATOR_PATTERN = r'\b([A-Z]{3})([A-Z]{3})\b'

# Alternative separator (_,-, etc.) (EUR_USD, EUR-USD)
ALT_SEPARATOR_PATTERN = r'\b([A-Z]{3})[-_]([A-Z]{3})\b'


def extract_forex_pairs(text: str) -> Set[str]:
    """
    Extract forex currency pairs from text.
    
    Args:
        text: Text to extract pairs from
        
    Returns:
        Set of extracted forex pairs in standard notation (e.g., 'EUR/USD')
    """
    if not text:
        return set()
    
    found_pairs = set()
    
    # Find standard notation pairs (EUR/USD)
    standard_matches = re.finditer(STANDARD_PAIR_PATTERN, text, re.IGNORECASE)
    for match in standard_matches:
        base, quote = match.groups()
        pair = f"{base.upper()}/{quote.upper()}"
        if pair in ALL_FOREX_PAIRS or f"{quote.upper()}/{base.upper()}" in ALL_FOREX_PAIRS:
            found_pairs.add(pair)
    
    # Find no separator pairs (EURUSD)
    no_sep_matches = re.finditer(NO_SEPARATOR_PATTERN, text, re.IGNORECASE)
    for match in no_sep_matches:
        base, quote = match.groups()
        pair = f"{base.upper()}/{quote.upper()}"
        if pair in ALL_FOREX_PAIRS:
            found_pairs.add(pair)
    
    # Find alternative separator pairs (EUR-USD, EUR_USD)
    alt_sep_matches = re.finditer(ALT_SEPARATOR_PATTERN, text, re.IGNORECASE)
    for match in alt_sep_matches:
        base, quote = match.groups()
        pair = f"{base.upper()}/{quote.upper()}"
        if pair in ALL_FOREX_PAIRS:
            found_pairs.add(pair)
    
    return found_pairs


def is_valid_forex_pair(pair: str) -> bool:
    """
    Check if a string is a valid forex pair.
    
    Args:
        pair: String to check
        
    Returns:
        True if valid forex pair, False otherwise
    """
    # Normalize to standard format
    normalized = pair.upper().replace("-", "/").replace("_", "/")
    
    # If no separator, try to split into base and quote
    if "/" not in normalized and len(normalized) == 6:
        normalized = f"{normalized[:3]}/{normalized[3:]}"
    
    return normalized in ALL_FOREX_PAIRS


def get_forex_pair_components(pair: str) -> List[str]:
    """
    Split a forex pair into its component currencies.
    
    Args:
        pair: Forex pair to split
        
    Returns:
        List of component currencies [base, quote]
    """
    # Normalize to standard format
    normalized = pair.upper().replace("-", "/").replace("_", "/")
    
    # If no separator, split into base and quote
    if "/" not in normalized and len(normalized) == 6:
        return [normalized[:3], normalized[3:]]
    
    # Otherwise, split on separator
    return normalized.split("/") 