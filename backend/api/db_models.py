"""ORM models for user-scoped session persistence.

A user uploads a `Dataset` (CSV) and generates one or more `Chart`s from it.
Everything the frontend needs to restore a dashboard — the mapping, rendered
HTML, and refine conversation history — lives on the Chart row. Mappings and
history are stored as JSONB so they round-trip without a rigid column schema.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    charts: Mapped[list["Chart"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(512))          # original filename
    content: Mapped[str] = mapped_column(Text)              # raw CSV text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="datasets")
    charts: Mapped[list["Chart"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class Chart(Base):
    __tablename__ = "charts"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    sub_prompt: Mapped[str] = mapped_column(Text)
    mapping: Mapped[dict | None] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list | None] = mapped_column(JSONB)     # [{role, content}, ...]
    position: Mapped[int] = mapped_column(Integer, default=0)  # order within a dashboard
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="charts")
    dataset: Mapped["Dataset"] = relationship(back_populates="charts")
