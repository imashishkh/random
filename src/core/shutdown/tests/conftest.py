"""
Configuration file for pytest for the shutdown module tests.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO if os.environ.get('DEBUG') else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Reset the ShutdownCoordinator singleton before and after each test session
def pytest_sessionstart(session):
    """
    Reset the ShutdownCoordinator singleton before starting tests.
    """
    from src.core.shutdown.coordinator import ShutdownCoordinator
    ShutdownCoordinator._instance = None


def pytest_sessionfinish(session, exitstatus):
    """
    Reset the ShutdownCoordinator singleton after tests are complete.
    """
    from src.core.shutdown.coordinator import ShutdownCoordinator
    ShutdownCoordinator._instance = None


# Configure event loop policy for Windows if needed
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) 