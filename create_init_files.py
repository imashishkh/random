#!/usr/bin/env python3
"""
Script to create __init__.py files in the src directory and all subdirectories
needed for imports. This script addresses the 'No module named src.X' errors 
by ensuring all directories in import paths are proper Python packages.

After running this script, you should update imports to use relative imports
instead of absolute imports with 'src' prefix to avoid circular dependencies.

Examples:
 - Change: from src.utils.config import Settings
 - To: from .config import Settings (within utils directory)
 - Or: from ..utils.config import Settings (from another package)
"""

import os
import sys
from pathlib import Path

# List of directories that need __init__.py files based on import errors
# These paths are relative to the project root
DIRECTORIES = [
    "src",
    "src/agents",
    "src/agents/orchestration",
    "src/agents/orchestrator",
    "src/agents/risk",
    "src/agents/signal_synthesizer",
    "src/agents/health_monitoring",
    "src/agents/technical_analysis",
    "src/agents/templates",
    "src/agents/memory",
    "src/cli",
    "src/core",
    "src/core/dependencies",
    "src/core/services",
    "src/core/services/initializers",
    "src/exchange",
    "src/exchange/auth",
    "src/exchange/rate_limiting",
    "src/market_adaptation",
    "src/notifications",
    "src/risk",
    "src/risk/examples",
    "src/security",
    "src/security/secrets",
    "src/db",
    "src/analytics",
    "src/trading",
    "src/trading/exit_management",
    "src/trading/exit_management/examples",
    "src/trading/execution",
    "src/trading/execution/orders",
    "src/trading/execution/messaging",
    "src/trading/execution/validation",
    "src/trading/risk",
    "src/visualization",
    "src/visualization/dag",
    "src/reinforcement",
    "src/reinforcement/environments",
    "src/rl",
    "src/rl/training",
    "src/utils",
    "src/utils/logging",
    "src/utils/retry",
    "src/data_manager",
    "src/account",
    "src/indicators",
    "src/strategies",
    "src/pipelines",
    "src/pipelines/sentiment",
    "src/backtesting",
    "src/sentiment",
    "src/collectors",
    "src/llm",
    "src/graphs",
    "src/tools",
    "src/worker",
    "src/cache",
    "src/types",
    "src/config",
    "src/services",
    "src/api",
    "src/dashboard",
    "src/routes",
    "src/communication",
    "src/hybrid_models",
    "src/strategy_evaluation",
    "src/main",
    "tests",
    "tests/unit",
    "tests/integration",
    "tests/core",
    "tests/agents",
    "tests/exchange",
    "tests/risk",
    "tests/utils",
    "tests/trading",
    "tests/market_adaptation",
    "tests/cli",
    "tests/visualization",
    "tests/notifications",
    "tests/stress",
    "tests/stability",
    "tests/harness",
]


def main():
    """Create __init__.py files in all directories."""
    # Get the project root (parent of this script)
    script_dir = Path(__file__).resolve().parent
    
    # Track counters for file creation and existing files
    created_count = 0
    exists_count = 0
    
    print(f"Creating __init__.py files in {len(DIRECTORIES)} directories...")
    
    for directory in DIRECTORIES:
        dir_path = script_dir / directory
        init_file = dir_path / "__init__.py"
        
        # Create directory if it doesn't exist
        if not dir_path.exists():
            print(f"Creating directory: {directory}")
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py if it doesn't exist
        if not init_file.exists():
            print(f"Creating __init__.py in {directory}")
            with open(init_file, "w") as f:
                package_name = directory.split("/")[-1]
                f.write(f'"""\n{package_name.capitalize()} package.\n"""\n')
            created_count += 1
        else:
            exists_count += 1
    
    print(f"\nSummary:")
    print(f"- {created_count} __init__.py files created")
    print(f"- {exists_count} __init__.py files already existed")
    print(f"\nIMPORTANT: Now update imports to use relative imports instead of 'src' prefix.")
    print(f"For example: Change 'from src.utils.config import X' to 'from .config import X'")
    print(f"This will help prevent circular imports and make your package more portable.")


if __name__ == "__main__":
    main() 