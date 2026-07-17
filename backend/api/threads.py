"""User-scoped thread persistence.

A *thread* is one CSV-upload workspace (Claude-style): a title, the CSV, and the
charts generated from it. Everything here is scoped to the signed-in user — a
thread is only ever visible to its owner. The frontend saves the full set of
charts for a thread whenever it changes (small N), so we replace-on-save.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import current_user_required
from api.db import get_db
from api.db_models import Chart, Thread

router = APIRouter(prefix="/threads", tags=["threads"])


# ── schemas ───────────────────────────────────────────────────────────────
class ThreadCreate(BaseModel):
    title: str
    csv_name: str
    csv_content: str


class ChartIn(BaseModel):
    sub_prompt: str = ""
    mapping: dict | None = None
    html: str | None = None
    history: list | None = None
    position: int = 0


class ChartOut(ChartIn):
    id: uuid.UUID


class ThreadSummary(BaseModel):
    id: uuid.UUID
    title: str
    chart_count: int
    updated_at: str


class ThreadDetail(BaseModel):
    id: uuid.UUID
    title: str
    csv_name: str
    csv_content: str
    charts: list[ChartOut]
    updated_at: str


async def _owned_thread(thread_id: uuid.UUID, user: dict, db: AsyncSession) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None or str(thread.user_id) != user["uid"]:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


def _uid(user: dict) -> uuid.UUID:
    # 'uid' is our User row UUID (minted into the JWT); DB rows key on it.
    return uuid.UUID(user["uid"])


# ── routes ────────────────────────────────────────────────────────────────
@router.post("", response_model=ThreadDetail)
async def create_thread(
    body: ThreadCreate,
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    thread = Thread(
        user_id=_uid(user), title=body.title[:512] or "Untitled",
        csv_name=body.csv_name[:512], csv_content=body.csv_content,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return _detail(thread, [])


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    counts = (
        select(Chart.thread_id, func.count(Chart.id).label("n"))
        .group_by(Chart.thread_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Thread, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.thread_id == Thread.id)
            .where(Thread.user_id == _uid(user))
            .order_by(Thread.updated_at.desc())
        )
    ).all()
    return [
        ThreadSummary(id=t.id, title=t.title, chart_count=int(n),
                      updated_at=t.updated_at.isoformat())
        for t, n in rows
    ]


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    thread = await _owned_thread(thread_id, user, db)
    charts = (
        await db.execute(
            select(Chart).where(Chart.thread_id == thread_id).order_by(Chart.position)
        )
    ).scalars().all()
    return _detail(thread, charts)


@router.put("/{thread_id}/charts", response_model=ThreadDetail)
async def save_charts(
    thread_id: uuid.UUID,
    charts: list[ChartIn],
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Replace the thread's charts with the given set (frontend sends the full
    list on every change). Touches the thread so it sorts to the top."""
    thread = await _owned_thread(thread_id, user, db)
    await db.execute(delete(Chart).where(Chart.thread_id == thread_id))
    for i, c in enumerate(charts):
        db.add(Chart(
            user_id=thread.user_id, thread_id=thread_id,
            sub_prompt=c.sub_prompt, mapping=c.mapping, html=c.html,
            history=c.history, position=c.position or i,
        ))
    await db.execute(update(Thread).where(Thread.id == thread_id).values(updated_at=func.now()))
    await db.commit()
    saved = (
        await db.execute(
            select(Chart).where(Chart.thread_id == thread_id).order_by(Chart.position)
        )
    ).scalars().all()
    await db.refresh(thread)
    return _detail(thread, saved)


@router.patch("/{thread_id}", response_model=ThreadSummary)
async def rename_thread(
    thread_id: uuid.UUID,
    body: dict,
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    thread = await _owned_thread(thread_id, user, db)
    thread.title = str(body.get("title", thread.title))[:512] or "Untitled"
    await db.commit()
    n = (
        await db.execute(select(func.count(Chart.id)).where(Chart.thread_id == thread_id))
    ).scalar_one()
    return ThreadSummary(id=thread.id, title=thread.title, chart_count=int(n),
                         updated_at=thread.updated_at.isoformat())


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: uuid.UUID,
    user: dict = Depends(current_user_required),
    db: AsyncSession = Depends(get_db),
):
    thread = await _owned_thread(thread_id, user, db)
    await db.delete(thread)  # cascades to charts
    await db.commit()
    return {"ok": True}


def _detail(thread: Thread, charts: list[Chart]) -> ThreadDetail:
    return ThreadDetail(
        id=thread.id, title=thread.title, csv_name=thread.csv_name,
        csv_content=thread.csv_content, updated_at=thread.updated_at.isoformat(),
        charts=[
            ChartOut(id=c.id, sub_prompt=c.sub_prompt, mapping=c.mapping,
                     html=c.html, history=c.history, position=c.position)
            for c in charts
        ],
    )
