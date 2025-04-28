# Python Import Guidelines for Forex Trading Project

## Best Practices for Avoiding Circular Imports

This guide outlines the best practices for organizing imports in the Forex Trading project to prevent circular dependencies.

### Using Relative Imports

When importing from modules within the same package, use relative imports:

```python
# ✅ DO: Within src/utils/ directory, import from other utils modules
from .config import Settings
from .patterns import Singleton

# ❌ DON'T: Use absolute imports with 'src' prefix within the same package
from src.utils.config import Settings  # Avoid this
```

For imports from parent or sibling packages, use relative imports with dots:

```python
# ✅ DO: From src/risk/fixed_amount.py, import from risk/base.py
from .base import PositionSizer

# ✅ DO: From src/strategies/integration.py, import from risk package
from ..risk.base import PositionSizingResult
```

### Structuring Your Imports

1. **Group imports logically**:
   ```python
   # Standard library
   import os
   import sys
   from typing import Dict, List, Optional
   
   # Third-party libraries
   import numpy as np
   import pandas as pd
   
   # Local application imports
   from .base import BaseClass
   from ..utils.helpers import format_date
   ```

2. **Avoid cyclic dependencies**:
   - If two modules need to import from each other, consider:
     - Moving shared code to a third module
     - Using lazy imports (import inside function)
     - Using type hints with string literals

### Lazy Imports

If imports cause circular dependencies, consider lazy importing (inside functions):

```python
def get_risk_manager():
    """Get a risk manager instance.
    
    Uses lazy import to avoid circular dependencies.
    """
    from ..risk.manager import RiskManager
    return RiskManager()
```

### Using Type Hints Without Imports

For circular references in type hints, use string literals or TYPE_CHECKING:

```python
from typing import TYPE_CHECKING, List, Dict

if TYPE_CHECKING:
    from ..risk.manager import RiskManager

def process_risk(data: Dict[str, float]) -> "RiskManager":
    # Implementation
    ...
```

### Common Circular Import Patterns to Avoid

1. **Mutual Imports**: Module A imports from B, and B imports from A
2. **Triangular Imports**: A imports B, B imports C, and C imports A
3. **Long Cycles**: A → B → C → D → ... → A

### How to Fix Circular Imports

1. **Identify the cycle** using import error messages or static analysis tools
2. **Refactor the code**:
   - Create a new module for shared functionality
   - Use dependency injection instead of imports
   - Move imports inside functions (lazy imports)
   - Use string literals for type annotations
3. **Test thoroughly** after making changes

### Testing for Import Issues

Run tests with warnings enabled to detect circular imports:

```bash
PYTHONPATH=src pytest -v tests/ -W error::ImportWarning
```

The project's `pytest.ini` is configured to raise errors for import warnings.

## Troubleshooting Import Errors

### "No module named 'src.X'" Error

1. Ensure the module exists in the correct location
2. Check if `__init__.py` exists in all parent directories
3. Set PYTHONPATH correctly: `export PYTHONPATH=src`
4. Use relative imports instead of `src.X` prefix

### "ImportError: cannot import name 'X'" Error

1. Check for circular dependencies
2. Try moving the import inside a function
3. Consider if the imported name actually exists in that module

## Advanced Import Techniques

### Package Structure Optimization

Organize related functionality into coherent packages:

```
src/
├── core/          # Core system components
├── data_manager/  # Data handling and processing
├── risk/          # Risk management
├── strategies/    # Trading strategies
└── utils/         # General utilities
```

### Refactoring for Better Dependencies

1. **Dependency Inversion**: Depend on abstractions, not concretions
2. **Interface Segregation**: Prefer small, specific interfaces
3. **Single Responsibility**: Each module should have one reason to change

Remember: Good import practices lead to a more maintainable, testable codebase! 