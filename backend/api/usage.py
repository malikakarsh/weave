"""Per-user daily rate limiting, metered per LLM call.

A "request" is one LLM call: a dashboard prompt is charged for the decompose
call plus each generated chart; a refine or insights call is charged 1. Admins
are exempt. Counts reset at UTC midnight (one `DailyUsage` row per user/day).
"""

import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from api.db import SessionLocal
from api.db_models import DailyUsage, User


def default_limit() -> int:
    """Global daily limit for users without a per-user override."""
    return int(os.getenv("DAILY_REQUEST_LIMIT", "20"))


async def effective_limit(user_id: str) -> int:
    """A user's daily limit: their override if set, else the global default."""
    async with SessionLocal() as db:
        row = await db.get(User, uuid.UUID(str(user_id)))
        if row is not None and row.daily_limit is not None:
            return row.daily_limit
    return default_limit()


def is_admin(user: dict) -> bool:
    return (user or {}).get("role") == "admin"


def _today() -> "datetime.date":
    return datetime.now(timezone.utc).date()


async def get_used(user_id: str) -> int:
    async with SessionLocal() as db:
        row = await db.get(DailyUsage, (uuid.UUID(str(user_id)), _today()))
        return row.count if row else 0


async def add_usage(user_id: str, n: int = 1) -> int:
    """Atomically add `n` to today's count (upsert) and return the new total."""
    async with SessionLocal() as db:
        stmt = (
            pg_insert(DailyUsage)
            .values(user_id=uuid.UUID(str(user_id)), day=_today(), count=n)
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={"count": DailyUsage.count + n},
            )
            .returning(DailyUsage.count)
        )
        total = (await db.execute(stmt)).scalar_one()
        await db.commit()
        return total


async def remaining(user: dict) -> int | None:
    """Requests left today, or None for admins (unlimited)."""
    if is_admin(user):
        return None
    return max(0, await effective_limit(user["uid"]) - await get_used(user["uid"]))


async def ensure_quota(user: dict) -> None:
    """Raise 429 if the user has no requests left today. Admins pass through."""
    if is_admin(user):
        return
    limit = await effective_limit(user["uid"])
    if await get_used(user["uid"]) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {limit} requests reached. Resets at midnight UTC.",
        )
