"""
backend/app/db.py

Async SQLAlchemy engine + session factory.
Supports both PostgreSQL (production via asyncpg) and SQLite (local dev via aiosqlite).
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# docker-compose sets DATABASE_URL=postgresql+asyncpg://...
# (or the older postgresql:// form — we normalise it here)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./trakn.db",   # fallback for local dev without docker
)

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
