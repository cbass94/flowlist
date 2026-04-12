# FlowList — async SQLAlchemy engine + session factory
# TODO: wire up lifespan in main.py to call init_db() on startup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """
    FastAPI dependency that yields a session for the duration of a request.
    The session owns the transaction: commits on success, rolls back on any exception.
    Routes must NOT call db.begin() — a transaction is already active (autobegin)
    by the time the first query runs (e.g. inside get_current_user).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
