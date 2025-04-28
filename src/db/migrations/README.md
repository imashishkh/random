# Database Migration Guide

This guide provides comprehensive documentation for the database migration process in the Forex Trading Platform v4. It covers the migration framework, how to create and apply migrations, testing procedures, and best practices.

## Table of Contents

1. [Migration Framework Overview](#migration-framework-overview)
2. [Creating New Migrations](#creating-new-migrations)
3. [Running Migrations](#running-migrations)
4. [Rolling Back Migrations](#rolling-back-migrations)
5. [Testing Migrations](#testing-migrations)
6. [Performance Benchmarking](#performance-benchmarking)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Migration Framework Overview

The Forex Trading Platform uses [Alembic](https://alembic.sqlalchemy.org/) for database migrations. Alembic provides a structured way to manage schema changes over time, ensuring consistency across environments and enabling seamless version control of the database schema.

Key components:
- **alembic.ini**: Configuration file for the migration tool
- **env.py**: Environment configuration for Alembic
- **versions/**: Directory containing individual migration scripts
- **script.py.mako**: Template for new migration scripts

The system supports both SQL-based migrations (using raw SQL commands) and programmatic migrations (using SQLAlchemy operations). Currently, most migrations use raw SQL for maximum flexibility.

## Creating New Migrations

### Step 1: Generate a Migration Script

```bash
# Navigate to the migrations directory
cd src/db/migrations

# Create a new migration (replace "description" with a brief description of the change)
alembic revision -m "description"
```

This will create a new file in the `versions/` directory with a unique identifier and the provided description.

### Step 2: Edit the Migration Script

Each migration script contains two main functions:
- `upgrade()`: Contains the changes to apply when upgrading the database
- `downgrade()`: Contains the changes to apply when rolling back the migration

Example of a migration script:

```python
"""Add performance indexes

Revision ID: 002
Revises: 001
Create Date: 2025-04-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # Add indexes for better query performance
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_fills_symbol_timestamp 
        ON trade_fills(symbol, executed_at);
    """)
    
    # ... additional index creation statements ...

def downgrade():
    # Remove indexes in reverse order
    op.execute("DROP INDEX IF EXISTS idx_trade_fills_symbol_timestamp;")
    
    # ... additional index removal statements ...
```

### Step 3: Review the Migration

Before committing the migration, ensure:
1. The `upgrade()` function correctly implements the intended changes
2. The `downgrade()` function correctly reverses those changes
3. Both functions are idempotent (can be run multiple times without errors)
4. The migration doesn't include changes that should be in separate migrations

## Running Migrations

### Checking Migration Status

To see the current state of migrations:

```bash
cd src/db/migrations
alembic current
```

To see the history of migrations:

```bash
alembic history
```

### Applying Migrations

To apply all pending migrations:

```bash
alembic upgrade head
```

To apply migrations up to a specific version:

```bash
alembic upgrade <revision>
```

To apply a specific number of migrations:

```bash
alembic upgrade +<n>
```

### Automated Migration Script

For convenience, you can use the provided script to initialize the database and apply migrations:

```bash
python src/db/init_db.py
```

## Rolling Back Migrations

Rollbacks are crucial for recovering from failed migrations or reverting changes.

To roll back the most recent migration:

```bash
alembic downgrade -1
```

To roll back to a specific version:

```bash
alembic downgrade <revision>
```

To roll back a specific number of migrations:

```bash
alembic downgrade -<n>
```

To roll back all migrations:

```bash
alembic downgrade base
```

**Important**: Always test rollbacks before applying migrations to production!

## Testing Migrations

We provide a comprehensive testing framework for migrations in `scripts/test_migrations.py`.

### Setting Up a Test Environment

```bash
python scripts/test_migrations.py --create-test-db
```

This creates a separate test database and applies the base schema.

### Testing a Specific Migration

```bash
python scripts/test_migrations.py --verify-migration 002
```

This applies the specified migration and verifies that all expected changes were applied correctly.

### Testing Rollback

```bash
python scripts/test_migrations.py --test-rollback 002
```

This applies the migration and then tests that it can be rolled back correctly.

### Running All Tests

```bash
python scripts/test_migrations.py --run-all-tests
```

This runs a comprehensive suite of tests on all migrations, including application and rollback tests.

## Performance Benchmarking

For migrations that affect performance (like adding indexes), we provide a benchmarking tool in `scripts/benchmark_migrations.py`.

### Running Benchmarks

```bash
# Run benchmarks before applying migrations
python scripts/benchmark_migrations.py --phase=pre --output=results.json

# Apply migrations
alembic upgrade head

# Run benchmarks after applying migrations
python scripts/benchmark_migrations.py --phase=post --output=results.json

# Compare results
python scripts/benchmark_migrations.py --compare=results.json
```

This will provide detailed performance metrics showing the impact of the migrations.

## Best Practices

### Migration Design

1. **Single Responsibility**: Each migration should handle one logical change
2. **Idempotence**: Migrations should be safe to run multiple times
3. **Atomicity**: Use transactions to ensure all-or-nothing execution
4. **Backward Compatibility**: Design migrations that don't break existing code
5. **Performance**: Consider the impact of migrations on production systems

### SQL Best Practices

1. **Use IF NOT EXISTS**: Prevent errors when objects already exist
2. **Use DROP IF EXISTS**: Prevent errors when objects don't exist during rollback
3. **Use CONCURRENTLY for indexes**: Add indexes without locking tables in production
4. **Use JSONB for flexible data**: When schema flexibility is needed

### Testing Practices

1. **Test in Development First**: Always run migrations in development before staging or production
2. **Test Rollbacks**: Always verify rollbacks work correctly
3. **Benchmark Performance**: For migrations that may impact performance
4. **Test with Representative Data**: Use realistic data volumes when testing

### Production Deployment

1. **Backup First**: Always backup the database before applying migrations
2. **Maintenance Window**: Schedule migrations during low-traffic periods
3. **Monitor Locks**: Watch for long-running migrations that might lock tables
4. **Have a Rollback Plan**: Know how to rollback if issues occur

## Troubleshooting

### Common Migration Issues

1. **Missing Dependencies**: Ensure all referenced tables/columns exist
2. **Lock Timeouts**: Large migrations may cause database locks
3. **Constraint Violations**: Data may violate new constraints
4. **Version Conflicts**: Multiple developers creating migrations simultaneously

### Resolving Issues

1. **Check Alembic Logs**: Look for detailed error messages
2. **Inspect Database State**: Compare actual schema with expected schema
3. **Manual Intervention**: Sometimes direct SQL fixes are needed
4. **Fixing Failed Migrations**: Create a new migration to fix issues rather than editing existing ones

## Migration Checklist

Before submitting a migration:

- [ ] Migration applies cleanly to a current database
- [ ] Migration rolls back cleanly
- [ ] All tests pass after migration
- [ ] Performance impact is acceptable
- [ ] Documentation is updated if needed
- [ ] Migration follows best practices

---

For additional help or questions about migrations, please contact the database team. 