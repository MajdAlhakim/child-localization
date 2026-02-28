"""Database initialisation — called on application startup."""
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.app.db.models import Base
from backend.app.db.session import engine


async def init_db(bind: AsyncEngine | None = None) -> None:
    """Create all tables if they do not exist.

    Args:
        bind: optional engine override (used in tests to pass in-memory engine).
    """
    target = bind or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(bind: AsyncEngine | None = None) -> None:
    """Drop all tables (test teardown only)."""
    target = bind or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
