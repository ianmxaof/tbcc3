from sqlalchemy import Column, Integer, String, Boolean, DateTime

from .base import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    source_type = Column(String)  # telegram_channel | reddit | manual
    identifier = Column(String)  # channel username or URL
    active = Column(Boolean, default=True)
    pool_id = Column(Integer)  # auto-assign scraped content to this pool
    schedule_cron = Column(String(64), nullable=True)  # e.g. "0 6 * * *" (minute hour dom month dow)
    schedule_enabled = Column(Boolean, default=False)
    media_types = Column(String(16), default="both")  # both | photos | videos
    max_messages_per_run = Column(Integer, default=50)
    last_scraped_at = Column(DateTime, nullable=True)
