"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

The app talks to Postgres over asyncpg. Endpoints get a request-scoped
`AsyncSession` via `Depends(get_db)`; Alembic owns schema migrations.
"""

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://weave:weave@localhost:5432/weave"
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models; Alembic reads Base.metadata."""


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
