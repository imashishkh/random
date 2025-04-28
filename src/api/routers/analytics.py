"""
API router for analytics endpoints. Provides access to trading performance metrics,
profit/loss over time, trade distribution analysis, and risk metrics.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import UUID4

from .schemas.analytics import (
    PerformanceMetricsResponse,
    PnLOverTimeResponse,
    TradeDistributionResponse,
    RiskAnalysisResponse
)
from ...services.analytics_service import AnalyticsService
from ...dependencies import get_analytics_service

# Create router
router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/performance", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    agent_id: Optional[UUID4] = None,
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    timeframe: Optional[str] = Query(None, description="Predefined timeframe (day, week, month, quarter, year)"),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> PerformanceMetricsResponse:
    """
    Get trading performance metrics for the specified filters.
    
    Returns key metrics like win rate, profit factor, and risk/reward ratio.
    
    - **agent_id**: Filter by trading agent
    - **symbol**: Filter by trading symbol/instrument
    - **start_date**: Analysis period start date
    - **end_date**: Analysis period end date  
    - **timeframe**: Predefined timeframe (overrides start/end dates)
    """
    try:
        return analytics_service.get_performance_metrics(
            agent_id=str(agent_id) if agent_id else None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving performance metrics: {str(e)}")


@router.get("/pnl", response_model=List[PnLOverTimeResponse])
async def get_pnl_over_time(
    interval: str = Query("day", description="Time interval for grouping (day, week, month)"),
    agent_id: Optional[UUID4] = None,
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    timeframe: Optional[str] = Query(None, description="Predefined timeframe (day, week, month, quarter, year)"),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> List[PnLOverTimeResponse]:
    """
    Get profit and loss data over time.
    
    Returns P&L for each time interval along with cumulative values.
    
    - **interval**: Time interval for grouping (day, week, month)
    - **agent_id**: Filter by trading agent
    - **symbol**: Filter by trading symbol/instrument
    - **start_date**: Analysis period start date
    - **end_date**: Analysis period end date
    - **timeframe**: Predefined timeframe (overrides start/end dates)
    """
    try:
        return analytics_service.get_pnl_over_time(
            interval=interval,
            agent_id=str(agent_id) if agent_id else None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving P&L data: {str(e)}")


@router.get("/distribution", response_model=TradeDistributionResponse)
async def get_trade_distribution(
    agent_id: Optional[UUID4] = None,
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    timeframe: Optional[str] = Query(None, description="Predefined timeframe (day, week, month, quarter, year)"),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> TradeDistributionResponse:
    """
    Get trade distribution analysis.
    
    Analyzes trade distribution by symbol, direction, time of day, and day of week.
    
    - **agent_id**: Filter by trading agent
    - **symbol**: Filter by trading symbol/instrument
    - **start_date**: Analysis period start date
    - **end_date**: Analysis period end date
    - **timeframe**: Predefined timeframe (overrides start/end dates)
    """
    try:
        return analytics_service.get_trade_distribution(
            agent_id=str(agent_id) if agent_id else None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving trade distribution: {str(e)}")


@router.get("/risk", response_model=RiskAnalysisResponse)
async def get_risk_analysis(
    agent_id: Optional[UUID4] = None,
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    timeframe: Optional[str] = Query(None, description="Predefined timeframe (day, week, month, quarter, year)"),
    confidence_level: float = Query(0.95, description="Confidence level for Value at Risk (VaR) calculation"),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> RiskAnalysisResponse:
    """
    Get risk analysis metrics.
    
    Provides drawdown metrics, Value at Risk, and other risk indicators.
    
    - **agent_id**: Filter by trading agent
    - **symbol**: Filter by trading symbol/instrument
    - **start_date**: Analysis period start date
    - **end_date**: Analysis period end date
    - **timeframe**: Predefined timeframe (overrides start/end dates)
    - **confidence_level**: Confidence level for VaR calculation (0.90, 0.95, 0.99)
    """
    try:
        return analytics_service.get_risk_analysis(
            agent_id=str(agent_id) if agent_id else None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            confidence_level=confidence_level
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving risk analysis: {str(e)}")


@router.post("/cache/clear")
async def clear_analytics_cache(
    agent_id: Optional[UUID4] = None,
    symbol: Optional[str] = None,
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Clear the analytics cache.
    
    Can be used to force fresh calculations after data changes.
    
    - **agent_id**: Clear cache only for this agent (optional)
    - **symbol**: Clear cache only for this symbol (optional)
    """
    try:
        analytics_service.clear_cache(
            agent_id=str(agent_id) if agent_id else None,
            symbol=symbol
        )
        return {"status": "success", "message": "Analytics cache cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing analytics cache: {str(e)}") 