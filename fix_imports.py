#!/usr/bin/env python3
"""
Script to convert absolute imports to relative imports.

This script finds all Python files in the src directory and converts 
absolute imports (from src.X import Y) to relative imports (from .X import Y 
or from ..X import Y).

Example:
    python fix_imports.py
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Regular expression to match import statements starting with 'src.'
IMPORT_REGEX = re.compile(r'^from\s+src\.(.+?)\s+import\s+(.+)$', re.MULTILINE)

def find_python_files(directory: str) -> List[Path]:
    """Find all Python files in the given directory and its subdirectories."""
    return list(Path(directory).glob('**/*.py'))

def convert_imports(file_path: Path, dry_run: bool = False) -> List[Tuple[str, str]]:
    """
    Convert absolute imports to relative imports in the given file.
    
    Args:
        file_path: Path to the Python file
        dry_run: If True, don't make any changes to the file
        
    Returns:
        A list of tuples (old_import, new_import)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Skip if no 'src.' imports
    if 'from src.' not in content:
        return []
    
    # Get file's relative path from src directory
    rel_path = file_path.relative_to(Path('src'))
    
    # Get the depth of the file from src
    depth = len(rel_path.parts) - 1  # -1 because we don't count the file itself
    
    changes = []
    
    def replacement_func(match):
        """Replace 'src.X' with appropriate relative import."""
        import_path = match.group(1)
        imported_items = match.group(2)
        
        # The new path depends on the current file's depth within src
        # and the path of the imported module
        current_module_parts = rel_path.parent.parts
        imported_module_parts = import_path.split('.')
        
        # If importing from the same package
        if imported_module_parts[0] == current_module_parts[0] if current_module_parts else False:
            # Same direct parent
            if len(imported_module_parts) == 1:
                new_import = f"from . import {imported_items}"
            else:
                new_import = f"from .{'.'.join(imported_module_parts[1:])} import {imported_items}"
        else:
            # Go up to the appropriate level and then to the target module
            dots = '.' * (depth + 1)
            new_import = f"from {dots}{import_path} import {imported_items}"
        
        # Store the change for reporting
        original = f"from src.{import_path} import {imported_items}"
        changes.append((original, new_import))
        
        return new_import
    
    # Replace all absolute imports with relative imports
    new_content = IMPORT_REGEX.sub(replacement_func, content)
    
    # Only make changes if there are differences
    if not dry_run and new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    
    return changes

def fix_imports(directory: str = 'src', dry_run: bool = False):
    """
    Fix imports in all Python files in the given directory.
    
    Args:
        directory: Path to the directory containing Python files
        dry_run: If True, don't make any changes to the files
    """
    files = find_python_files(directory)
    print(f"Found {len(files)} Python files in {directory}")
    
    files_with_changes = 0
    total_changes = 0
    
    for file_path in files:
        changes = convert_imports(file_path, dry_run)
        if changes:
            files_with_changes += 1
            total_changes += len(changes)
            print(f"\nChanges in {file_path}:")
            for old, new in changes:
                print(f"  {old} -> {new}")
    
    action = "Would change" if dry_run else "Changed"
    print(f"\n{action} imports in {files_with_changes} files ({total_changes} total changes)")
    
    if dry_run:
        print("\nThis was a dry run. Use --apply to make the changes.")

if __name__ == "__main__":
    # Parse command line arguments
    dry_run = len(sys.argv) <= 1 or sys.argv[1] != '--apply'
    
    if dry_run:
        print("Running in dry-run mode. No changes will be made.")
        print("Use --apply to make changes to the files.")
    
    fix_imports(dry_run=dry_run) 