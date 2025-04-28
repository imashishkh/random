"""
Utility functions for the Forex Trading dashboard.
"""
from datetime import datetime, timedelta
from decimal import Decimal
import random
from typing import Dict, List, Optional, Any, Tuple

# Format currency with the appropriate symbol and precision
def format_currency(amount: Decimal, currency: str = "USD", precision: int = 2) -> str:
    """Format a decimal amount as a currency string."""
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "BTC": "₿",
        "ETH": "Ξ"
    }
    
    symbol = symbols.get(currency, currency)
    
    # Special handling for crypto (show more decimal places)
    if currency in ["BTC", "ETH"]:
        precision = 8
    elif currency == "JPY":
        precision = 0  # JPY typically doesn't use decimal places
    
    formatted = f"{amount:.{precision}f}"
    
    # Add thousands separators
    parts = formatted.split(".")
    parts[0] = "{:,}".format(int(parts[0]))
    formatted = ".".join(parts)
    
    return f"{symbol}{formatted}"

# Format percentage with + or - sign
def format_percentage(value: float, include_sign: bool = True) -> str:
    """Format a decimal value as a percentage string with sign."""
    if include_sign and value > 0:
        return f"+{value:.2f}%"
    else:
        return f"{value:.2f}%"

# Format time based on how recent it is
def format_time(timestamp: datetime) -> str:
    """Format a timestamp based on how recent it is."""
    now = datetime.now()
    delta = now - timestamp
    
    if delta.days > 0:
        if delta.days == 1:
            return "Yesterday"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        else:
            return timestamp.strftime("%b %d, %Y")
    
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    
    return "Just now"

# Format bytes to human-readable format
def format_bytes(bytes_value: int) -> str:
    """Format bytes value to human-readable size (B, KB, MB, GB, etc.)."""
    if bytes_value < 0:
        return "0 B"
    
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    suffix_index = 0
    value = float(bytes_value)
    
    while value >= 1024 and suffix_index < len(suffixes) - 1:
        value /= 1024
        suffix_index += 1
    
    if suffix_index == 0:
        return f"{int(value)} {suffixes[suffix_index]}"
    else:
        return f"{value:.2f} {suffixes[suffix_index]}"

# Format time delta to human-readable format
def format_time_delta(delta: timedelta) -> str:
    """Format a timedelta to human-readable format."""
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        if days == 1:
            return f"{days} day, {hours}h"
        else:
            return f"{days} days, {hours}h"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

# Generate mock trade data for the dashboard
def generate_mock_trades(num_trades: int = 5) -> List[Dict[str, Any]]:
    """Generate random trade data for demonstration purposes."""
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"]
    sides = ["BUY", "SELL"]
    statuses = ["FILLED", "FILLED", "FILLED", "PENDING", "CANCELLED"]
    
    trades = []
    
    for i in range(num_trades):
        pair = random.choice(pairs)
        side = random.choice(sides)
        size = round(random.uniform(0.1, 10.0), 2)
        price = round(random.uniform(0.8, 1.5), 5)
        if "JPY" in pair:
            price = round(random.uniform(100, 150), 2)
        
        # Calculate 10 to 30 minutes ago for the timestamp
        minutes_ago = random.randint(1, 30)
        timestamp = datetime.now().replace(microsecond=0)
        timestamp = timestamp.replace(minute=timestamp.minute - minutes_ago)
        
        profit_loss = round(random.uniform(-100, 100), 2)
        
        trades.append({
            "id": f"T{random.randint(10000, 99999)}",
            "pair": pair,
            "side": side,
            "size": size,
            "price": price,
            "status": random.choice(statuses),
            "timestamp": timestamp,
            "profit_loss": profit_loss
        })
    
    # Sort by timestamp, most recent first
    return sorted(trades, key=lambda x: x["timestamp"], reverse=True)

# Generate mock wallet data
def generate_mock_wallet() -> Dict[str, Any]:
    """Generate mock wallet data for demonstration."""
    return {
        "balance": Decimal(str(round(random.uniform(5000, 15000), 2))),
        "equity": Decimal(str(round(random.uniform(5000, 15000), 2))),
        "margin": Decimal(str(round(random.uniform(1000, 3000), 2))),
        "free_margin": Decimal(str(round(random.uniform(2000, 8000), 2))),
        "margin_level": round(random.uniform(200, 500), 2),
        "currency": "USD"
    }

# Generate mock performance metrics
def generate_mock_performance() -> Dict[str, Any]:
    """Generate mock performance data for demonstration."""
    daily_change = round(random.uniform(-2.5, 2.5), 2)
    weekly_change = round(random.uniform(-5.0, 8.0), 2)
    monthly_change = round(random.uniform(-10.0, 15.0), 2)
    
    return {
        "daily_change": format_percentage(daily_change),
        "weekly_change": format_percentage(weekly_change),
        "monthly_change": format_percentage(monthly_change),
        "total_trades": random.randint(100, 500),
        "win_rate": f"{round(random.uniform(40, 70), 1)}%",
        "profit_factor": round(random.uniform(1.1, 2.2), 2),
        "average_win": round(random.uniform(20, 50), 2),
        "average_loss": round(random.uniform(10, 30), 2),
        "largest_win": round(random.uniform(100, 300), 2),
        "largest_loss": round(random.uniform(50, 150), 2),
        "sharpe_ratio": round(random.uniform(0.8, 2.5), 2)
    }

# Generate mock agent status data
def generate_mock_agent_status() -> List[Dict[str, str]]:
    """Generate mock trading agent status data."""
    agents = [
        {"name": "TrendFollower", "status": random.choice(["active", "stopped", "error"])},
        {"name": "MeanReversion", "status": random.choice(["active", "stopped"])},
        {"name": "BreakoutTrader", "status": random.choice(["active", "warning"])},
        {"name": "GridTrader", "status": random.choice(["active", "stopped"])},
        {"name": "NewsMomentum", "status": random.choice(["stopped", "warning"])},
    ]
    
    return agents

# Generate mock forex price data
def generate_mock_forex_prices() -> Dict[str, Dict[str, Any]]:
    """Generate mock forex price data for the ticker."""
    pairs = {
        "EUR/USD": {"base": 1.08},
        "GBP/USD": {"base": 1.27},
        "USD/JPY": {"base": 145.0},
        "AUD/USD": {"base": 0.65},
        "USD/CAD": {"base": 1.35},
        "USD/CHF": {"base": 0.91},
        "NZD/USD": {"base": 0.60}
    }
    
    result = {}
    
    for pair, data in pairs.items():
        base = data["base"]
        # Random price fluctuation within 0.5%
        change_pct = random.uniform(-0.5, 0.5)
        
        # Calculate the actual price with fluctuation
        if "JPY" in pair:
            price = round(base * (1 + change_pct/100), 2)
            price_str = f"{price:.2f}"
        else:
            price = round(base * (1 + change_pct/100), 5)
            price_str = f"{price:.5f}"
        
        # Daily change (separate from current fluctuation)
        daily_change = random.uniform(-1.0, 1.0)
        
        result[pair] = {
            "price": price_str,
            "change": format_percentage(daily_change)
        }
    
    return result 