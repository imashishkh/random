#!/usr/bin/env python3
"""
Database Migration Benchmarking Tool

This script measures query performance before and after applying migrations.
It runs a series of representative queries with EXPLAIN ANALYZE and compares
execution times and query plans to verify performance improvements.

Usage:
    python benchmark_migrations.py --phase=[pre|post] --output=results.json
    python benchmark_migrations.py --compare=results.json

Example workflow:
    1. Run with --phase=pre before applying migrations
    2. Apply migrations (alembic upgrade head)
    3. Run with --phase=post and same output file
    4. Run with --compare to see performance comparison
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("benchmark_migrations")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "forex")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Define benchmark queries
BENCHMARK_QUERIES = {
    "trade_fills_symbol_timestamp": """
        EXPLAIN ANALYZE
        SELECT * FROM trade_fills
        WHERE symbol = 'EUR/USD'
        ORDER BY executed_at DESC
        LIMIT 100;
    """,
    
    "trade_fills_agent_id": """
        EXPLAIN ANALYZE
        SELECT * FROM trade_fills
        WHERE agent_id = '12345678-1234-1234-1234-123456789012'
        LIMIT 100;
    """,
    
    "positions_agent_id_status": """
        EXPLAIN ANALYZE
        SELECT * FROM positions
        WHERE agent_id = '12345678-1234-1234-1234-123456789012'
        AND status = 'OPEN';
    """,
    
    "positions_symbol_status": """
        EXPLAIN ANALYZE
        SELECT * FROM positions
        WHERE symbol = 'EUR/USD'
        AND status = 'OPEN';
    """,
    
    "risk_alerts_agent_id_resolved": """
        EXPLAIN ANALYZE
        SELECT * FROM risk_alerts
        WHERE agent_id = '12345678-1234-1234-1234-123456789012'
        AND resolved = FALSE
        ORDER BY triggered_at DESC;
    """,
    
    "agent_states_agent_id": """
        EXPLAIN ANALYZE
        SELECT * FROM agent_states
        WHERE agent_id = '12345678-1234-1234-1234-123456789012';
    """
}


def get_db_connection():
    """Create a database connection."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return None


def run_query_benchmark(query_name: str, query: str) -> Dict[str, Any]:
    """
    Run a query with EXPLAIN ANALYZE and extract performance metrics.
    
    Args:
        query_name: Name of the query for reporting
        query: SQL query with EXPLAIN ANALYZE
        
    Returns:
        Dictionary with performance metrics
    """
    results = {
        "query_name": query_name,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "execution_time_ms": None,
        "plan_rows": None,
        "planning_time_ms": None,
        "buffers_hit": None,
        "buffers_read": None,
        "scan_method": None,
        "raw_plan": None
    }
    
    conn = get_db_connection()
    if not conn:
        results["error"] = "Failed to connect to database"
        return results
    
    try:
        with conn.cursor() as cursor:
            start_time = time.time()
            cursor.execute(query)
            query_results = cursor.fetchall()
            end_time = time.time()
            
            # Calculate total time without EXPLAIN ANALYZE overhead
            total_time = (end_time - start_time) * 1000  # ms
            
            # Extract metrics from EXPLAIN ANALYZE output
            raw_plan = "\n".join(str(row) for row in query_results)
            results["raw_plan"] = raw_plan
            
            # Parse execution time from the last line of explain output
            for row in reversed(query_results):
                if "Execution Time" in str(row):
                    execution_time = str(row).split(": ")[1].split(" ms")[0]
                    results["execution_time_ms"] = float(execution_time)
                    break
            
            # Parse planning time
            for row in query_results:
                if "Planning Time" in str(row):
                    planning_time = str(row).split(": ")[1].split(" ms")[0]
                    results["planning_time_ms"] = float(planning_time)
                    break
            
            # Determine scan method (Index Scan, Seq Scan, etc.)
            for row in query_results:
                row_str = str(row)
                if "Seq Scan" in row_str:
                    results["scan_method"] = "Sequential Scan"
                    break
                elif "Index Scan" in row_str:
                    results["scan_method"] = "Index Scan"
                    break
                elif "Index Only Scan" in row_str:
                    results["scan_method"] = "Index Only Scan"
                    break
            
            # Extract buffers information if available
            for row in query_results:
                row_str = str(row)
                if "Buffers: shared hit=" in row_str:
                    hit_part = row_str.split("hit=")[1].split(" ")[0]
                    results["buffers_hit"] = int(hit_part)
                if "read=" in row_str:
                    read_part = row_str.split("read=")[1].split(" ")[0]
                    results["buffers_read"] = int(read_part)
            
            results["success"] = True
            
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Error running benchmark for {query_name}: {e}")
    finally:
        conn.close()
    
    return results


def run_all_benchmarks() -> Dict[str, Any]:
    """
    Run all benchmark queries and collect results.
    
    Returns:
        Dictionary with results for all queries
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "queries": {}
    }
    
    for name, query in BENCHMARK_QUERIES.items():
        logger.info(f"Running benchmark for {name}...")
        query_result = run_query_benchmark(name, query)
        results["queries"][name] = query_result
        
        if query_result["success"]:
            logger.info(f"  Execution time: {query_result.get('execution_time_ms')} ms")
            logger.info(f"  Scan method: {query_result.get('scan_method')}")
        else:
            logger.error(f"  Benchmark failed: {query_result.get('error')}")
    
    return results


def compare_results(pre_results: Dict[str, Any], post_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare pre-migration and post-migration benchmark results.
    
    Args:
        pre_results: Benchmark results before migration
        post_results: Benchmark results after migration
        
    Returns:
        Dictionary with comparison metrics
    """
    comparison = {
        "summary": {
            "total_queries": len(BENCHMARK_QUERIES),
            "improved_queries": 0,
            "degraded_queries": 0,
            "unchanged_queries": 0,
            "failed_queries": 0,
            "avg_improvement_pct": 0
        },
        "queries": {}
    }
    
    total_pct_change = 0
    valid_comparisons = 0
    
    for query_name in BENCHMARK_QUERIES.keys():
        pre_query = pre_results.get("queries", {}).get(query_name, {})
        post_query = post_results.get("queries", {}).get(query_name, {})
        
        query_comparison = {
            "name": query_name,
            "pre_migration": {
                "execution_time_ms": pre_query.get("execution_time_ms"),
                "scan_method": pre_query.get("scan_method"),
                "buffers_hit": pre_query.get("buffers_hit"),
                "buffers_read": pre_query.get("buffers_read")
            },
            "post_migration": {
                "execution_time_ms": post_query.get("execution_time_ms"),
                "scan_method": post_query.get("scan_method"),
                "buffers_hit": post_query.get("buffers_hit"),
                "buffers_read": post_query.get("buffers_read")
            }
        }
        
        pre_time = pre_query.get("execution_time_ms")
        post_time = post_query.get("execution_time_ms")
        
        # Skip failed queries
        if not pre_query.get("success") or not post_query.get("success"):
            query_comparison["status"] = "FAILED"
            comparison["summary"]["failed_queries"] += 1
        elif pre_time is None or post_time is None:
            query_comparison["status"] = "INCOMPLETE"
            comparison["summary"]["failed_queries"] += 1
        else:
            time_diff = pre_time - post_time
            pct_change = (time_diff / pre_time) * 100 if pre_time > 0 else 0
            
            query_comparison["time_diff_ms"] = time_diff
            query_comparison["percent_change"] = pct_change
            
            # Determine if performance improved
            improved = pct_change > 5  # Consider >5% improvement significant
            degraded = pct_change < -5  # Consider >5% degradation significant
            
            if improved:
                query_comparison["status"] = "IMPROVED"
                comparison["summary"]["improved_queries"] += 1
            elif degraded:
                query_comparison["status"] = "DEGRADED"
                comparison["summary"]["degraded_queries"] += 1
            else:
                query_comparison["status"] = "UNCHANGED"
                comparison["summary"]["unchanged_queries"] += 1
            
            # Add to average calculation
            total_pct_change += pct_change
            valid_comparisons += 1
            
            # Check for scan method changes
            if pre_query.get("scan_method") != post_query.get("scan_method"):
                query_comparison["scan_method_changed"] = True
                query_comparison["scan_improvement"] = (
                    pre_query.get("scan_method") == "Sequential Scan" and 
                    post_query.get("scan_method") in ["Index Scan", "Index Only Scan"]
                )
        
        comparison["queries"][query_name] = query_comparison
    
    # Calculate overall metrics
    if valid_comparisons > 0:
        comparison["summary"]["avg_improvement_pct"] = total_pct_change / valid_comparisons
    
    return comparison


def save_results(results: Dict[str, Any], output_file: str, phase: str):
    """
    Save benchmark results to a JSON file.
    
    Args:
        results: Benchmark results
        output_file: Path to output file
        phase: Benchmark phase ('pre' or 'post')
    """
    # Load existing file if it exists
    existing_data = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse existing file {output_file}, will overwrite")
    
    # Update with new results
    existing_data[phase] = results
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(existing_data, f, indent=2)
        
    logger.info(f"Results saved to {output_file}")


def load_results(input_file: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load benchmark results from a JSON file.
    
    Args:
        input_file: Path to input file
        
    Returns:
        Tuple of (pre_results, post_results)
    """
    if not os.path.exists(input_file):
        logger.error(f"File {input_file} does not exist")
        return None, None
    
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        pre_results = data.get("pre")
        post_results = data.get("post")
        
        if not pre_results:
            logger.error("No pre-migration results found in file")
        if not post_results:
            logger.error("No post-migration results found in file")
            
        return pre_results, post_results
    except Exception as e:
        logger.error(f"Error loading results: {e}")
        return None, None


def print_comparison(comparison: Dict[str, Any]):
    """
    Print benchmark comparison results in a readable format.
    
    Args:
        comparison: Comparison results
    """
    summary = comparison["summary"]
    queries = comparison["queries"]
    
    print("\n" + "=" * 80)
    print(f"MIGRATION PERFORMANCE BENCHMARK COMPARISON")
    print("=" * 80)
    
    print(f"\nSummary:")
    print(f"  Total queries:     {summary['total_queries']}")
    print(f"  Improved queries:  {summary['improved_queries']}")
    print(f"  Degraded queries:  {summary['degraded_queries']}")
    print(f"  Unchanged queries: {summary['unchanged_queries']}")
    print(f"  Failed queries:    {summary['failed_queries']}")
    print(f"  Avg improvement:   {summary['avg_improvement_pct']:.2f}%")
    
    print("\nDetailed Results:")
    for name, query in queries.items():
        print(f"\n  {name}:")
        print(f"    Status: {query.get('status', 'UNKNOWN')}")
        
        pre_time = query.get('pre_migration', {}).get('execution_time_ms')
        post_time = query.get('post_migration', {}).get('execution_time_ms')
        
        if pre_time is not None and post_time is not None:
            print(f"    Execution time: {pre_time:.2f}ms -> {post_time:.2f}ms")
            
            if 'percent_change' in query:
                print(f"    Change: {query['percent_change']:.2f}%")
            
            pre_scan = query.get('pre_migration', {}).get('scan_method')
            post_scan = query.get('post_migration', {}).get('scan_method')
            if pre_scan != post_scan:
                print(f"    Scan method: {pre_scan} -> {post_scan}")
    
    print("\n" + "=" * 80)
    
    # Provide recommendations
    print("\nRecommendations:")
    if summary['degraded_queries'] > 0:
        print("  - Review degraded queries for potential index issues")
    if summary['failed_queries'] > 0:
        print("  - Investigate failed benchmark queries")
    if summary['avg_improvement_pct'] < 10:
        print("  - Consider additional indexing strategies for better performance")
    else:
        print("  - Migration successfully improved query performance")
    
    print("\n" + "=" * 80)


def main():
    """Main function to run benchmarks or compare results."""
    parser = argparse.ArgumentParser(description="Database migration benchmark tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phase", choices=["pre", "post"], 
                       help="Benchmark phase (pre or post migration)")
    group.add_argument("--compare", metavar="FILE", 
                      help="Compare pre and post results from FILE")
    
    parser.add_argument("--output", default="benchmark_results.json",
                       help="Output file for benchmark results")
    
    args = parser.parse_args()
    
    if args.phase:
        # Run benchmarks and save results
        logger.info(f"Running {args.phase}-migration benchmarks...")
        results = run_all_benchmarks()
        save_results(results, args.output, args.phase)
        logger.info(f"{args.phase.capitalize()}-migration benchmarks completed")
    
    elif args.compare:
        # Load and compare results
        logger.info(f"Comparing benchmark results from {args.compare}...")
        pre_results, post_results = load_results(args.compare)
        
        if pre_results and post_results:
            comparison = compare_results(pre_results, post_results)
            print_comparison(comparison)
            
            # Save comparison to file
            comparison_file = f"{os.path.splitext(args.compare)[0]}_comparison.json"
            with open(comparison_file, 'w') as f:
                json.dump(comparison, f, indent=2)
            logger.info(f"Comparison saved to {comparison_file}")
        else:
            logger.error("Cannot compare results: missing pre or post data")


if __name__ == "__main__":
    main() 