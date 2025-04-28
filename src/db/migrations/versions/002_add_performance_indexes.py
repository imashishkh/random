"""Add performance indexes for query optimization

Revision ID: 002
Revises: 001
Create Date: 2025-04-23

This migration adds performance-optimized indexes to improve query performance
for common database operations. Each index targets specific query patterns
identified during performance analysis.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add performance indexes to key tables.
    
    The indexes created in this migration target the following query patterns:
    - Queries filtering trades by symbol and timestamp
    - Queries filtering trades by agent ID
    - Queries filtering positions by agent ID and status
    - Queries filtering positions by symbol and status
    - Queries filtering risk alerts by agent ID and resolution status
    - Queries retrieving agent state by agent ID
    """
    # Create composite index for TradeFill(symbol, timestamp)
    # This improves queries that filter by symbol and order by timestamp
    # Note: We check if the existing idx_trade_fills_symbol_executed_at meets our needs
    # If not, we create a new index with the desired column ordering
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_trade_fills_symbol_timestamp'
            ) THEN
                CREATE INDEX idx_trade_fills_symbol_timestamp 
                ON trade_fills(symbol, executed_at);
            END IF;
        END
        $$;
    """)
    
    # Create index for TradeFill(agent_id) if it doesn't exist
    # This improves queries that filter trades by agent
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_trade_fills_agent_id'
            ) THEN
                CREATE INDEX idx_trade_fills_agent_id 
                ON trade_fills(agent_id);
            END IF;
        END
        $$;
    """)
    
    # Create composite index for Position(agent_id, status)
    # This improves queries that filter positions by agent and status
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_positions_agent_id_status'
            ) THEN
                CREATE INDEX idx_positions_agent_id_status 
                ON positions(agent_id, status);
            END IF;
        END
        $$;
    """)
    
    # Create composite index for Position(symbol, status)
    # This improves queries that filter positions by symbol and status
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_positions_symbol_status'
            ) THEN
                CREATE INDEX idx_positions_symbol_status 
                ON positions(symbol, status);
            END IF;
        END
        $$;
    """)
    
    # Create composite index for RiskAlert(agent_id, resolved)
    # This improves queries that filter risk alerts by agent and resolution status
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_risk_alerts_agent_id_resolved'
            ) THEN
                CREATE INDEX idx_risk_alerts_agent_id_resolved 
                ON risk_alerts(agent_id, resolved);
            END IF;
        END
        $$;
    """)
    
    # Create index for AgentState(agent_id)
    # This improves queries that look up agent state by ID
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_agent_states_agent_id'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'agent_states' AND column_name = 'agent_id'
            ) THEN
                CREATE INDEX idx_agent_states_agent_id 
                ON agent_states(agent_id);
            END IF;
        END
        $$;
    """)


def downgrade():
    """
    Remove all indexes created in this migration.
    
    This function drops each index in reverse order to cleanly revert
    the upgrade. Each DROP statement is wrapped in a conditional check
    to ensure idempotence.
    """
    # Drop AgentState(agent_id) index
    op.execute("""
        DROP INDEX IF EXISTS idx_agent_states_agent_id;
    """)
    
    # Drop RiskAlert(agent_id, resolved) index
    op.execute("""
        DROP INDEX IF EXISTS idx_risk_alerts_agent_id_resolved;
    """)
    
    # Drop Position(symbol, status) index
    op.execute("""
        DROP INDEX IF EXISTS idx_positions_symbol_status;
    """)
    
    # Drop Position(agent_id, status) index
    op.execute("""
        DROP INDEX IF EXISTS idx_positions_agent_id_status;
    """)
    
    # Drop TradeFill(agent_id) index
    op.execute("""
        DROP INDEX IF EXISTS idx_trade_fills_agent_id;
    """)
    
    # Drop TradeFill(symbol, timestamp) index
    op.execute("""
        DROP INDEX IF EXISTS idx_trade_fills_symbol_timestamp;
    """) 