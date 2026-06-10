"""Async import pipeline jobs (extension bytes → staged → Celery telegram queue)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def new_import_job_id() -> str:
    return str(uuid.uuid4())


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="bytes")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="stored")
    pool_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    saved_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    staging_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    media_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extension_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
