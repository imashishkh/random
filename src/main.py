"""
Main application entry point with basic health check
"""
import os
import json
import logging
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from pydantic import BaseModel
import uvicorn
from typing import Dict, Any, List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import security modules
from .security.auth import setup_security
from .security.api_key import get_api_key, require_scopes, ApiKey

# Import exchange modules
from .exchange import BinanceClient

# Import agent health monitoring modules
from .agents.health import get_health_monitor

# Import analytics modules
from .analytics.api import router as analytics_router

# Import cache modules
from .cache.redis_cache import get_redis_connection

# Import middleware modules
from .api.middleware.rate_limiter import RateLimiter

# Import config
from .config import settings

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Forex Trading AI System",
    description="USDT-Based Forex AI Trading Agent Swarm",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Apply security middleware
app = setup_security(app)

# Initialize exchange clients
binance_client = None

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analytics_router)

@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup"""
    global binance_client
    
    try:
        # Initialize Binance client
        logger.info("Initializing Binance client...")
        use_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
        binance_client = BinanceClient(
            testnet=use_testnet,
            timeout=int(os.getenv("BINANCE_TIMEOUT_MS", "30000")),
            enable_rate_limit=True
        )
        logger.info("Binance client initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Binance client: {str(e)}")
        # Don't crash the application if Binance client fails to initialize
        # It will be reported as offline in health checks

    # Initialize and start agent health monitoring
    try:
        health_monitor = get_health_monitor()
        health_monitor.start_monitoring()
        logger.info("Started agent health monitoring")
    except Exception as e:
        logger.error(f"Failed to start agent health monitoring: {str(e)}")

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    services: dict

class AgentHealthResponse(BaseModel):
    agent_id: str
    status: str
    details: dict

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify system status
    """
    try:
        # Check the status of Binance API
        binance_status = "offline"
        binance_message = "Not initialized"
        
        if binance_client:
            try:
                success, message = binance_client.test_connection()
                binance_status = "online" if success else "degraded"
                binance_message = message
            except Exception as e:
                binance_status = "error"
                binance_message = str(e)
        
        # Check agent health monitoring status
        agent_health_status = "offline"
        agent_health_message = "Not initialized"
        
        try:
            health_monitor = get_health_monitor()
            if health_monitor.running:
                agent_health_status = "online"
                agent_health_message = f"Monitoring {len(health_monitor.agent_metrics)} agents"
            else:
                agent_health_status = "offline"
                agent_health_message = "Monitoring service not running"
        except Exception as e:
            agent_health_status = "error"
            agent_health_message = str(e)
        
        # Check the status of other services
        # In a real implementation, we would check each service
        services = {
            "database": "online",
            "kafka": "online",
            "redis": "online",
            "binance_api": {
                "status": binance_status,
                "message": binance_message
            },
            "agent_health_monitoring": {
                "status": agent_health_status,
                "message": agent_health_message
            }
        }
        
        # Determine overall status based on service statuses
        overall_status = "healthy"
        if any(service == "offline" or (isinstance(service, dict) and service.get("status") == "offline") 
               for service in services.values()):
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "version": app.version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "services": services
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="System health check failed")

@app.get("/api/agents/health", dependencies=[Depends(get_api_key)])
async def agent_health_metrics():
    """
    Get health metrics for all agents
    """
    try:
        health_monitor = get_health_monitor()
        
        if not health_monitor.running:
            # Start monitoring if not already running
            health_monitor.start_monitoring()
            logger.info("Started agent health monitoring")
        
        all_metrics = health_monitor.get_all_health_metrics()
        
        # Convert to list of agent health responses
        agents_health = []
        for agent_id, metrics in all_metrics.items():
            agents_health.append({
                "agent_id": agent_id,
                "status": metrics["status"],
                "details": metrics
            })
        
        return {
            "agents_count": len(agents_health),
            "agents": agents_health
        }
    except Exception as e:
        logger.error(f"Error retrieving agent health metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve agent health metrics: {str(e)}")

@app.get("/api/agents/health/{agent_id}", dependencies=[Depends(get_api_key)])
async def agent_health_detail(agent_id: str):
    """
    Get detailed health metrics for a specific agent
    """
    try:
        health_monitor = get_health_monitor()
        metrics = health_monitor.get_agent_health(agent_id)
        
        if metrics is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found or not registered for health monitoring")
        
        return {
            "agent_id": agent_id,
            "status": metrics["status"],
            "details": metrics
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving health metrics for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve health metrics: {str(e)}")

@app.post("/api/agents/{agent_id}/restart", dependencies=[Depends(require_scopes(["admin"]))])
async def restart_agent(agent_id: str):
    """
    Restart a specific agent. Requires admin scope.
    """
    try:
        health_monitor = get_health_monitor()
        
        # Check if agent exists
        if agent_id not in health_monitor.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found or not registered for health monitoring")
        
        # Get agent metrics
        metrics = health_monitor.agent_metrics.get(agent_id)
        
        # Attempt to restart the agent
        success = health_monitor._restart_agent(agent_id, metrics)
        
        if success:
            return {
                "success": True,
                "message": f"Agent {agent_id} restarted successfully"
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to restart agent {agent_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to restart agent: {str(e)}")

@app.post("/api/agents/monitoring/start", dependencies=[Depends(require_scopes(["admin"]))])
async def start_monitoring():
    """
    Start the agent health monitoring. Requires admin scope.
    """
    try:
        health_monitor = get_health_monitor()
        
        if health_monitor.running:
            return {
                "success": True,
                "message": "Agent health monitoring is already running"
            }
        
        health_monitor.start_monitoring()
        return {
            "success": True,
            "message": "Agent health monitoring started successfully"
        }
    except Exception as e:
        logger.error(f"Error starting agent health monitoring: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {str(e)}")

@app.post("/api/agents/monitoring/stop", dependencies=[Depends(require_scopes(["admin"]))])
async def stop_monitoring():
    """
    Stop the agent health monitoring. Requires admin scope.
    """
    try:
        health_monitor = get_health_monitor()
        
        if not health_monitor.running:
            return {
                "success": True,
                "message": "Agent health monitoring is not running"
            }
        
        health_monitor.stop_monitoring()
        return {
            "success": True,
            "message": "Agent health monitoring stopped successfully"
        }
    except Exception as e:
        logger.error(f"Error stopping agent health monitoring: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {str(e)}")

@app.get("/")
async def root():
    """
    Root endpoint
    """
    return {
        "name": "Forex Trading AI System",
        "version": app.version,
        "status": "running"
    }

@app.get("/api/secure", dependencies=[Depends(get_api_key)])
async def secure_endpoint():
    """
    A secure endpoint that requires API key authentication
    """
    return {
        "message": "You have access to the secure API",
        "authenticated": True
    }

@app.get("/api/admin", dependencies=[Depends(require_scopes(["admin"]))])
async def admin_endpoint():
    """
    Admin endpoint that requires an API key with admin scope
    """
    return {
        "message": "You have access to the admin API",
        "admin": True
    }

@app.post("/api/keys")
async def create_api_key(request: Request, api_key: ApiKey = Depends(require_scopes(["admin"]))):
    """
    Create a new API key (requires admin scope)
    """
    from src.security.api_key import generate_api_key
    
    # Extract request data
    data = await request.json()
    name = data.get("name", "Default Key")
    owner_id = data.get("owner_id", 1)  # Default owner ID
    expires_days = data.get("expires_days", 90)
    scopes = data.get("scopes", ["read"])
    
    # Generate new API key
    raw_key, key_record = generate_api_key(
        name=name,
        owner_id=owner_id,
        expires_days=expires_days,
        scopes=scopes
    )
    
    # Return the raw key (only shown once)
    return {
        "message": "API key created successfully",
        "key": raw_key,
        "expires_at": key_record.expires_at.isoformat(),
        "scopes": key_record.scopes
    }

@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event handler
    """
    logger.info("Shutting down the application")
    
    # Stop agent health monitoring
    try:
        health_monitor = get_health_monitor()
        if health_monitor.running:
            health_monitor.stop_monitoring()
            logger.info("Stopped agent health monitoring")
    except Exception as e:
        logger.error(f"Error stopping agent health monitoring: {str(e)}")

# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for HTTP exceptions"""
    return Response(
        status_code=exc.status_code,
        content=json.dumps({"detail": exc.detail}),
        media_type="application/json"
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting application on {host}:{port}")
    uvicorn.run(app, host=host, port=port) 