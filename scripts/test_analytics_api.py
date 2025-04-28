#!/usr/bin/env python
"""
Test script for the Analytics API functionality.

This script tests the following features:
1. Redis caching behavior
2. Rate limiting functionality
3. API endpoint responses

Usage:
    python scripts/test_analytics_api.py
"""
import os
import sys
import time
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta

# API base URL
BASE_URL = "http://localhost:8000/api/v1/analytics"
API_KEY = os.environ.get("API_KEY", "test_key")

# Headers for API requests
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

async def test_endpoint_with_rate_limit(session, endpoint, requests_count):
    """Test rate limiting by making multiple requests to an endpoint."""
    print(f"\nTesting rate limiting for {endpoint}")
    start_time = time.time()
    
    responses = []
    for i in range(requests_count):
        async with session.get(f"{BASE_URL}/{endpoint}", headers=HEADERS) as response:
            response_json = await response.json()
            status = response.status
            responses.append(status)
            
            # Print rate limit headers
            rate_limit = response.headers.get("X-RateLimit-Limit")
            rate_remaining = response.headers.get("X-RateLimit-Remaining")
            rate_reset = response.headers.get("X-RateLimit-Reset")
            
            print(f"Request {i+1}: Status {status}, Limit: {rate_limit}, Remaining: {rate_remaining}, Reset: {rate_reset}")
            
            # If rate limited, break
            if status == 429:
                print(f"Rate limit hit after {i+1} requests")
                break
            
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.1)
    
    end_time = time.time()
    print(f"Completed in {end_time - start_time:.2f} seconds")
    print(f"Response statuses: {responses}")
    
    return responses

async def test_cache_behavior(session, endpoint, params=None):
    """Test caching behavior by making sequential requests to an endpoint."""
    print(f"\nTesting cache behavior for {endpoint}")
    
    # Make first request
    start_time = time.time()
    async with session.get(f"{BASE_URL}/{endpoint}", params=params, headers=HEADERS) as response:
        first_response = await response.json()
        first_time = time.time() - start_time
        print(f"First request: {response.status}, Time: {first_time:.3f}s")
    
    # Make second request (should be cached)
    start_time = time.time()
    async with session.get(f"{BASE_URL}/{endpoint}", params=params, headers=HEADERS) as response:
        second_response = await response.json()
        second_time = time.time() - start_time
        print(f"Second request: {response.status}, Time: {second_time:.3f}s")
    
    # Check if second request was faster
    speedup = first_time / second_time if second_time > 0 else float('inf')
    print(f"Cache speedup: {speedup:.2f}x")
    
    return first_response, second_response, speedup

async def test_trades_endpoint(session):
    """Test the /trades endpoint."""
    print("\n=== Testing /trades endpoint ===")
    params = {
        "page": 1,
        "page_size": 10
    }
    
    # Test cache behavior
    first, second, speedup = await test_cache_behavior(session, "trades", params)
    
    # Validate response
    if isinstance(first, list):
        print(f"Response validation: Success - Received {len(first)} trades")
    else:
        print(f"Response validation: Failed - Expected list, got {type(first)}")
    
    # Test rate limiting
    await test_endpoint_with_rate_limit(session, "trades", 120)

async def test_positions_endpoint(session):
    """Test the /positions endpoint."""
    print("\n=== Testing /positions endpoint ===")
    params = {
        "page": 1,
        "page_size": 10
    }
    
    # Test cache behavior
    first, second, speedup = await test_cache_behavior(session, "positions", params)
    
    # Validate response
    if isinstance(first, list):
        print(f"Response validation: Success - Received {len(first)} positions")
    else:
        print(f"Response validation: Failed - Expected list, got {type(first)}")
    
    # Test rate limiting
    await test_endpoint_with_rate_limit(session, "positions", 120)

async def test_pnl_endpoint(session):
    """Test the /pnl endpoint."""
    print("\n=== Testing /pnl endpoint ===")
    params = {
        "timeframe": "MONTH"
    }
    
    # Test cache behavior
    first, second, speedup = await test_cache_behavior(session, "pnl", params)
    
    # Validate response
    if isinstance(first, dict) and "metrics" in first:
        print(f"Response validation: Success - PnL metrics received")
    else:
        print(f"Response validation: Failed - Expected PnL response, got {first}")
    
    # Test rate limiting
    await test_endpoint_with_rate_limit(session, "pnl", 70)

async def test_risk_endpoint(session):
    """Test the /risk endpoint."""
    print("\n=== Testing /risk endpoint ===")
    params = {
        "timeframe": "MONTH"
    }
    
    # Test cache behavior
    first, second, speedup = await test_cache_behavior(session, "risk", params)
    
    # Validate response
    if isinstance(first, dict) and "max_drawdown" in first:
        print(f"Response validation: Success - Risk metrics received")
    else:
        print(f"Response validation: Failed - Expected risk metrics, got {first}")
    
    # Test rate limiting
    await test_endpoint_with_rate_limit(session, "risk", 70)

async def test_performance_endpoint(session):
    """Test the /performance endpoint."""
    print("\n=== Testing /performance endpoint ===")
    params = {
        "timeframe": "MONTH"
    }
    
    # Test cache behavior
    first, second, speedup = await test_cache_behavior(session, "performance", params)
    
    # Validate response
    if isinstance(first, dict) and "pnl" in first:
        print(f"Response validation: Success - Performance metrics received")
    else:
        print(f"Response validation: Failed - Expected performance metrics, got {first}")
    
    # Test rate limiting
    await test_endpoint_with_rate_limit(session, "performance", 50)

async def test_reports_endpoint(session):
    """Test the /reports endpoint."""
    print("\n=== Testing /reports endpoint ===")
    
    # Create report request
    data = {
        "report_type": "PERFORMANCE",
        "format": "JSON",
        "timeframe": "MONTH"
    }
    
    # Make report request
    async with session.post(f"{BASE_URL}/reports", json=data, headers=HEADERS) as response:
        report_response = await response.json()
        print(f"Report response: {response.status}")
        
        if response.status == 200 and "report_id" in report_response:
            print(f"Response validation: Success - Report ID: {report_response['report_id']}")
        else:
            print(f"Response validation: Failed - {report_response}")
    
    # Test rate limiting
    start_time = time.time()
    
    for i in range(15):
        async with session.post(f"{BASE_URL}/reports", json=data, headers=HEADERS) as response:
            status = response.status
            
            # Print rate limit headers
            rate_limit = response.headers.get("X-RateLimit-Limit")
            rate_remaining = response.headers.get("X-RateLimit-Remaining")
            rate_reset = response.headers.get("X-RateLimit-Reset")
            
            print(f"Request {i+1}: Status {status}, Limit: {rate_limit}, Remaining: {rate_remaining}, Reset: {rate_reset}")
            
            # If rate limited, break
            if status == 429:
                print(f"Rate limit hit after {i+1} requests")
                break
            
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.2)
    
    end_time = time.time()
    print(f"Completed in {end_time - start_time:.2f} seconds")

async def main():
    """Main test function."""
    print("=== Analytics API Test Script ===")
    print(f"API Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    
    # Create aiohttp client session
    async with aiohttp.ClientSession() as session:
        # Test endpoints
        await test_trades_endpoint(session)
        await test_positions_endpoint(session)
        await test_pnl_endpoint(session)
        await test_risk_endpoint(session)
        await test_performance_endpoint(session)
        await test_reports_endpoint(session)
    
    print("\n=== All tests completed ===")

if __name__ == "__main__":
    asyncio.run(main()) 