"""
Pydantic schemas for analytics API.

This module defines the data structures for analytics API requests and responses.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union, Any
from datetime import datetime

class DateRangeParams(BaseModel):
    """
    Query parameters for date range filtering.
    
    Users can provide either explicit start/end dates or a timeframe option.
    """
    start_date: Optional[datetime] = Field(None, description="Start date for the analysis")
    end_date: Optional[datetime] = Field(None, description="End date for the analysis (defaults to current time if not provided)")
    timeframe: Optional[str] = Field(None, description="Predefined timeframe (day, week, month, quarter, year)")

class PerformanceMetric(BaseModel):
    """Base model for a performance metric with value and unit."""
    value: Union[float, int, str] = Field(..., description="Value of the metric")
    unit: Optional[str] = Field(None, description="Unit of measurement (%, $, etc.)")

class PerformanceMetricsResponse(BaseModel):
    """Performance metrics for trading activity."""
    
    total_trades: int = Field(..., description="Total number of trades in the period")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    win_rate: float = Field(..., description="Percentage of winning trades")
    profit_factor: float = Field(..., description="Ratio of gross profit to gross loss")
    average_profit: float = Field(..., description="Average profit per trade")
    average_loss: float = Field(..., description="Average loss per trade")
    risk_reward_ratio: float = Field(..., description="Risk-reward ratio")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio (if enough data available)")
    total_profit_loss: float = Field(..., description="Total profit/loss for the period")
    max_consecutive_wins: int = Field(..., description="Maximum consecutive winning trades")
    max_consecutive_losses: int = Field(..., description="Maximum consecutive losing trades")
    average_trade_duration: Optional[float] = Field(None, description="Average trade duration in minutes")
    
    # Cache metadata
    cached: bool = Field(False, description="Whether this data came from cache")
    cache_time: Optional[datetime] = Field(None, description="When this data was cached")

class PnLOverTimeResponse(BaseModel):
    """Profit and loss data for a specific time interval."""
    
    date: datetime = Field(..., description="Start of the time interval")
    profit_loss: float = Field(..., description="Profit/loss for this interval")
    cumulative_profit_loss: float = Field(..., description="Cumulative profit/loss up to this interval")
    trade_count: int = Field(..., description="Number of trades in this interval")
    win_rate: Optional[float] = Field(None, description="Win rate for this interval")
    
    # Optional fields depending on the analysis
    win_count: Optional[int] = Field(None, description="Number of winning trades in the interval")
    loss_count: Optional[int] = Field(None, description="Number of losing trades in the interval")

class DistributionItem(BaseModel):
    """
    Single item in a distribution analysis.
    
    Used for category-based analytics like symbol or trade direction distribution.
    """
    category: str = Field(..., description="Category name (e.g., symbol, direction)")
    count: int = Field(..., description="Number of trades in this category")
    percentage: float = Field(..., description="Percentage of total trades")
    profit_loss: float = Field(..., description="Total profit/loss for this category")
    win_rate: float = Field(..., description="Win rate for this category")
    
    # Optional additional metrics
    average_profit: Optional[float] = Field(None, description="Average profit per winning trade")
    average_loss: Optional[float] = Field(None, description="Average loss per losing trade")

class TradeDistributionResponse(BaseModel):
    """Trade distribution analysis across various categories."""
    
    by_symbol: List[DistributionItem] = Field(..., description="Distribution by trading symbol")
    by_direction: List[DistributionItem] = Field(..., description="Distribution by trade direction (buy/sell)")
    by_time_of_day: List[DistributionItem] = Field(..., description="Distribution by hour of day")
    by_day_of_week: List[DistributionItem] = Field(..., description="Distribution by day of week")
    total_trades: int = Field(..., description="Total number of trades analyzed")
    
    # Optional additional distributions
    by_trade_duration: Optional[List[DistributionItem]] = Field(None, description="Trade distribution by duration")
    by_strategy: Optional[List[DistributionItem]] = Field(None, description="Trade distribution by strategy if applicable")
    
    # Cache metadata
    cached: bool = Field(False, description="Whether this data came from cache")
    cache_time: Optional[datetime] = Field(None, description="When this data was cached")

class DrawdownPeriod(BaseModel):
    """Information about a significant drawdown period."""
    
    start_date: datetime = Field(..., description="Start date of drawdown period")
    end_date: Optional[datetime] = Field(None, description="End date of drawdown period (None if ongoing)")
    depth: float = Field(..., description="Maximum drawdown depth (percentage)")
    duration: int = Field(..., description="Duration in days")
    recovery: Optional[int] = Field(None, description="Recovery time in days (None if not recovered)")

class RiskAnalysisResponse(BaseModel):
    """Risk analysis metrics for trading activity."""
    
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    current_drawdown: float = Field(..., description="Current drawdown percentage (0 if at equity high)")
    value_at_risk: float = Field(..., description="Value at Risk (VaR)")
    confidence_level: float = Field(..., description="Confidence level used for VaR calculation")
    average_drawdown: float = Field(..., description="Average drawdown")
    drawdown_periods: List[DrawdownPeriod] = Field(..., description="Significant drawdown periods")
    risk_of_ruin: Optional[float] = Field(None, description="Estimated risk of ruin")
    daily_value_at_risk: Optional[float] = Field(None, description="Daily Value at Risk")
    expected_shortfall: Optional[float] = Field(None, description="Expected Shortfall (Conditional VaR)")
    
    # Cache metadata
    cached: bool = Field(False, description="Whether this data came from cache")
    cache_time: Optional[datetime] = Field(None, description="When this data was cached") 