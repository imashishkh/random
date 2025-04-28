"""
Alembic migration environment configuration.

This file configures how migrations are run in the project.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path so models can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# This is the Alembic Config object, which provides access to the values within the .ini file
config = context.config

# Override the sqlalchemy.url from the alembic.ini file with the DATABASE_URL environment variable
sqlalchemy_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/forex')
config.set_main_option('sqlalchemy.url', sqlalchemy_url)

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Import SQLAlchemy models here - whenever you create a new model, make sure to import it here
# This is where you would typically import your SQLAlchemy models to generate migrations
# from src.models import Base  # Replace with your actual Base import

# Currently this project uses raw SQL schema and doesn't have an ORM,
# so we'll create an empty metadata object for alembic's use
from sqlalchemy import MetaData
target_metadata = MetaData()

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online() 