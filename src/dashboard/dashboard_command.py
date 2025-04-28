"""
Forex Trading Dashboard - Main Dashboard Command

This module implements the dashboard command for the Forex Trading system.
It provides an integrated terminal-based UI for monitoring and controlling
the trading system.
"""

import os
import sys
import time
import curses
import signal
import threading
from typing import Dict, List, Any, Optional, Tuple, Callable

from ..utils.config_manager import ConfigManager
from ..utils.logging.log_manager import get_log_manager
from ..utils.notification_manager import get_notification_manager, NotificationLevel

# Define UI constants
HEADER_HEIGHT = 3
FOOTER_HEIGHT = 2
MIN_WIDTH = 80
MIN_HEIGHT = 24

class DashboardCommand:
    """Main dashboard interface implementation."""
    
    def __init__(self):
        """Initialize the dashboard command."""
        self.config_manager = ConfigManager.get_instance()
        self.log_manager = get_log_manager()
        self.logger = self.log_manager.get_logger(__name__)
        self.notification_manager = get_notification_manager()
        
        # Dashboard configuration
        self.theme = self.config_manager.get("dashboard.theme", "auto")
        self.refresh_interval = self.config_manager.get("dashboard.refresh_interval", 5)
        
        # Dashboard state
        self.running = False
        self.current_panel = "overview"
        self.panels = {
            "overview": self._draw_overview_panel,
            "trades": self._draw_trades_panel,
            "notifications": self._draw_notifications_panel,
            "logs": self._draw_logs_panel,
            "config": self._draw_config_panel,
        }
        
        # Initialize data caches
        self.trades_cache = []
        self.notifications_cache = []
        self.logs_cache = []
        self.config_cache = {}
        
        # Thread for background data refreshing
        self.refresh_thread = None
        self.data_lock = threading.Lock()
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """
        Run the dashboard with the given arguments.
        
        Args:
            args: Command line arguments.
            
        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        # Log dashboard startup
        self.logger.info("Starting Forex Trading Dashboard")
        
        # Set up signal handling for graceful exit
        signal.signal(signal.SIGINT, self._handle_interrupt)
        
        try:
            # Initialize UI
            self.running = True
            
            # Start background data refresh thread
            self.refresh_thread = threading.Thread(target=self._background_refresh)
            self.refresh_thread.daemon = True
            self.refresh_thread.start()
            
            # Start the UI main loop
            return curses.wrapper(self._main_loop)
            
        except Exception as e:
            self.logger.error(f"Error running dashboard: {e}", exc_info=True)
            print(f"Error: {e}")
            return 1
        finally:
            self.running = False
            # Wait for background thread to finish
            if self.refresh_thread and self.refresh_thread.is_alive():
                self.refresh_thread.join(timeout=1.0)
    
    def _main_loop(self, stdscr) -> int:
        """
        Main UI loop for the dashboard.
        
        Args:
            stdscr: Standard screen from curses.
            
        Returns:
            Exit code.
        """
        # Set up colors
        self._setup_colors()
        
        # Hide cursor
        curses.curs_set(0)
        
        # Enable keypad mode
        stdscr.keypad(True)
        
        # Set timeout for getch (non-blocking)
        stdscr.timeout(100)
        
        # Initial draw
        self._draw_ui(stdscr)
        
        # Main loop
        while self.running:
            # Get input
            try:
                ch = stdscr.getch()
                
                # Handle keys
                if ch == ord('q'):
                    self.running = False
                    break
                elif ch == ord('1'):
                    self.current_panel = "overview"
                elif ch == ord('2'):
                    self.current_panel = "trades"
                elif ch == ord('3'):
                    self.current_panel = "notifications"
                elif ch == ord('4'):
                    self.current_panel = "logs"
                elif ch == ord('5'):
                    self.current_panel = "config"
                elif ch == ord('r'):
                    self._refresh_data()
                
                # Redraw UI
                self._draw_ui(stdscr)
                
            except curses.error:
                # No input, continue
                pass
            
            # Sleep a bit to reduce CPU usage
            time.sleep(0.05)
        
        return 0
    
    def _setup_colors(self):
        """Set up color pairs for the UI."""
        curses.start_color()
        curses.use_default_colors()
        
        # Basic colors
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)     # Header/footer
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)    # Selected items
        curses.init_pair(3, curses.COLOR_GREEN, -1)                    # Success/profit
        curses.init_pair(4, curses.COLOR_RED, -1)                      # Error/loss
        curses.init_pair(5, curses.COLOR_YELLOW, -1)                   # Warning
        curses.init_pair(6, curses.COLOR_CYAN, -1)                     # Info
        curses.init_pair(7, curses.COLOR_MAGENTA, -1)                  # Critical
        
        # Dark mode colors (if theme is dark)
        if self.theme == "dark" or (self.theme == "auto" and curses.COLORS >= 256):
            curses.init_pair(8, 253, 235)    # Light text on dark background
            curses.init_pair(9, 243, 235)    # Dimmed text on dark background
        else:
            # Light mode fallback
            curses.init_pair(8, curses.COLOR_BLACK, -1)  # Normal text
            curses.init_pair(9, 238, -1)                 # Dimmed text
    
    def _draw_ui(self, stdscr):
        """
        Draw the entire UI.
        
        Args:
            stdscr: Standard screen from curses.
        """
        # Get screen dimensions
        height, width = stdscr.getmaxyx()
        
        # Check for minimum size
        if height < MIN_HEIGHT or width < MIN_WIDTH:
            stdscr.clear()
            try:
                stdscr.addstr(0, 0, f"Terminal too small: {width}x{height}. Min: {MIN_WIDTH}x{MIN_HEIGHT}")
            except curses.error:
                pass  # May happen on small terminals
            stdscr.refresh()
            return
        
        # Clear screen
        stdscr.clear()
        
        # Draw header
        self._draw_header(stdscr, width)
        
        # Draw footer
        self._draw_footer(stdscr, height, width)
        
        # Calculate content area
        content_height = height - HEADER_HEIGHT - FOOTER_HEIGHT
        
        # Create content window
        content_win = curses.newwin(content_height, width, HEADER_HEIGHT, 0)
        
        # Draw content
        panel_func = self.panels.get(self.current_panel, self._draw_overview_panel)
        panel_func(content_win, content_height, width)
        
        # Refresh
        stdscr.refresh()
        content_win.refresh()
    
    def _draw_header(self, stdscr, width):
        """
        Draw the header.
        
        Args:
            stdscr: Standard screen from curses.
            width: Screen width.
        """
        # Draw header background
        stdscr.attron(curses.color_pair(1))
        for i in range(HEADER_HEIGHT):
            stdscr.addstr(i, 0, " " * (width - 1))
        
        # Draw title
        title = " Forex Trading Dashboard "
        stdscr.addstr(1, (width - len(title)) // 2, title)
        
        # Draw version
        version = f"v{self.config_manager.get('app.version', '0.1.0')}"
        stdscr.addstr(1, width - len(version) - 2, version)
        
        # Draw time
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        stdscr.addstr(1, 2, current_time)
        
        stdscr.attroff(curses.color_pair(1))
        
        # Draw tabs
        tab_y = HEADER_HEIGHT - 1
        tab_x = 2
        tabs = [
            (1, "Overview", "overview"),
            (2, "Trades", "trades"),
            (3, "Notifications", "notifications"),
            (4, "Logs", "logs"),
            (5, "Config", "config"),
        ]
        
        for key, label, panel_id in tabs:
            # Highlight current tab
            if panel_id == self.current_panel:
                stdscr.attron(curses.color_pair(2))
                tab_str = f" {key}:{label} "
            else:
                stdscr.attron(curses.color_pair(8))
                tab_str = f" {key}:{label} "
            
            # Draw tab
            stdscr.addstr(tab_y, tab_x, tab_str)
            tab_x += len(tab_str)
            
            # Reset attributes
            stdscr.attroff(curses.color_pair(2))
            stdscr.attroff(curses.color_pair(8))
    
    def _draw_footer(self, stdscr, height, width):
        """
        Draw the footer.
        
        Args:
            stdscr: Standard screen from curses.
            height: Screen height.
            width: Screen width.
        """
        # Draw footer background
        stdscr.attron(curses.color_pair(1))
        for i in range(FOOTER_HEIGHT):
            stdscr.addstr(height - FOOTER_HEIGHT + i, 0, " " * (width - 1))
        
        # Draw keyboard shortcuts
        shortcuts = "q:Quit  r:Refresh"
        stdscr.addstr(height - 2, 2, shortcuts)
        
        # Draw status
        status = "Connected"  # TODO: Get actual status
        stdscr.addstr(height - 2, width - len(status) - 2, status)
        
        stdscr.attroff(curses.color_pair(1))
    
    def _draw_overview_panel(self, win, height, width):
        """
        Draw the overview panel.
        
        Args:
            win: Window to draw on.
            height: Window height.
            width: Window width.
        """
        win.box()
        win.addstr(0, 2, " Overview ")
        
        # Draw system status
        win.addstr(2, 2, "System Status")
        win.addstr(3, 4, "Status: ", curses.color_pair(8))
        win.addstr(3, 13, "Running", curses.color_pair(3))
        
        # Draw performance summary
        win.addstr(5, 2, "Performance Summary")
        win.addstr(6, 4, "Total Profit: ", curses.color_pair(8))
        win.addstr(6, 18, "$0.00", curses.color_pair(3))
        win.addstr(7, 4, "Open Trades: ", curses.color_pair(8))
        win.addstr(7, 17, "0")
        win.addstr(8, 4, "Success Rate: ", curses.color_pair(8))
        win.addstr(8, 18, "0.0%")
        
        # Draw recent activity
        win.addstr(10, 2, "Recent Activity")
        win.addstr(11, 4, "No recent activity", curses.color_pair(9))
        
        # Draw notifications
        win.addstr(13, 2, "Recent Notifications")
        with self.data_lock:
            if self.notifications_cache:
                for i, notification in enumerate(self.notifications_cache[:3]):
                    level_color = {
                        NotificationLevel.DEBUG: curses.color_pair(6),
                        NotificationLevel.INFO: curses.color_pair(6),
                        NotificationLevel.WARNING: curses.color_pair(5),
                        NotificationLevel.ERROR: curses.color_pair(4),
                        NotificationLevel.CRITICAL: curses.color_pair(7),
                    }.get(notification.level, curses.color_pair(8))
                    
                    timestamp = notification.timestamp.strftime("%H:%M:%S")
                    win.addstr(14 + i, 4, f"{timestamp} ", curses.color_pair(9))
                    win.addstr(14 + i, 13, f"{notification.level.name}: {notification.title}", level_color)
            else:
                win.addstr(14, 4, "No notifications", curses.color_pair(9))
    
    def _draw_trades_panel(self, win, height, width):
        """
        Draw the trades panel.
        
        Args:
            win: Window to draw on.
            height: Window height.
            width: Window width.
        """
        win.box()
        win.addstr(0, 2, " Trades ")
        
        # Draw column headers
        win.addstr(2, 2, "ID", curses.color_pair(8))
        win.addstr(2, 8, "Pair", curses.color_pair(8))
        win.addstr(2, 15, "Direction", curses.color_pair(8))
        win.addstr(2, 28, "Open Price", curses.color_pair(8))
        win.addstr(2, 42, "Current", curses.color_pair(8))
        win.addstr(2, 54, "P/L", curses.color_pair(8))
        win.addstr(2, 62, "Open Time", curses.color_pair(8))
        
        # Draw separator
        for x in range(2, width - 2):
            win.addch(3, x, curses.ACS_HLINE)
        
        # Draw trades
        with self.data_lock:
            if self.trades_cache:
                for i, trade in enumerate(self.trades_cache[:height-6]):
                    y = 4 + i
                    
                    # Mock data for display purposes
                    trade_id = f"T{trade.get('id', i+1)}"
                    pair = trade.get('pair', 'EUR/USD')
                    direction = trade.get('direction', 'BUY')
                    open_price = trade.get('open_price', '1.0000')
                    current_price = trade.get('current_price', '1.0010')
                    
                    # Calculate profit/loss (mocked)
                    pl = float(current_price) - float(open_price)
                    if direction == 'SELL':
                        pl *= -1
                    pl_str = f"{pl:.4f}"
                    
                    # Format time
                    open_time = trade.get('open_time', time.strftime("%Y-%m-%d %H:%M"))
                    
                    # Display trade
                    win.addstr(y, 2, trade_id)
                    win.addstr(y, 8, pair)
                    
                    # Color direction
                    if direction == 'BUY':
                        win.addstr(y, 15, direction, curses.color_pair(3))
                    else:
                        win.addstr(y, 15, direction, curses.color_pair(4))
                    
                    win.addstr(y, 28, open_price)
                    win.addstr(y, 42, current_price)
                    
                    # Color P/L
                    if pl > 0:
                        win.addstr(y, 54, pl_str, curses.color_pair(3))
                    elif pl < 0:
                        win.addstr(y, 54, pl_str, curses.color_pair(4))
                    else:
                        win.addstr(y, 54, pl_str)
                    
                    win.addstr(y, 62, open_time)
            else:
                win.addstr(4, 2, "No active trades", curses.color_pair(9))
        
        # Draw legend
        win.addstr(height - 2, 2, "Shortcuts: ", curses.color_pair(8))
        win.addstr(height - 2, 13, "o", curses.color_pair(6))
        win.addstr(height - 2, 14, ":Open  ")
        win.addstr(height - 2, 22, "c", curses.color_pair(6))
        win.addstr(height - 2, 23, ":Close  ")
        win.addstr(height - 2, 32, "d", curses.color_pair(6))
        win.addstr(height - 2, 33, ":Details")
    
    def _draw_notifications_panel(self, win, height, width):
        """
        Draw the notifications panel.
        
        Args:
            win: Window to draw on.
            height: Window height.
            width: Window width.
        """
        win.box()
        win.addstr(0, 2, " Notifications ")
        
        # Draw column headers
        win.addstr(2, 2, "Time", curses.color_pair(8))
        win.addstr(2, 12, "Level", curses.color_pair(8))
        win.addstr(2, 22, "Title", curses.color_pair(8))
        win.addstr(2, 52, "Ack", curses.color_pair(8))
        
        # Draw separator
        for x in range(2, width - 2):
            win.addch(3, x, curses.ACS_HLINE)
        
        # Draw notifications
        with self.data_lock:
            if self.notifications_cache:
                for i, notification in enumerate(self.notifications_cache[:height-6]):
                    y = 4 + i
                    
                    # Get notification details
                    timestamp = notification.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    level = notification.level.name
                    title = notification.title
                    ack = "✓" if notification.is_acknowledged else " "
                    
                    # Choose color based on level
                    level_color = {
                        NotificationLevel.DEBUG: curses.color_pair(6),
                        NotificationLevel.INFO: curses.color_pair(6),
                        NotificationLevel.WARNING: curses.color_pair(5),
                        NotificationLevel.ERROR: curses.color_pair(4),
                        NotificationLevel.CRITICAL: curses.color_pair(7),
                    }.get(notification.level, curses.color_pair(8))
                    
                    # Display notification
                    win.addstr(y, 2, timestamp[:10])
                    win.addstr(y, 12, level, level_color)
                    
                    # Truncate title if too long
                    if len(title) > 29:
                        title = title[:26] + "..."
                        
                    win.addstr(y, 22, title)
                    win.addstr(y, 52, ack)
            else:
                win.addstr(4, 2, "No notifications", curses.color_pair(9))
        
        # Draw legend
        win.addstr(height - 2, 2, "Shortcuts: ", curses.color_pair(8))
        win.addstr(height - 2, 13, "a", curses.color_pair(6))
        win.addstr(height - 2, 14, ":Acknowledge  ")
        win.addstr(height - 2, 29, "d", curses.color_pair(6))
        win.addstr(height - 2, 30, ":Details  ")
        win.addstr(height - 2, 41, "c", curses.color_pair(6))
        win.addstr(height - 2, 42, ":Clear All")
    
    def _draw_logs_panel(self, win, height, width):
        """
        Draw the logs panel.
        
        Args:
            win: Window to draw on.
            height: Window height.
            width: Window width.
        """
        win.box()
        win.addstr(0, 2, " Logs ")
        
        # Draw column headers
        win.addstr(2, 2, "Time", curses.color_pair(8))
        win.addstr(2, 12, "Level", curses.color_pair(8))
        win.addstr(2, 22, "Logger", curses.color_pair(8))
        win.addstr(2, 35, "Message", curses.color_pair(8))
        
        # Draw separator
        for x in range(2, width - 2):
            win.addch(3, x, curses.ACS_HLINE)
        
        # Draw logs
        with self.data_lock:
            if self.logs_cache:
                for i, log in enumerate(self.logs_cache[:height-6]):
                    y = 4 + i
                    
                    # Get log details
                    timestamp = log.get('timestamp', '')
                    level = log.get('level', 'INFO')
                    logger = log.get('logger', '')
                    message = log.get('message', '')
                    
                    # Choose color based on level
                    level_color = {
                        'DEBUG': curses.color_pair(6),
                        'INFO': curses.color_pair(8),
                        'WARNING': curses.color_pair(5),
                        'ERROR': curses.color_pair(4),
                        'CRITICAL': curses.color_pair(7),
                    }.get(level, curses.color_pair(8))
                    
                    # Display log
                    win.addstr(y, 2, timestamp[:10])
                    win.addstr(y, 12, level, level_color)
                    
                    # Truncate logger if too long
                    if len(logger) > 12:
                        logger = logger[:9] + "..."
                    win.addstr(y, 22, logger)
                    
                    # Truncate message if too long
                    max_msg_len = width - 37
                    if len(message) > max_msg_len:
                        message = message[:max_msg_len-3] + "..."
                    win.addstr(y, 35, message)
            else:
                win.addstr(4, 2, "No logs", curses.color_pair(9))
        
        # Draw legend
        win.addstr(height - 2, 2, "Shortcuts: ", curses.color_pair(8))
        win.addstr(height - 2, 13, "f", curses.color_pair(6))
        win.addstr(height - 2, 14, ":Filter  ")
        win.addstr(height - 2, 24, "e", curses.color_pair(6))
        win.addstr(height - 2, 25, ":Export  ")
        win.addstr(height - 2, 35, "c", curses.color_pair(6))
        win.addstr(height - 2, 36, ":Clear Display")
    
    def _draw_config_panel(self, win, height, width):
        """
        Draw the configuration panel.
        
        Args:
            win: Window to draw on.
            height: Window height.
            width: Window width.
        """
        win.box()
        win.addstr(0, 2, " Configuration ")
        
        # Draw column headers
        win.addstr(2, 2, "Section", curses.color_pair(8))
        win.addstr(2, 20, "Key", curses.color_pair(8))
        win.addstr(2, 35, "Value", curses.color_pair(8))
        win.addstr(2, 55, "Type", curses.color_pair(8))
        
        # Draw separator
        for x in range(2, width - 2):
            win.addch(3, x, curses.ACS_HLINE)
        
        # Draw configuration
        with self.data_lock:
            if self.config_cache:
                y = 4
                for section, keys in sorted(self.config_cache.items()):
                    for key, value in sorted(keys.items()):
                        if y >= height - 3:
                            break
                        
                        # Only show the key part (not the section)
                        display_key = key
                        
                        # Determine value type
                        if isinstance(value, bool):
                            value_type = "boolean"
                            display_value = str(value).lower()
                        elif isinstance(value, int):
                            value_type = "integer"
                            display_value = str(value)
                        elif isinstance(value, float):
                            value_type = "float" 
                            display_value = str(value)
                        elif isinstance(value, str):
                            value_type = "string"
                            display_value = value
                        elif value is None:
                            value_type = "null"
                            display_value = "null"
                        else:
                            value_type = type(value).__name__
                            display_value = str(value)
                        
                        # Truncate displays if too long
                        if len(display_key) > 14:
                            display_key = display_key[:11] + "..."
                        
                        if len(display_value) > 19:
                            display_value = display_value[:16] + "..."
                        
                        # Display config item
                        win.addstr(y, 2, section)
                        win.addstr(y, 20, display_key)
                        win.addstr(y, 35, display_value)
                        win.addstr(y, 55, value_type)
                        
                        y += 1
            else:
                win.addstr(4, 2, "No configuration settings", curses.color_pair(9))
        
        # Draw legend
        win.addstr(height - 2, 2, "Shortcuts: ", curses.color_pair(8))
        win.addstr(height - 2, 13, "e", curses.color_pair(6))
        win.addstr(height - 2, 14, ":Edit  ")
        win.addstr(height - 2, 22, "f", curses.color_pair(6))
        win.addstr(height - 2, 23, ":Filter  ")
        win.addstr(height - 2, 32, "i", curses.color_pair(6))
        win.addstr(height - 2, 33, ":Import  ")
        win.addstr(height - 2, 43, "x", curses.color_pair(6))
        win.addstr(height - 2, 44, ":Export")
    
    def _background_refresh(self):
        """Background thread function for refreshing data."""
        while self.running:
            try:
                self._refresh_data()
                
                # Sleep for the refresh interval
                time.sleep(self.refresh_interval)
                
            except Exception as e:
                self.logger.error(f"Error in background refresh: {e}", exc_info=True)
    
    def _refresh_data(self):
        """Refresh all data from sources."""
        try:
            with self.data_lock:
                # Refresh notifications
                self.notifications_cache = self.notification_manager.get_notifications(limit=50)
                
                # Refresh logs
                # TODO: Implement log retrieval
                self.logs_cache = []
                
                # Refresh trades
                # TODO: Implement trade retrieval
                self.trades_cache = [
                    # Mock trade data for display purposes
                    {"id": 1, "pair": "EUR/USD", "direction": "BUY", "open_price": "1.0800", 
                     "current_price": "1.0821", "open_time": "2023-08-09 14:32"},
                    {"id": 2, "pair": "GBP/JPY", "direction": "SELL", "open_price": "155.50", 
                     "current_price": "155.32", "open_time": "2023-08-09 15:45"},
                ]
                
                # Refresh configuration
                raw_config = self.config_manager.get_all()
                # Organize by sections
                self.config_cache = {}
                for key, value in raw_config.items():
                    if "." in key:
                        section, key_name = key.split(".", 1)
                        if section not in self.config_cache:
                            self.config_cache[section] = {}
                        self.config_cache[section][key_name] = value
                    else:
                        if "general" not in self.config_cache:
                            self.config_cache["general"] = {}
                        self.config_cache["general"][key] = value
        
        except Exception as e:
            self.logger.error(f"Error refreshing data: {e}", exc_info=True)
            self.notification_manager.notify_error(
                title="Dashboard Data Refresh Error",
                message=f"Failed to refresh dashboard data: {e}",
                source="dashboard"
            )
    
    def _handle_interrupt(self, signum, frame):
        """
        Handle SIGINT signal.
        
        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        self.running = False
        

def run_dashboard(args: Optional[List[str]] = None) -> int:
    """
    Run the dashboard command.
    
    Args:
        args: Command line arguments.
        
    Returns:
        Exit code.
    """
    dashboard = DashboardCommand()
    return dashboard.run(args)


if __name__ == "__main__":
    sys.exit(run_dashboard()) 