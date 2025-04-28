"""
Data models for the analytics module.

This module defines the Pydantic models used by the analytics API for request/response
data validation and documentation.
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator


class TimeFrame(str, Enum):
    """Time frames for analytics queries and reports."""
    DAY = "day"
    WEEK = "week" 
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


class ReportType(str, Enum):
    """Types of reports that can be generated."""
    PERFORMANCE = "performance"
    TRADE_HISTORY = "trade_history"
    PNL = "pnl"
    RISK_ANALYSIS = "risk_analysis"
    PORTFOLIO = "portfolio"
    AGENTS = "agents"
    COMPREHENSIVE = "comprehensive"


class ReportFormat(str, Enum):
    """Output formats for reports and exports."""
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class Side(str, Enum):
    """Trade side enum."""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    """Trade status enum."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class TradeResponse(BaseModel):
    """Trade data model for API responses."""
    id: str = Field(..., description="Trade ID")
    symbol: str = Field(..., description="Trading symbol (e.g., 'EURUSD')")
    side: Side = Field(..., description="Trade side (BUY/SELL)")
    quantity: float = Field(..., description="Trade quantity")
    entry_price: float = Field(..., description="Entry price")
    exit_price: Optional[float] = Field(None, description="Exit price (if closed)")
    status: TradeStatus = Field(..., description="Trade status")
    pnl: Optional[float] = Field(None, description="Realized profit/loss (if closed)")
    pnl_percentage: Optional[float] = Field(None, description="P&L as percentage")
    commission: float = Field(0.0, description="Commission paid")
    open_time: datetime = Field(..., description="Open timestamp")
    close_time: Optional[datetime] = Field(None, description="Close timestamp (if closed)")
    duration: Optional[float] = Field(None, description="Trade duration in seconds (if closed)")
    agent_id: Optional[str] = Field(None, description="ID of the agent that placed the trade")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    position_id: Optional[str] = Field(None, description="Position ID this trade belongs to")
    exchange: str = Field(..., description="Exchange where the trade was executed")
    tags: List[str] = Field(default_factory=list, description="Custom tags for categorization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "id": "t-123456",
                "symbol": "EURUSD",
                "side": "BUY",
                "quantity": 1.0,
                "entry_price": 1.09423,
                "exit_price": 1.09526,
                "status": "CLOSED",
                "pnl": 103.0,
                "pnl_percentage": 0.94,
                "commission": 2.5,
                "open_time": "2023-06-01T12:34:56Z",
                "close_time": "2023-06-01T14:22:33Z",
                "duration": 6457,
                "agent_id": "agent-001",
                "stop_loss": 1.09323,
                "take_profit": 1.09623,
                "position_id": "p-789012",
                "exchange": "oanda",
                "tags": ["trend-following", "breakout"],
                "metadata": {"strategy": "mean_reversion", "confidence": 0.85}
            }
        }


class PositionStatus(str, Enum):
    """Position status enum."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class PositionResponse(BaseModel):
    """Position data model for API responses."""
    id: str = Field(..., description="Position ID")
    symbol: str = Field(..., description="Trading symbol")
    side: Side = Field(..., description="Position side (BUY/SELL)")
    size: float = Field(..., description="Position size")
    avg_entry_price: float = Field(..., description="Average entry price")
    avg_exit_price: Optional[float] = Field(None, description="Average exit price (if closed)")
    status: PositionStatus = Field(..., description="Position status")
    pnl: Optional[float] = Field(None, description="Realized profit/loss (if closed)")
    pnl_percentage: Optional[float] = Field(None, description="P&L as percentage")
    unrealized_pnl: Optional[float] = Field(None, description="Unrealized profit/loss (if open)")
    commission: float = Field(0.0, description="Total commission paid")
    open_time: datetime = Field(..., description="Open timestamp")
    close_time: Optional[datetime] = Field(None, description="Close timestamp (if closed)")
    duration: Optional[float] = Field(None, description="Position duration in seconds (if closed)")
    agent_id: Optional[str] = Field(None, description="ID of the agent that manages this position")
    current_price: Optional[float] = Field(None, description="Current market price (if open)")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    trades: List[str] = Field(default_factory=list, description="Trade IDs associated with this position")
    exchange: str = Field(..., description="Exchange where the position is held")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "id": "p-789012",
                "symbol": "EURUSD",
                "side": "BUY",
                "size": 2.0,
                "avg_entry_price": 1.09423,
                "avg_exit_price": 1.09526,
                "status": "CLOSED",
                "pnl": 206.0,
                "pnl_percentage": 0.94,
                "unrealized_pnl": None,
                "commission": 5.0,
                "open_time": "2023-06-01T12:34:56Z",
                "close_time": "2023-06-01T14:22:33Z",
                "duration": 6457,
                "agent_id": "agent-001",
                "current_price": None,
                "stop_loss": 1.09323,
                "take_profit": 1.09623,
                "trades": ["t-123456", "t-123457"],
                "exchange": "oanda",
                "metadata": {"strategy": "mean_reversion", "confidence": 0.85}
            }
        }


class TimeSeriesEntry(BaseModel):
    """Time series entry for profit/loss over time."""
    timestamp: datetime = Field(..., description="Timestamp for this data point")
    value: float = Field(..., description="Value at this timestamp")


class PnLData(BaseModel):
    """Profit and loss data model."""
    realized_pnl: float = Field(..., description="Realized profit/loss from closed positions")
    unrealized_pnl: Optional[float] = Field(None, description="Unrealized profit/loss from open positions")
    total_pnl: float = Field(..., description="Total profit/loss (realized + unrealized)")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    win_rate: float = Field(..., description="Win rate as a percentage")
    profit_factor: Optional[float] = Field(None, description="Profit factor (gross profit / gross loss)")
    avg_win: Optional[float] = Field(None, description="Average profit on winning trades")
    avg_loss: Optional[float] = Field(None, description="Average loss on losing trades")
    time_series: Optional[List[TimeSeriesEntry]] = Field(None, description="Time series of PnL data")


class PnLResponse(BaseModel):
    """Profit and loss response model."""
    data: PnLData = Field(..., description="Profit and loss metrics")
    start_date: datetime = Field(..., description="Start date of the period")
    end_date: datetime = Field(..., description="End date of the period")
    timeframe: TimeFrame = Field(..., description="Time frame used for the analysis")
    agent_id: Optional[str] = Field(None, description="Agent ID if filtered")
    symbol: Optional[str] = Field(None, description="Symbol if filtered")
    timestamp: datetime = Field(..., description="Timestamp when the data was generated")


class RiskMetrics(BaseModel):
    """Risk analysis metrics model."""
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    max_drawdown_amount: float = Field(..., description="Maximum drawdown amount in account currency")
    max_drawdown_duration: Optional[int] = Field(None, description="Maximum drawdown duration in days")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(None, description="Sortino ratio")
    calmar_ratio: Optional[float] = Field(None, description="Calmar ratio")
    volatility: Optional[float] = Field(None, description="Portfolio volatility (standard deviation)")
    var_95: Optional[float] = Field(None, description="Value at Risk (95% confidence)")
    var_99: Optional[float] = Field(None, description="Value at Risk (99% confidence)")
    risk_of_ruin: Optional[float] = Field(None, description="Estimated risk of ruin")
    avg_risk_per_trade: Optional[float] = Field(None, description="Average risk per trade as percentage")
    risk_reward_ratio: Optional[float] = Field(None, description="Risk-reward ratio")
    drawdown_periods: Optional[List[Dict[str, Any]]] = Field(None, description="List of significant drawdown periods")
    risk_concentration: Optional[Dict[str, float]] = Field(None, description="Risk concentration by symbol or agent")


class TradeStats(BaseModel):
    """Trading statistics model."""
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    breakeven_trades: int = Field(..., description="Number of breakeven trades")
    win_rate: float = Field(..., description="Win rate as a percentage")
    avg_win: Optional[float] = Field(None, description="Average profit on winning trades")
    avg_loss: Optional[float] = Field(None, description="Average loss on losing trades")
    largest_win: Optional[float] = Field(None, description="Largest winning trade")
    largest_loss: Optional[float] = Field(None, description="Largest losing trade")
    avg_trade_duration: Optional[float] = Field(None, description="Average trade duration in seconds")
    avg_bars_in_trade: Optional[float] = Field(None, description="Average number of bars in a trade")
    profitable_days: Optional[int] = Field(None, description="Number of profitable days")
    unprofitable_days: Optional[int] = Field(None, description="Number of unprofitable days")
    best_day: Optional[float] = Field(None, description="Best day return")
    worst_day: Optional[float] = Field(None, description="Worst day return")


class PerformanceMetrics(BaseModel):
    """Comprehensive performance metrics model."""
    total_return: float = Field(..., description="Total return percentage")
    annualized_return: Optional[float] = Field(None, description="Annualized return percentage")
    trade_stats: TradeStats = Field(..., description="Trading statistics")
    risk_metrics: RiskMetrics = Field(..., description="Risk metrics")
    expectancy: Optional[float] = Field(None, description="System expectancy (average profit per trade)")
    expectancy_ratio: Optional[float] = Field(None, description="Expectancy ratio")
    profit_factor: Optional[float] = Field(None, description="Profit factor (gross profit / gross loss)")
    kelly_percentage: Optional[float] = Field(None, description="Kelly criterion percentage")
    recovery_factor: Optional[float] = Field(None, description="Recovery factor")
    z_score: Optional[float] = Field(None, description="Z-score (statistical significance)")
    trades: Optional[List[TradeResponse]] = Field(None, description="Individual trade data")
    trade_distribution: Optional[Dict[str, Any]] = Field(None, description="Distribution of trade results")
    time_analysis: Optional[Dict[str, Any]] = Field(None, description="Time-based analysis")


class MetricsResponse(BaseModel):
    """Combined metrics response model."""
    pnl: PnLResponse = Field(..., description="Profit and loss metrics")
    performance: PerformanceMetrics = Field(..., description="Performance metrics")
    timestamp: datetime = Field(..., description="Timestamp when the data was generated")


class ReportResponse(BaseModel):
    """Report generation response model."""
    report_id: str = Field(..., description="Report ID")
    report_type: ReportType = Field(..., description="Type of report")
    format: ReportFormat = Field(..., description="Output format")
    url: str = Field(..., description="URL to download the report")
    expires_at: Optional[datetime] = Field(None, description="URL expiration timestamp")
    created_at: datetime = Field(..., description="Report creation timestamp")
    size_bytes: Optional[int] = Field(None, description="Size of the report in bytes")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters used to generate the report")
    status: Optional[str] = Field("completed", description="Status of the report generation (generating, completed, failed)")

    class Config:
        schema_extra = {
            "example": {
                "report_id": "report-123456",
                "report_type": "performance",
                "format": "pdf",
                "url": "/api/v1/analytics/reports/report-123456",
                "expires_at": "2023-07-01T00:00:00Z",
                "created_at": "2023-06-01T15:30:45Z",
                "size_bytes": 156289,
                "parameters": {
                    "agent_id": "agent-001",
                    "timeframe": "month",
                    "start_date": "2023-05-01T00:00:00Z",
                    "end_date": "2023-06-01T00:00:00Z"
                },
                "status": "completed"
            }
        } 