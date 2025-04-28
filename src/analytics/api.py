"""
API endpoints for analytics and reporting services.

This module defines the FastAPI router for the analytics features,
including trade data retrieval, performance metrics, and report generation.
"""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Path, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import io

from ..security.api_key import get_api_key, require_scopes, ApiKey
from .service import AnalyticsService
from .reporting import ReportingService
from .models import (
    TimeFrame, ReportType, ReportFormat,
    TradeResponse, PositionResponse, 
    PnLResponse, RiskMetrics, PerformanceMetrics,
    MetricsResponse, ReportResponse
)
from ..api.middleware.rate_limiter import RateLimiter
from ..config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_api_key)]
)

# Initialize services
analytics_service = AnalyticsService()
reporting_service = ReportingService()

# Error responses for documentation
COMMON_RESPONSES = {
    400: {"description": "Bad Request - Invalid parameters"},
    401: {"description": "Unauthorized - Authentication required"},
    403: {"description": "Forbidden - Insufficient permissions"},
    429: {"description": "Too Many Requests - Rate limit exceeded"}
}

@router.get(
    "/trades", 
    response_model=List[TradeResponse],
    responses=COMMON_RESPONSES,
    summary="Retrieve trade data",
    description="""
    Retrieve trade data with optional filtering options.
    
    This endpoint supports filtering by symbol, agent ID, time range, and status.
    Results are paginated and can be sorted by various fields.
    
    Rate limits:
    - Basic tier: 100 requests/minute
    - Premium tier: 500 requests/minute
    - Enterprise tier: 2000 requests/minute
    
    Results are cached for 5 minutes.
    """
)
@require_scopes(["analytics:read"])
async def get_trades(
    symbol: Optional[str] = None,
    agent_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=100, seconds=60))
):
    """
    Retrieve trade data with optional filtering.
    
    Args:
        symbol: Filter by trading symbol (e.g., "EURUSD")
        agent_id: Filter by agent ID
        start_time: Filter trades after this datetime
        end_time: Filter trades before this datetime
        status: Filter by trade status (e.g., "OPEN", "CLOSED")
        page: Page number for pagination
        page_size: Number of items per page
        
    Returns:
        List of trades matching the filter criteria
    """
    try:
        trades = await analytics_service.get_trades(
            symbol=symbol,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
            page=page,
            page_size=page_size
        )
        return trades
    except Exception as e:
        logger.error(f"Error retrieving trades: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving trades: {str(e)}")

@router.get(
    "/positions", 
    response_model=List[PositionResponse],
    responses=COMMON_RESPONSES,
    summary="Retrieve position data",
    description="""
    Retrieve position data with optional filtering options.
    
    This endpoint supports filtering by symbol, agent ID, and status.
    Results are paginated and include both open and closed positions.
    
    Rate limits:
    - Basic tier: 100 requests/minute
    - Premium tier: 500 requests/minute
    - Enterprise tier: 2000 requests/minute
    
    Results are cached for 5 minutes.
    """
)
@require_scopes(["analytics:read"])
async def get_positions(
    symbol: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=100, seconds=60))
):
    """
    Retrieve position data with optional filtering.
    
    Args:
        symbol: Filter by trading symbol (e.g., "EURUSD")
        agent_id: Filter by agent ID
        status: Filter by position status (e.g., "OPEN", "CLOSED")
        page: Page number for pagination
        page_size: Number of items per page
        
    Returns:
        List of positions matching the filter criteria
    """
    try:
        positions = await analytics_service.get_positions(
            symbol=symbol,
            agent_id=agent_id,
            status=status,
            page=page,
            page_size=page_size
        )
        return positions
    except Exception as e:
        logger.error(f"Error retrieving positions: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving positions: {str(e)}")

@router.get(
    "/pnl", 
    response_model=PnLResponse,
    responses=COMMON_RESPONSES,
    summary="Get profit/loss metrics",
    description="""
    Get profit and loss metrics for a specific time period.
    
    This endpoint calculates PnL metrics including realized, unrealized, and total PnL,
    as well as time series data for PnL over the specified period.
    
    Rate limits:
    - Basic tier: 50 requests/minute
    - Premium tier: 250 requests/minute
    - Enterprise tier: 1000 requests/minute
    
    Results are cached for 10 minutes.
    """
)
@require_scopes(["analytics:read"])
async def get_pnl_metrics(
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    timeframe: TimeFrame = TimeFrame.MONTH,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=50, seconds=60))
):
    """
    Get profit and loss metrics for a specific time period.
    
    Args:
        agent_id: Filter by agent ID
        symbol: Filter by trading symbol (e.g., "EURUSD")
        timeframe: Time period for grouping data (day, week, month, etc.)
        start_date: Start date for filtering data
        end_date: End date for filtering data
        
    Returns:
        PnL metrics including realized, unrealized, and total PnL
    """
    try:
        pnl = await analytics_service.get_pnl_metrics(
            agent_id=agent_id,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date
        )
        return pnl
    except ValueError as e:
        # Handle specific validation errors
        logger.warning(f"Invalid parameters for PnL metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving PnL metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving PnL metrics: {str(e)}")

@router.get(
    "/risk", 
    response_model=RiskMetrics,
    responses=COMMON_RESPONSES,
    summary="Get risk metrics",
    description="""
    Get risk analysis metrics for a specific time period.
    
    This endpoint calculates risk metrics including drawdown, volatility, Sharpe ratio,
    Sortino ratio, and maximum consecutive losses.
    
    Rate limits:
    - Basic tier: 50 requests/minute
    - Premium tier: 250 requests/minute
    - Enterprise tier: 1000 requests/minute
    
    Results are cached for 10 minutes.
    """
)
@require_scopes(["analytics:read"])
async def get_risk_metrics(
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    timeframe: TimeFrame = TimeFrame.MONTH,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=50, seconds=60))
):
    """
    Get risk analysis metrics for a specific time period.
    
    Args:
        agent_id: Filter by agent ID
        symbol: Filter by trading symbol
        timeframe: Time period for analysis
        start_date: Start date for filtering data
        end_date: End date for filtering data
        
    Returns:
        Risk metrics including drawdown, volatility, and risk ratios
    """
    try:
        # Get time range from timeframe if dates not specified
        if not start_date or not end_date:
            start_date, end_date = await analytics_service._get_time_range(timeframe, start_date, end_date)
            
        # Retrieve positions for risk calculation
        positions = await analytics_service.get_positions(
            agent_id=agent_id,
            symbol=symbol,
            status="CLOSED",
            start_time=start_date,
            end_time=end_date
        )
        
        # Retrieve trades for risk calculation
        trades = await analytics_service.get_trades(
            agent_id=agent_id,
            symbol=symbol,
            start_time=start_date,
            end_time=end_date
        )
        
        # Calculate risk metrics
        risk_metrics = await analytics_service.calculate_risk_metrics(positions, trades)
        return risk_metrics
    except Exception as e:
        logger.error(f"Error retrieving risk metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving risk metrics: {str(e)}")

@router.get(
    "/performance", 
    response_model=PerformanceMetrics,
    responses=COMMON_RESPONSES,
    summary="Get comprehensive performance metrics",
    description="""
    Get comprehensive performance metrics for a specific time period.
    
    This endpoint provides a complete performance analysis including PnL, risk,
    and trade statistics metrics in a single response.
    
    Rate limits:
    - Basic tier: 30 requests/minute
    - Premium tier: 150 requests/minute
    - Enterprise tier: 600 requests/minute
    
    Results are cached for 10 minutes.
    """
)
@require_scopes(["analytics:read"])
async def get_performance_metrics(
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    timeframe: TimeFrame = TimeFrame.MONTH,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_trades: bool = False,
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=30, seconds=60))
):
    """
    Get comprehensive performance metrics for a specific time period.
    
    Args:
        agent_id: Filter by agent ID
        symbol: Filter by trading symbol
        timeframe: Time period for analysis
        start_date: Start date for filtering data
        end_date: End date for filtering data
        include_trades: Whether to include trade data in the response
        
    Returns:
        Comprehensive performance metrics
    """
    try:
        performance = await analytics_service.get_performance_metrics(
            agent_id=agent_id,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            include_trades=include_trades
        )
        return performance
    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving performance metrics: {str(e)}")

@router.post(
    "/reports", 
    response_model=ReportResponse,
    responses={
        **COMMON_RESPONSES,
        202: {"description": "Accepted - Report generation started"}
    },
    summary="Generate a report",
    description="""
    Generate a report of the specified type and format.
    
    This endpoint initiates report generation for various report types including
    performance reports, trade logs, daily PnL, and risk analysis.
    
    For large reports, the generation will happen in the background and a status
    endpoint will be provided to check progress.
    
    Rate limits:
    - Basic tier: 10 requests/minute
    - Premium tier: 50 requests/minute
    - Enterprise tier: 200 requests/minute
    
    Reports are stored for 30 days.
    """
)
@require_scopes(["analytics:read", "reports:generate"])
async def generate_report(
    report_type: ReportType,
    format: ReportFormat = ReportFormat.PDF,
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    timeframe: TimeFrame = TimeFrame.MONTH,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    background: bool = True,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=10, seconds=60))
):
    """
    Generate a report of the specified type and format.
    
    Args:
        report_type: Type of report to generate
        format: Output format for the report
        agent_id: Filter by agent ID
        symbol: Filter by trading symbol
        timeframe: Time period for the report
        start_date: Start date for filtering data
        end_date: End date for filtering data
        background: Whether to generate the report in the background
        
    Returns:
        Report response with metadata and download URL
    """
    try:
        # Get time range from timeframe if dates not specified
        if not start_date or not end_date:
            start_date, end_date = await analytics_service._get_time_range(timeframe, start_date, end_date)
        
        # Prepare data for report generation
        if report_type == ReportType.PERFORMANCE:
            # Get performance metrics for the report
            performance = await analytics_service.get_performance_metrics(
                agent_id=agent_id or api_key.account_id,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                include_trades=True
            )
            
            # Convert to dict for the report generator
            data = performance.dict()
        elif report_type == ReportType.TRADE_HISTORY:
            # Get trades for the report
            trades = await analytics_service.get_trades(
                agent_id=agent_id or api_key.account_id,
                symbol=symbol,
                start_time=start_date,
                end_time=end_date,
                page_size=1000  # Get a large number of trades for the report
            )
            
            # Prepare data
            data = {
                "trades": [trade.dict() for trade in trades],
                "start_date": start_date,
                "end_date": end_date,
                "account_id": agent_id or api_key.account_id,
                "symbol": symbol,
                "timeframe": timeframe.value
            }
        elif report_type == ReportType.PNL:
            # Get PnL metrics for the report
            pnl = await analytics_service.get_pnl_metrics(
                agent_id=agent_id or api_key.account_id,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )
            
            # Convert to dict for the report generator
            data = pnl.dict()
        elif report_type == ReportType.RISK_ANALYSIS:
            # Get risk metrics for the report
            risk = await analytics_service.get_risk_metrics(
                agent_id=agent_id or api_key.account_id,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )
            
            # Convert to dict for the report generator
            data = risk.dict()
        else:
            raise ValueError(f"Unsupported report type: {report_type}")
        
        # Add common fields
        data.update({
            "generated_at": datetime.now().isoformat(),
            "start_date": start_date,
            "end_date": end_date,
            "account_id": agent_id or api_key.account_id,
            "symbol": symbol,
            "timeframe": timeframe.value,
            "report_type": report_type.value
        })
        
        # Generate the report
        if background:
            # Use background tasks for report generation
            report = await reporting_service.generate_report(
                report_type=report_type,
                format=format,
                data=data,
                background_tasks=background_tasks
            )
            
            # Return 202 Accepted with report ID
            return report
        else:
            # Generate report synchronously
            report = await reporting_service.generate_report(
                report_type=report_type,
                format=format,
                data=data
            )
            
            return report
    except ValueError as e:
        # Handle validation errors
        logger.warning(f"Invalid parameters for report generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

@router.get(
    "/reports/{report_id}",
    responses={
        **COMMON_RESPONSES,
        200: {"description": "OK - Report found", "content": {"application/octet-stream": {}}},
        404: {"description": "Not Found - Report not found"}
    },
    summary="Download a generated report",
    description="""
    Download a previously generated report by its ID.
    
    This endpoint returns the report file in the format it was generated in.
    The file will be returned with the appropriate content type and disposition headers.
    
    Rate limits:
    - Basic tier: 20 requests/minute
    - Premium tier: 100 requests/minute
    - Enterprise tier: 500 requests/minute
    """
)
@require_scopes(["analytics:read", "reports:read"])
async def get_report(
    report_id: str = Path(..., description="The ID of the report to download"),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=20, seconds=60))
):
    """
    Download a generated report.
    
    Args:
        report_id: The ID of the report to download
        
    Returns:
        The report file as a streaming response
    """
    try:
        # Get the report and its metadata
        report_data, metadata = await reporting_service.get_report(report_id)
        
        # Get the format from metadata
        format_value = metadata.get("format", "json").lower()
        
        # Set content type based on format
        content_types = {
            "pdf": "application/pdf",
            "csv": "text/csv",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json"
        }
        content_type = content_types.get(format_value, "application/octet-stream")
        
        # Set filename based on report type and format
        report_type = metadata.get("report_type", "report")
        filename = f"{report_type}_{datetime.now().strftime('%Y%m%d')}.{format_value}"
        
        # Return the report as a streaming response
        return StreamingResponse(
            report_data,
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except FileNotFoundError:
        # Report not found
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    except Exception as e:
        logger.error(f"Error retrieving report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving report: {str(e)}")

@router.get(
    "/reports/{report_id}/status",
    response_model=Dict[str, Any],
    responses={
        **COMMON_RESPONSES,
        404: {"description": "Not Found - Report not found"}
    },
    summary="Check report generation status",
    description="""
    Check the status of a background report generation task.
    
    This endpoint returns the current status of the report generation process,
    including progress percentage and estimated completion time if available.
    
    Rate limits:
    - Basic tier: 30 requests/minute
    - Premium tier: 150 requests/minute
    - Enterprise tier: 600 requests/minute
    """
)
@require_scopes(["analytics:read", "reports:read"])
async def check_report_status(
    report_id: str = Path(..., description="The ID of the report to check"),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=30, seconds=60))
):
    """
    Check report generation status.
    
    Args:
        report_id: The ID of the report to check
        
    Returns:
        Status information for the report
    """
    try:
        # For simplicity, we'll try to get the report
        # If it exists, it's completed; if not, it's still generating
        try:
            await reporting_service.get_report(report_id)
            return {
                "report_id": report_id,
                "status": "completed",
                "progress": 100,
                "url": f"/api/v1/analytics/reports/{report_id}"
            }
        except FileNotFoundError:
            # Report not found, check if it's being generated
            # In a real application, you would check a database record
            return {
                "report_id": report_id,
                "status": "generating",
                "progress": 50,  # Placeholder
                "estimated_completion": (datetime.now() + timedelta(minutes=1)).isoformat()
            }
    except Exception as e:
        logger.error(f"Error checking report status for {report_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking report status: {str(e)}")

@router.get(
    "/reports",
    response_model=List[Dict[str, Any]],
    responses=COMMON_RESPONSES,
    summary="List available reports",
    description="""
    List reports that have been generated for the authenticated user.
    
    This endpoint returns metadata for all available reports, including
    report type, format, generation date, and download URL.
    
    Rate limits:
    - Basic tier: 20 requests/minute
    - Premium tier: 100 requests/minute
    - Enterprise tier: 500 requests/minute
    """
)
@require_scopes(["analytics:read", "reports:read"])
async def list_reports(
    report_type: Optional[ReportType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=20, seconds=60))
):
    """
    List available reports.
    
    Args:
        report_type: Filter by report type
        start_date: Filter reports generated after this date
        end_date: Filter reports generated before this date
        
    Returns:
        List of report metadata
    """
    try:
        # Get reports for the user
        reports = await reporting_service.list_reports(api_key.account_id)
        
        # Apply filters if provided
        if report_type:
            reports = [r for r in reports if r.get("report_type") == report_type]
        
        if start_date:
            reports = [r for r in reports if datetime.fromisoformat(r.get("created_at", "2000-01-01")) >= start_date]
        
        if end_date:
            reports = [r for r in reports if datetime.fromisoformat(r.get("created_at", "2099-12-31")) <= end_date]
        
        # Add download URLs
        for report in reports:
            report["url"] = f"/api/v1/analytics/reports/{report['report_id']}"
        
        return reports
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing reports: {str(e)}")

@router.delete(
    "/reports/{report_id}",
    response_model=Dict[str, Any],
    responses={
        **COMMON_RESPONSES,
        404: {"description": "Not Found - Report not found"}
    },
    summary="Delete a report",
    description="""
    Delete a previously generated report.
    
    This endpoint permanently deletes a report and its metadata.
    This action cannot be undone.
    
    Rate limits:
    - Basic tier: 10 requests/minute
    - Premium tier: 50 requests/minute
    - Enterprise tier: 200 requests/minute
    """
)
@require_scopes(["reports:delete"])
async def delete_report(
    report_id: str = Path(..., description="The ID of the report to delete"),
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=10, seconds=60))
):
    """
    Delete a report.
    
    Args:
        report_id: The ID of the report to delete
        
    Returns:
        Success message
    """
    try:
        # Delete the report
        success = await reporting_service.delete_report(report_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
        
        return {"message": f"Report {report_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting report: {str(e)}")

@router.get(
    "/trades/export",
    responses={
        **COMMON_RESPONSES,
        200: {"description": "OK - Export successful", "content": {"text/csv": {}, "application/json": {}}}
    },
    summary="Export trade data",
    description="""
    Export trade data in CSV or JSON format.
    
    This endpoint supports filtering by symbol, time range, and status.
    The data is returned as a streaming response to handle large datasets efficiently.
    
    Rate limits:
    - Basic tier: 5 requests/minute
    - Premium tier: 20 requests/minute
    - Enterprise tier: 50 requests/minute
    """
)
@require_scopes(["analytics:read", "data:export"])
async def export_trades(
    format: str = Query("csv", description="Export format (csv or json)"),
    symbol: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    api_key: ApiKey = Depends(get_api_key),
    rate_limiter: bool = Depends(RateLimiter(times=5, seconds=60))
):
    """
    Export trade data in CSV or JSON format.
    
    Args:
        format: Export format (csv or json)
        symbol: Filter by trading symbol
        start_date: Filter trades after this date
        end_date: Filter trades before this date
        status: Filter by trade status
        
    Returns:
        Streaming response with the exported data
    """
    try:
        # Get trades with filtering
        trades = await analytics_service.get_trades(
            agent_id=api_key.account_id,
            symbol=symbol,
            start_time=start_date,
            end_time=end_date,
            status=status,
            page_size=10000  # Get a large number of trades for export
        )
        
        # Convert to list of dicts
        trade_dicts = [trade.dict() for trade in trades]
        
        if format.lower() == "csv":
            # Create in-memory string buffer
            output = io.StringIO()
            
            # Get field names from first trade or use defaults
            fieldnames = list(trade_dicts[0].keys()) if trade_dicts else [
                "id", "symbol", "direction", "quantity", "entry_price", 
                "exit_price", "pnl", "status", "open_time", "close_time"
            ]
            
            # Convert to CSV
            import csv
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for trade in trade_dicts:
                writer.writerow(trade)
            
            # Reset buffer position
            output.seek(0)
            
            # Return streaming response
            return StreamingResponse(
                output,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=trades_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
            )
        else:
            # Return JSON response
            return JSONResponse(content=trade_dicts)
    except Exception as e:
        logger.error(f"Error exporting trades: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting trades: {str(e)}")

# --- WebSocket endpoint for real-time analytics ---
# This would typically be in a separate websockets.py file but we're including it here for completeness

from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json

class AnalyticsConnectionManager:
    """Manager for WebSocket connections to real-time analytics."""
    
    def __init__(self):
        """Initialize the connection manager."""
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, account_id: str):
        """Connect a client to the WebSocket."""
        await websocket.accept()
        if account_id not in self.active_connections:
            self.active_connections[account_id] = []
        self.active_connections[account_id].append(websocket)
        
    def disconnect(self, websocket: WebSocket, account_id: str):
        """Disconnect a client from the WebSocket."""
        if account_id in self.active_connections:
            self.active_connections[account_id].remove(websocket)
            if not self.active_connections[account_id]:
                del self.active_connections[account_id]
                
    async def broadcast(self, account_id: str, message: Dict[str, Any]):
        """Broadcast a message to all connected clients for an account."""
        if account_id in self.active_connections:
            for connection in self.active_connections[account_id]:
                await connection.send_json(message)
                
    async def update_metrics_task(self, account_id: str, interval: int = 5):
        """Task to periodically update and broadcast metrics."""
        while account_id in self.active_connections:
            try:
                # Get latest metrics
                pnl_metrics = await analytics_service.get_pnl_metrics(
                    agent_id=account_id,
                    timeframe=TimeFrame.DAY
                )
                
                risk_metrics = await analytics_service.get_risk_metrics(
                    agent_id=account_id,
                    timeframe=TimeFrame.DAY
                )
                
                # Combine metrics
                metrics_update = {
                    "type": "metrics_update",
                    "timestamp": datetime.now().isoformat(),
                    "pnl": pnl_metrics.dict(),
                    "risk": risk_metrics.dict()
                }
                
                # Broadcast to all connections for this account
                await self.broadcast(account_id, metrics_update)
                
                # Wait for next update
                await asyncio.sleep(interval)
                
            except Exception as e:
                error_message = {
                    "type": "error",
                    "message": str(e)
                }
                await self.broadcast(account_id, error_message)
                await asyncio.sleep(interval)

# Initialize connection manager
analytics_ws_manager = AnalyticsConnectionManager()

@router.websocket("/ws/{account_id}")
async def websocket_analytics_endpoint(
    websocket: WebSocket, 
    account_id: str
):
    """WebSocket endpoint for real-time analytics updates."""
    # In a real application, you would authenticate the WebSocket connection
    # For simplicity, we're skipping that here
    
    await analytics_ws_manager.connect(websocket, account_id)
    
    # Start background task for updates
    task = asyncio.create_task(
        analytics_ws_manager.update_metrics_task(account_id)
    )
    
    try:
        while True:
            # Handle incoming messages (e.g., changing update frequency)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "set_interval":
                # Cancel existing task
                task.cancel()
                # Start new task with updated interval
                interval = int(message.get("interval", 5))
                task = asyncio.create_task(
                    analytics_ws_manager.update_metrics_task(account_id, interval)
                )
                
    except WebSocketDisconnect:
        analytics_ws_manager.disconnect(websocket, account_id)
        task.cancel()
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
        analytics_ws_manager.disconnect(websocket, account_id)
        task.cancel() 