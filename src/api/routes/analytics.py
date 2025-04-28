"""
API routes for analytics functionality.

This module provides the routes for the analytics API, allowing clients
to access performance metrics, trade data, and risk analysis.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ...database import get_db
from ...analytics.service import AnalyticsService
from .schemas.analytics import (
    PerformanceMetricsResponse,
    PnLOverTimeResponse,
    TradeDistributionResponse,
    RiskAnalysisResponse,
    DateRangeParams
)
from .deps import get_current_user
from ...models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/performance", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    agent_id: Optional[int] = None,
    symbol: Optional[str] = None,
    params: DateRangeParams = Depends(),
    use_cache: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get performance metrics for trading activities.
    
    Returns key performance indicators including Sharpe ratio, Sortino ratio,
    max drawdown, win rate, and more.
    """
    try:
        analytics_service = AnalyticsService(db=db)
        
        # Convert date string to datetime if provided
        start_date = params.start_date
        end_date = params.end_date
        
        # If timeframe is provided, override start_date
        if params.timeframe and not params.start_date:
            now = datetime.now()
            if params.timeframe == "day":
                start_date = now - timedelta(days=1)
            elif params.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif params.timeframe == "month":
                start_date = now - timedelta(days=30)
            elif params.timeframe == "quarter":
                start_date = now - timedelta(days=90)
            elif params.timeframe == "year":
                start_date = now - timedelta(days=365)
        
        # Get performance metrics
        metrics = await analytics_service.get_performance_metrics(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            use_cache=use_cache
        )
        
        return metrics
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting performance metrics: {str(e)}")

@router.get("/pnl-over-time", response_model=List[PnLOverTimeResponse])
async def get_pnl_over_time(
    agent_id: Optional[int] = None,
    symbol: Optional[str] = None,
    interval: str = Query("day", enum=["day", "week", "month"]),
    params: DateRangeParams = Depends(),
    use_cache: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get P&L over time for visualization.
    
    Returns profit and loss data grouped by day, week, or month.
    """
    try:
        analytics_service = AnalyticsService(db=db)
        
        # Convert date string to datetime if provided
        start_date = params.start_date
        end_date = params.end_date
        
        # If timeframe is provided, override start_date
        if params.timeframe and not params.start_date:
            now = datetime.now()
            if params.timeframe == "day":
                start_date = now - timedelta(days=1)
            elif params.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif params.timeframe == "month":
                start_date = now - timedelta(days=30)
            elif params.timeframe == "quarter":
                start_date = now - timedelta(days=90)
            elif params.timeframe == "year":
                start_date = now - timedelta(days=365)
        
        # Get P&L over time
        pnl_data = await analytics_service.get_pnl_over_time(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            use_cache=use_cache
        )
        
        return pnl_data
    except Exception as e:
        logger.error(f"Error getting P&L over time: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting P&L over time: {str(e)}")

@router.get("/trade-distribution", response_model=TradeDistributionResponse)
async def get_trade_distribution(
    agent_id: Optional[int] = None,
    symbol: Optional[str] = None,
    params: DateRangeParams = Depends(),
    use_cache: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get trade distribution analysis.
    
    Returns trade distributions by symbol, direction, time of day, 
    and day of week.
    """
    try:
        analytics_service = AnalyticsService(db=db)
        
        # Convert date string to datetime if provided
        start_date = params.start_date
        end_date = params.end_date
        
        # If timeframe is provided, override start_date
        if params.timeframe and not params.start_date:
            now = datetime.now()
            if params.timeframe == "day":
                start_date = now - timedelta(days=1)
            elif params.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif params.timeframe == "month":
                start_date = now - timedelta(days=30)
            elif params.timeframe == "quarter":
                start_date = now - timedelta(days=90)
            elif params.timeframe == "year":
                start_date = now - timedelta(days=365)
        
        # Get trade distribution
        distribution = await analytics_service.get_trade_distribution(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            use_cache=use_cache
        )
        
        return distribution
    except Exception as e:
        logger.error(f"Error getting trade distribution: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting trade distribution: {str(e)}")

@router.get("/risk-analysis", response_model=RiskAnalysisResponse)
async def get_risk_analysis(
    agent_id: Optional[int] = None,
    symbol: Optional[str] = None,
    params: DateRangeParams = Depends(),
    use_cache: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get risk analysis metrics.
    
    Returns risk metrics including max drawdown, Value at Risk (VaR),
    consecutive losses, and risk-reward ratio.
    """
    try:
        analytics_service = AnalyticsService(db=db)
        
        # Convert date string to datetime if provided
        start_date = params.start_date
        end_date = params.end_date
        
        # If timeframe is provided, override start_date
        if params.timeframe and not params.start_date:
            now = datetime.now()
            if params.timeframe == "day":
                start_date = now - timedelta(days=1)
            elif params.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif params.timeframe == "month":
                start_date = now - timedelta(days=30)
            elif params.timeframe == "quarter":
                start_date = now - timedelta(days=90)
            elif params.timeframe == "year":
                start_date = now - timedelta(days=365)
        
        # Get risk analysis
        risk_analysis = await analytics_service.get_risk_analysis(
            agent_id=agent_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            use_cache=use_cache
        )
        
        return risk_analysis
    except Exception as e:
        logger.error(f"Error getting risk analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting risk analysis: {str(e)}")

@router.delete("/cache")
async def invalidate_analytics_cache(
    agent_id: Optional[int] = None,
    symbol: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Invalidate the analytics cache for specified parameters.
    
    This is useful after new trades are added or existing trades are modified.
    """
    try:
        analytics_service = AnalyticsService(db=db)
        
        # Invalidate cache
        result = await analytics_service.invalidate_cache(
            agent_id=agent_id,
            symbol=symbol
        )
        
        if result:
            return {"status": "success", "message": "Cache invalidated successfully"}
        else:
            return {"status": "warning", "message": "Cache invalidation may not be complete"}
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error invalidating cache: {str(e)}") 