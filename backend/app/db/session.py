"""Async SQLAlchemy database session management."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

import os


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _get_engine():
    settings = get_settings()
    # Ensure data directory exists for SQLite
    if "sqlite" in settings.database_url:
        db_path = settings.database_url.split("///")[-1]
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    return create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
    )


engine = _get_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all tables. Called on application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose engine. Called on application shutdown."""
    await engine.dispose()
