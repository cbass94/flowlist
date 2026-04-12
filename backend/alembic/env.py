import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so their metadata is registered on Base before autogenerate
from app.database import Base
from app.models import (  # noqa: F401
    AIEstimationLog,
    CalendarBlock,
    SchedulingRunLog,
    Task,
    User,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_async_url() -> str:
    """Return the asyncpg DATABASE_URL for online migrations."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url  # already postgresql+asyncpg:// from docker-compose


def get_sync_url() -> str:
    """Return a psycopg2 URL for offline migrations."""
    return get_async_url().replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Override sqlalchemy.url directly from the environment rather than reading
    # it from alembic.ini. configparser interpolation chokes on a DATABASE_URL
    # that contains percent signs (e.g. URL-encoded passwords like %23, %40).
    config.set_main_option("sqlalchemy.url", get_async_url())
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
