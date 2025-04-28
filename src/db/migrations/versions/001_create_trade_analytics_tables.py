"""Create trade analytics tables

Revision ID: 001
Revises: 
Create Date: 2025-04-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import os

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Get the schema SQL file path
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                              'trade_analytics_schema.sql')
    
    # Read the schema SQL file
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute the schema SQL
    op.execute(schema_sql)


def downgrade():
    # Drop all tables created in the schema
    op.execute("""
    DROP TABLE IF EXISTS trade_fills CASCADE;
    DROP TABLE IF EXISTS positions CASCADE;
    DROP TABLE IF EXISTS risk_alerts CASCADE;
    DROP TABLE IF EXISTS agent_states CASCADE;
    DROP TABLE IF EXISTS symbols CASCADE;
    
    DROP VIEW IF EXISTS agent_performance CASCADE;
    DROP VIEW IF EXISTS daily_pnl CASCADE;
    
    DROP FUNCTION IF EXISTS update_timestamp_column() CASCADE;
    """) 