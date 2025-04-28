#!/usr/bin/env python3
"""
Trading Performance Analytics Dashboard Example

This script demonstrates how to use the trading performance analytics module to
create a comprehensive trading dashboard with performance metrics and visualizations.
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
import traceback

# Add the parent directory to the path to import the analytics module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Script started")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Path: {sys.path}")

try:
    from analytics import TradingPerformanceAnalytics
    print("Successfully imported analytics module")
except Exception as e:
    print(f"Error importing analytics module: {str(e)}")
    traceback.print_exc()
    sys.exit(1)


def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Trading Performance Dashboard")
    
    # Data source options
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--mock", action="store_true", help="Use mock data")
    source_group.add_argument("--file", type=str, help="Path to trade data file (JSON/CSV)")
    source_group.add_argument("--api", type=str, help="API URL for trade data")
    
    # Mock data options
    parser.add_argument("--num-trades", type=int, default=100, help="Number of mock trades to generate")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols")
    
    # Time period options
    parser.add_argument("--period", type=str, default="all_time", 
                      choices=[
                          "today", "yesterday", "this_week", "last_week",
                          "this_month", "last_month", "this_year", "last_year",
                          "last_7_days", "last_30_days", "last_90_days", "all_time"
                      ],
                      help="Time period to analyze")
    
    # Filter options
    parser.add_argument("--filter-symbol", type=str, help="Filter by symbol")
    parser.add_argument("--filter-strategy", type=str, help="Filter by strategy")
    parser.add_argument("--filter-direction", type=str, choices=["BUY", "SELL"], help="Filter by direction")
    parser.add_argument("--min-pnl", type=float, help="Filter by minimum P&L")
    parser.add_argument("--max-pnl", type=float, help="Filter by maximum P&L")
    
    # Visualization options
    parser.add_argument("--view", type=str, default="dashboard",
                      choices=["dashboard", "summary", "pnl", "trades", "symbols", "risk"],
                      help="Type of visualization to display")
    parser.add_argument("--pnl-period", type=str, default="daily",
                      choices=["daily", "weekly", "monthly", "yearly"],
                      help="Time aggregation for P&L chart")
    
    return parser.parse_args()


def main():
    """Main function"""
    # Set up logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Parse arguments
    args = parse_arguments()
    
    # Initialize analytics
    try:
        if args.mock:
            logger.info("Using mock data generator")
            symbols = args.symbols.split(",") if args.symbols else None
            analytics = TradingPerformanceAnalytics(
                "mock", 
                num_trades=args.num_trades,
                symbols=symbols
            )
        elif args.file:
            logger.info(f"Loading data from file: {args.file}")
            analytics = TradingPerformanceAnalytics("file", file_path=args.file)
        elif args.api:
            logger.info(f"Loading data from API: {args.api}")
            analytics = TradingPerformanceAnalytics("api", api_url=args.api)
        else:
            logger.error("No data source specified")
            return 1
    except Exception as e:
        logger.error(f"Error initializing analytics: {str(e)}")
        return 1
    
    # Prepare filters
    filters = {}
    if args.filter_symbol:
        filters["symbols"] = [args.filter_symbol]
    if args.filter_strategy:
        filters["strategies"] = [args.filter_strategy]
    if args.filter_direction:
        from analytics import TradeDirection
        filters["directions"] = [getattr(TradeDirection, args.filter_direction)]
    if args.min_pnl is not None:
        filters["min_pnl"] = args.min_pnl
    if args.max_pnl is not None:
        filters["max_pnl"] = args.max_pnl
    
    # Display the appropriate view
    try:
        if args.view == "dashboard":
            analytics.display_dashboard(args.period, **filters)
        elif args.view == "summary":
            analytics.display_summary(args.period, **filters)
        elif args.view == "pnl":
            analytics.display_pnl_chart(args.period, period=args.pnl_period, **filters)
        elif args.view == "trades":
            analytics.display_trade_table(args.period, **filters)
        elif args.view == "symbols":
            analytics.display_symbol_performance(args.period, **filters)
        elif args.view == "risk":
            analytics.display_risk_metrics(args.period, **filters)
    except Exception as e:
        logger.error(f"Error displaying analytics: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 