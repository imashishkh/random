#!/usr/bin/env python3
"""
Comprehensive health check script for Airflow
This script verifies all critical components of Airflow are functioning properly.
It can be used both as a standalone script and as part of a container health check.
"""

import os
import sys
import time
import socket
import requests
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

# Configuration
WEBSERVER_URL = os.environ.get('AIRFLOW__WEBSERVER__BASE_URL', 'http://localhost:8080')
DB_CONN = os.environ.get('AIRFLOW__DATABASE__SQL_ALCHEMY_CONN', 'postgresql+psycopg2://airflow:airflow@postgres:5432/airflow')
BROKER_URL = os.environ.get('AIRFLOW__CELERY__BROKER_URL', 'redis://redis:6379/1')
HEALTH_ENDPOINT = '/health'

def check_webserver():
    """Check if Airflow webserver is responding"""
    try:
        response = requests.get(f"{WEBSERVER_URL}{HEALTH_ENDPOINT}", timeout=5)
        if response.status_code != 200:
            print(f"Webserver returned non-200 status code: {response.status_code}")
            return False
        
        # Optionally check JSON response content
        try:
            data = response.json()
            if data.get('status') != 'healthy':
                print(f"Webserver reports unhealthy status: {data}")
                return False
        except Exception as e:
            print(f"Failed to parse webserver response: {e}")
            return False
            
        return True
    except requests.RequestException as e:
        print(f"Failed to connect to Airflow webserver: {e}")
        return False

def check_database():
    """Check if Airflow database is accessible and has expected tables"""
    try:
        engine = create_engine(DB_CONN)
        conn = engine.connect()
        
        # Check if we can execute a query
        result = conn.execute(text("SELECT 1"))
        if next(result)[0] != 1:
            print("Database query returned unexpected result")
            return False
            
        # Check if essential Airflow tables exist
        tables_result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('dag', 'dag_run', 'task_instance')"
        ))
        tables = [row[0] for row in tables_result]
        
        missing_tables = set(['dag', 'dag_run', 'task_instance']) - set(tables)
        if missing_tables:
            print(f"Missing essential Airflow tables: {missing_tables}")
            return False
            
        conn.close()
        return True
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return False

def check_broker():
    """Check if message broker (Redis) is accessible"""
    try:
        # Parse the broker URL
        parsed_url = urlparse(BROKER_URL)
        
        if parsed_url.scheme == 'redis':
            # For Redis, check socket connection
            host = parsed_url.hostname or 'localhost'
            port = parsed_url.port or 6379
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result != 0:
                print(f"Failed to connect to Redis broker at {host}:{port}")
                return False
                
            return True
        else:
            # For other broker types, would need specific checks
            print(f"Broker scheme {parsed_url.scheme} not supported for health check")
            # Return True by default to not fail on unsupported broker types
            return True
    except Exception as e:
        print(f"Failed to check broker connection: {e}")
        return False

def main():
    """Main health check function"""
    print("Starting Airflow health check...")
    
    # Add a small delay to allow connections to stabilize
    time.sleep(1)
    
    webserver_ok = check_webserver()
    database_ok = check_database()
    broker_ok = check_broker()
    
    print(f"Health check results: Webserver: {'✅' if webserver_ok else '❌'}, "
          f"Database: {'✅' if database_ok else '❌'}, "
          f"Broker: {'✅' if broker_ok else '❌'}")
    
    # All components must be healthy
    if webserver_ok and database_ok and broker_ok:
        print("Airflow health check passed!")
        return 0
    else:
        print("Airflow health check failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 