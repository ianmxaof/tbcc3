from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, nullable=False)
    source_name = Column(String(256), nullable=True)
    pool_id = Column(Integer, nullable=True)
    trigger = Column(String(16), nullable=False, default="manual")  # manual | cron
    status = Column(String(16), nullable=False, default="queued")  # queued | running | done | failed | skipped
    messages_scanned = Column(Integer, nullable=False, default=0)
    stored = Column(Integer, nullable=False, default=0)
    skipped_duplicate = Column(Integer, nullable=False, default=0)
    skipped_media_type = Column(Integer, nullable=False, default=0)
    skipped_no_media = Column(Integer, nullable=False, default=0)
    errors_count = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text, nullable=True)
    errors_json = Column(Text, nullable=True)
    celery_task_id = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
