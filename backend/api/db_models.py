"""ORM models for user-scoped session persistence.

A user works in **threads** (Claude-style): each thread is one CSV-upload
workspace with a title, the CSV, and the charts generated from it. Every chart
keeps its own refine conversation history. Mappings and history are JSONB so
they round-trip without a rigid column schema. `DailyUsage` meters LLM calls
per user per day for rate limiting.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


def _uuid_col():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_col()
    # Google's stable subject identifier — the join key from the JWT.
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(Text)
    # "admin" (unlimited, full access) or "user" (rate limited). Derived from
    # ADMIN_EMAILS at login, not user-editable.
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    threads: Mapped[list["Thread"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    charts: Mapped[list["Chart"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))         # shown in the sidebar
    csv_name: Mapped[str] = mapped_column(String(512))      # original filename
    csv_content: Mapped[str] = mapped_column(Text)          # raw CSV text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="threads")
    charts: Mapped[list["Chart"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan",
        order_by="Chart.position",
    )


class Chart(Base):
    __tablename__ = "charts"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    sub_prompt: Mapped[str] = mapped_column(Text)
    mapping: Mapped[dict | None] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list | None] = mapped_column(JSONB)     # [{role, content}, ...]
    position: Mapped[int] = mapped_column(Integer, default=0)  # order within a thread
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="charts")
    thread: Mapped["Thread"] = relationship(back_populates="charts")


class DailyUsage(Base):
    """One row per user per UTC day; `count` is the number of LLM calls made.
    Used to enforce the per-user daily request limit (admins are exempt)."""

    __tablename__ = "daily_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
