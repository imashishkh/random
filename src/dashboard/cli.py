#!/usr/bin/env python
"""
Forex Trading Dashboard CLI

This module serves as the main entry point for the CLI dashboard, providing
command-line interfaces for various components of the Forex Trading system.
"""
import argparse
import os
import sys
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from .dashboard import run_dashboard
from ..account.manager import WalletManager, AccountManager
from ..account.models import WalletType
from ..utils.config_manager import ConfigManager
from ..utils.logging.log_manager import get_log_manager, LogManager
from ..utils.notification_manager import (
    get_notification_manager, 
    NotificationManager,
    NotificationLevel
)
from .cli_config import config_command, log_command

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args(args: List[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Forex Trading Dashboard CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch the trading dashboard")
    
    # Wallet management commands
    wallet_parser = subparsers.add_parser("wallet", help="Wallet management commands")
    wallet_subparsers = wallet_parser.add_subparsers(dest="wallet_command", help="Wallet command to run")
    
    # List wallets
    list_parser = wallet_subparsers.add_parser("list", help="List all wallets for a user")
    list_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    
    # Create wallet
    create_parser = wallet_subparsers.add_parser("create", help="Create a new wallet")
    create_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    create_parser.add_argument("--name", "-n", required=True, help="Wallet name")
    create_parser.add_argument("--type", "-t", choices=[t.value for t in WalletType], 
                             default="hot", help="Wallet type")
    create_parser.add_argument("--password", "-p", help="Password for hot wallets")
    
    # Get wallet details
    get_parser = wallet_subparsers.add_parser("get", help="Get wallet details")
    get_parser.add_argument("--wallet-id", "-i", required=True, type=int, help="Wallet ID")
    
    # Get wallet transactions
    transactions_parser = wallet_subparsers.add_parser("transactions", help="Get wallet transactions")
    transactions_parser.add_argument("--wallet-id", "-i", required=True, type=int, help="Wallet ID")
    transactions_parser.add_argument("--days", "-d", type=int, default=7, help="Number of days to fetch")
    transactions_parser.add_argument("--type", "-t", help="Transaction type filter")
    transactions_parser.add_argument("--limit", "-l", type=int, default=50, help="Maximum number of transactions")
    
    # Security check
    security_parser = wallet_subparsers.add_parser("security", help="Check for suspicious activity")
    security_parser.add_argument("--wallet-id", "-i", required=True, type=int, help="Wallet ID")
    
    # Balance history
    history_parser = wallet_subparsers.add_parser("history", help="Get balance history")
    history_parser.add_argument("--wallet-id", "-i", required=True, type=int, help="Wallet ID")
    history_parser.add_argument("--period", "-p", choices=["day", "week", "month", "year"], 
                             default="week", help="Time period")
    history_parser.add_argument("--asset", "-a", help="Asset filter")
    
    # Fund allocation
    allocation_parser = wallet_subparsers.add_parser("allocation", help="Get fund allocation")
    allocation_parser.add_argument("--wallet-id", "-i", required=True, type=int, help="Wallet ID")
    
    return parser.parse_args(args)

def handle_wallet_command(args: argparse.Namespace) -> int:
    """Handle wallet management commands."""
    try:
        wallet_manager = WalletManager()
        
        if args.wallet_command == "list":
            wallets = wallet_manager.get_user_wallets(args.user_id)
            print(f"Found {len(wallets)} wallets for user {args.user_id}:")
            
            for i, wallet in enumerate(wallets):
                wallet_id = wallet.get("id", f"Unknown-{i}")
                name = wallet.get("name", "Unnamed Wallet")
                wallet_type = wallet.get("wallet_type", "unknown")
                address = wallet.get("address", "No address")
                
                # Calculate total balance
                balances = wallet.get("balances", {})
                total_balance = sum(balances.values())
                
                print(f"\nWallet {wallet_id}: {name}")
                print(f"  Type: {wallet_type}")
                print(f"  Address: {address}")
                print(f"  Total Balance: ${total_balance:.2f}")
                
                if balances:
                    print("  Assets:")
                    for asset, value in balances.items():
                        print(f"    {asset}: {value}")
            
            return 0
            
        elif args.wallet_command == "create":
            from src.account.wallet import create_wallet
            
            # Validate password for hot wallets
            if args.type == "hot" and not args.password:
                print("Error: Password is required for hot wallets")
                return 1
            
            # Create wallet
            wallet_type = WalletType(args.type)
            wallet = create_wallet(
                user_id=args.user_id,
                wallet_type=wallet_type,
                password=args.password,
                name=args.name
            )
            
            print(f"Wallet created successfully:")
            print(f"  ID: {wallet.id}")
            print(f"  Name: {wallet.name}")
            print(f"  Type: {wallet.wallet_type}")
            print(f"  Address: {wallet.address}")
            
            return 0
            
        elif args.wallet_command == "get":
            wallet_data = wallet_manager.get_wallet(args.wallet_id)
            
            print(f"Wallet {args.wallet_id}:")
            print(f"  Name: {wallet_data.get('name', 'Unnamed Wallet')}")
            print(f"  Type: {wallet_data.get('wallet_type', 'unknown')}")
            print(f"  Address: {wallet_data.get('address', 'No address')}")
            print(f"  Created: {wallet_data.get('created_at', 'Unknown')}")
            
            balances = wallet_data.get("balances", {})
            if balances:
                print("\nBalances:")
                for asset, amount in balances.items():
                    print(f"  {asset}: {amount}")
            
            print(f"\nLast updated: {wallet_data.get('last_updated', 'Unknown')}")
            
            return 0
            
        elif args.wallet_command == "transactions":
            # Calculate date range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=args.days)
            
            transactions = wallet_manager.get_wallet_transactions(
                wallet_id=args.wallet_id,
                start_time=start_time,
                end_time=end_time,
                transaction_type=args.type,
                limit=args.limit
            )
            
            print(f"Found {len(transactions)} transactions for wallet {args.wallet_id}:")
            
            for tx in transactions:
                tx_id = tx.get("transaction_id", "Unknown ID")
                tx_type = tx.get("transaction_type", "Unknown type")
                asset = tx.get("asset", "Unknown asset")
                amount = tx.get("amount", 0)
                timestamp = tx.get("timestamp", "Unknown time")
                status = tx.get("status", "Unknown status")
                
                if isinstance(timestamp, datetime):
                    time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    time_str = str(timestamp)
                
                print(f"\nTransaction: {tx_id}")
                print(f"  Type: {tx_type}")
                print(f"  Asset: {asset}")
                print(f"  Amount: {amount}")
                print(f"  Time: {time_str}")
                print(f"  Status: {status}")
            
            return 0
            
        elif args.wallet_command == "security":
            alerts = wallet_manager.detect_suspicious_activity(args.wallet_id)
            
            if alerts:
                print(f"Found {len(alerts)} suspicious activities for wallet {args.wallet_id}:")
                
                for alert in alerts:
                    alert_type = alert.get("type", "unknown")
                    severity = alert.get("severity", "low")
                    description = alert.get("description", "No description")
                    
                    print(f"\n[{severity.upper()}] {alert_type}")
                    print(f"  {description}")
                    
                    # Print additional details
                    if "timestamp" in alert:
                        time_str = alert["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(alert["timestamp"], datetime) else alert["timestamp"]
                        print(f"  Time: {time_str}")
                    elif "date" in alert:
                        print(f"  Date: {alert['date']}")
                    
                    if "transaction_id" in alert:
                        print(f"  Transaction: {alert['transaction_id']}")
                    
                    if "failed_transactions" in alert:
                        print(f"  Failed transactions: {', '.join(alert['failed_transactions'])}")
            else:
                print(f"No suspicious activities detected for wallet {args.wallet_id}")
            
            return 0
            
        elif args.wallet_command == "history":
            history = wallet_manager.get_wallet_balance_history(
                wallet_id=args.wallet_id,
                period=args.period,
                asset=args.asset
            )
            
            if history:
                print(f"Balance history for wallet {args.wallet_id} ({args.period}):")
                
                asset_label = args.asset if args.asset else "Total"
                print(f"\nShowing balance history for: {asset_label}")
                
                # Print in reverse chronological order (newest first)
                for point in sorted(history, key=lambda x: x.get("timestamp"), reverse=True):
                    timestamp = point.get("timestamp")
                    balance = point.get("balance", 0)
                    
                    if isinstance(timestamp, datetime):
                        time_str = timestamp.strftime("%Y-%m-%d %H:%M")
                    else:
                        time_str = str(timestamp)
                    
                    print(f"  {time_str}: {balance:.6f}")
            else:
                print(f"No balance history data found for wallet {args.wallet_id}")
            
            return 0
            
        elif args.wallet_command == "allocation":
            allocation = wallet_manager.get_fund_allocation(args.wallet_id)
            
            if allocation:
                print(f"Fund allocation for wallet {args.wallet_id}:")
                
                # Sort by percentage (descending)
                sorted_allocation = sorted(allocation.items(), key=lambda x: x[1], reverse=True)
                
                for asset, percentage in sorted_allocation:
                    print(f"  {asset}: {percentage:.2f}%")
            else:
                print(f"No allocation data found for wallet {args.wallet_id}")
            
            return 0
            
        else:
            print(f"Unknown wallet command: {args.wallet_command}")
            return 1
            
    except Exception as e:
        print(f"Error executing wallet command: {str(e)}")
        logger.error(f"Error in wallet command: {str(e)}", exc_info=True)
        return 1

class CLI:
    """Main CLI interface for the Forex Trading Dashboard."""
    
    def __init__(self):
        """Initialize the CLI with required managers."""
        # Initialize managers
        self.config_manager = ConfigManager.get_instance()
        self.log_manager = get_log_manager()
        self.logger = self.log_manager.get_logger(__name__)
        self.notification_manager = get_notification_manager()
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """
        Run the CLI with the given arguments.
        
        Args:
            args: Command line arguments.
            
        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        # Create main parser
        parser = argparse.ArgumentParser(
            description="Forex Trading Dashboard CLI",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  forex-dash config list            List all configuration sections
  forex-dash config get app.name    Get a specific configuration value
  forex-dash config set app.debug true --type boolean  Set a configuration value
  forex-dash log get --level ERROR  Get all error logs
  forex-dash trade list             List active trades
"""
        )
        
        # Add version argument
        parser.add_argument(
            '--version', '-v', 
            action='version', 
            version=f'Forex Trading Dashboard {self.config_manager.get("app.version", "0.1.0")}'
        )
        
        # Create subparsers for commands
        subparsers = parser.add_subparsers(dest="command", help="Command to run")
        
        # Config command
        config_parser = subparsers.add_parser(
            "config", 
            help="Manage configuration"
        )
        
        # Log command
        log_parser = subparsers.add_parser(
            "log", 
            help="Manage logs"
        )
        
        # Dashboard command
        dashboard_parser = subparsers.add_parser(
            "dashboard", 
            help="Launch interactive dashboard"
        )
        dashboard_parser.add_argument(
            "--theme", 
            choices=["light", "dark", "auto"], 
            help="Dashboard theme"
        )
        dashboard_parser.add_argument(
            "--refresh", 
            type=int, 
            help="Refresh interval in seconds"
        )
        
        # Trading commands
        trade_parser = subparsers.add_parser(
            "trade", 
            help="Trading commands"
        )
        trade_subparsers = trade_parser.add_subparsers(
            dest="trade_command",
            help="Trading subcommands"
        )
        
        # Trade list command
        trade_list_parser = trade_subparsers.add_parser(
            "list", 
            help="List active trades"
        )
        trade_list_parser.add_argument(
            "--all", 
            action="store_true", 
            help="Include closed trades"
        )
        
        # Notifications command
        notification_parser = subparsers.add_parser(
            "notify", 
            help="Manage notifications"
        )
        notification_subparsers = notification_parser.add_subparsers(
            dest="notification_command",
            help="Notification subcommands"
        )
        
        # Notification list command
        notification_list_parser = notification_subparsers.add_parser(
            "list", 
            help="List notifications"
        )
        notification_list_parser.add_argument(
            "--unacked", 
            action="store_true", 
            help="Show only unacknowledged notifications"
        )
        notification_list_parser.add_argument(
            "--level", 
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            help="Filter by notification level"
        )
        
        # Notification acknowledge command
        notification_ack_parser = notification_subparsers.add_parser(
            "ack", 
            help="Acknowledge notifications"
        )
        notification_ack_parser.add_argument(
            "id", 
            nargs="?", 
            help="Notification ID to acknowledge (or 'all')"
        )
        
        # Parse arguments
        parsed_args = parser.parse_args(args)
        
        # Log the command being executed
        if args:
            self.logger.info(f"CLI command executed: {' '.join(args)}")
        
        # If no command is provided, show help
        if not parsed_args.command:
            parser.print_help()
            return 1
        
        try:
            # Dispatch to appropriate command handler
            if parsed_args.command == "config":
                # Remove the 'config' argument and pass the rest to the config command
                config_args = args[1:] if args and args[0] == "config" else []
                return config_command(config_args)
                
            elif parsed_args.command == "log":
                # Remove the 'log' argument and pass the rest to the log command
                log_args = args[1:] if args and args[0] == "log" else []
                return log_command(log_args)
                
            elif parsed_args.command == "dashboard":
                return self._handle_dashboard(parsed_args)
                
            elif parsed_args.command == "trade":
                return self._handle_trade(parsed_args)
                
            elif parsed_args.command == "notify":
                return self._handle_notification(parsed_args)
                
            else:
                print(f"Unknown command: {parsed_args.command}")
                return 1
                
        except Exception as e:
            self.logger.error(f"Error executing command: {e}", exc_info=True)
            self.notification_manager.notify_error(
                title="Command Error",
                message=f"Error executing command: {e}",
                source="cli"
            )
            print(f"Error: {e}")
            return 1
    
    def _handle_dashboard(self, args: argparse.Namespace) -> int:
        """
        Handle the 'dashboard' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        # TODO: Implement dashboard launching
        print("Interactive dashboard not yet implemented")
        
        # Apply theme if specified
        if args.theme:
            self.config_manager.set("dashboard.theme", args.theme)
            self.config_manager.save()
            print(f"Dashboard theme set to: {args.theme}")
        
        # Apply refresh interval if specified
        if args.refresh:
            self.config_manager.set("dashboard.refresh_interval", args.refresh)
            self.config_manager.save()
            print(f"Dashboard refresh interval set to: {args.refresh} seconds")
        
        # This is a placeholder for when the dashboard is implemented
        self.notification_manager.notify_info(
            title="Dashboard Requested",
            message="Dashboard launch was requested but is not yet implemented",
            source="cli"
        )
        
        return 0
    
    def _handle_trade(self, args: argparse.Namespace) -> int:
        """
        Handle the 'trade' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        if not args.trade_command:
            print("Missing trade subcommand. Use 'list' or other available commands.")
            return 1
        
        if args.trade_command == "list":
            # TODO: Implement trade listing
            print("Trade listing not yet implemented")
            
            # This is a placeholder for when the trade list is implemented
            include_closed = args.all
            closed_text = "including closed trades" if include_closed else "active trades only"
            print(f"Would list trades ({closed_text})")
            
            self.notification_manager.notify_info(
                title="Trade List Requested",
                message=f"Trade listing was requested ({closed_text}) but is not yet implemented",
                source="cli"
            )
            
            return 0
        
        else:
            print(f"Unknown trade command: {args.trade_command}")
            return 1
    
    def _handle_notification(self, args: argparse.Namespace) -> int:
        """
        Handle the 'notify' command.
        
        Args:
            args: Parsed arguments.
            
        Returns:
            Exit code.
        """
        if not args.notification_command:
            print("Missing notification subcommand. Use 'list' or 'ack'.")
            return 1
        
        if args.notification_command == "list":
            # Filter by level if specified
            level = None
            if args.level:
                try:
                    level = NotificationLevel[args.level]
                except KeyError:
                    print(f"Invalid notification level: {args.level}")
                    return 1
            
            # Get notifications
            notifications = self.notification_manager.get_notifications(
                unacknowledged_only=args.unacked,
                level=level
            )
            
            if not notifications:
                print("No notifications found")
                return 0
            
            # Print notifications
            print("\nNotifications:")
            print(f"{'-'*80}")
            
            for i, notification in enumerate(notifications):
                # Get notification details
                notification_id = notification.id
                title = notification.title
                message = notification.message
                level = notification.level.name
                timestamp = notification.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                acknowledged = "Yes" if notification.is_acknowledged else "No"
                
                # Color mapping
                level_colors = {
                    "DEBUG": "\033[36m",    # Cyan
                    "INFO": "\033[32m",     # Green
                    "WARNING": "\033[33m",  # Yellow
                    "ERROR": "\033[31m",    # Red
                    "CRITICAL": "\033[35m"  # Magenta
                }
                
                reset_color = "\033[0m"
                level_color = level_colors.get(level, "\033[0m")
                
                # Print notification
                print(f"{i+1}. [{notification_id}] {level_color}{level}{reset_color}: {title}")
                print(f"   Time: {timestamp}  Acknowledged: {acknowledged}")
                print(f"   {message}")
                print()
            
            return 0
            
        elif args.notification_command == "ack":
            if not args.id:
                print("Please specify a notification ID or 'all'")
                return 1
            
            if args.id.lower() == "all":
                # Acknowledge all notifications
                count = self.notification_manager.acknowledge_all()
                print(f"Acknowledged {count} notifications")
                return 0
            
            else:
                # Acknowledge a specific notification
                try:
                    notification_id = args.id
                    success = self.notification_manager.acknowledge_notification(notification_id)
                    
                    if success:
                        print(f"Acknowledged notification: {notification_id}")
                        return 0
                    else:
                        print(f"Failed to acknowledge notification: {notification_id}")
                        return 1
                        
                except Exception as e:
                    print(f"Error acknowledging notification: {e}")
                    return 1
        
        else:
            print(f"Unknown notification command: {args.notification_command}")
            return 1

def main() -> int:
    """Main entry point for the CLI."""
    # Create CLI instance
    cli = CLI()
    
    try:
        # Run CLI with command-line arguments
        return cli.run(sys.argv[1:])
    except Exception as e:
        print(f"Unhandled error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 