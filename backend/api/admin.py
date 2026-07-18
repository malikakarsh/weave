"""Admin-only endpoints: a read-only view of users and their activity.

Guarded by `require_admin` (403 for non-admins). Aggregates the per-day
`daily_usage` rows into total and today's LLM-call counts per user.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_admin
from api.db import get_db
from api.db_models import DailyUsage, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every user with their visit count and LLM usage (total + today)."""
    today = datetime.now(timezone.utc).date()
    total = func.coalesce(func.sum(DailyUsage.count), 0)
    today_sum = func.coalesce(
        func.sum(DailyUsage.count).filter(DailyUsage.day == today), 0
    )
    rows = (
        await db.execute(
            select(User, total.label("total"), today_sum.label("today"))
            .outerjoin(DailyUsage, DailyUsage.user_id == User.id)
            .group_by(User.id)
            .order_by(User.last_seen_at.desc().nulls_last())
        )
    ).all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "role": u.role,
            "visits": u.visits,
            "total_usage": int(total_usage),
            "today_usage": int(today_usage),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
        }
        for u, total_usage, today_usage in rows
    ]


@router.get("/stats")
async def stats(
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Headline totals for the dashboard."""
    today = datetime.now(timezone.utc).date()
    user_count = (await db.execute(select(func.count(User.id)))).scalar_one()
    calls_total = (await db.execute(select(func.coalesce(func.sum(DailyUsage.count), 0)))).scalar_one()
    calls_today = (
        await db.execute(
            select(func.coalesce(func.sum(DailyUsage.count), 0)).where(DailyUsage.day == today)
        )
    ).scalar_one()
    return {
        "users": int(user_count),
        "calls_total": int(calls_total),
        "calls_today": int(calls_today),
    }
