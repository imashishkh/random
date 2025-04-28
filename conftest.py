"""
conftest.py - Configuration file for pytest

This file provides setup for pytest to properly handle imports in the project.
It automatically adds the src directory to the Python path to allow tests to
import from the src package.
"""

import os
import sys
from pathlib import Path

# Add the root directory to the Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Add src directory to the Python path 
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir)) 