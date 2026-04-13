from sqlalchemy import Boolean, Column, Integer, String, DateTime

from .base import Base


class ContentPool(Base):
    __tablename__ = "content_pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)  # e.g. "cosplay", "amateur"
    channel_id = Column(Integer)  # target posting channel
    album_size = Column(Integer, default=5)
    interval_minutes = Column(Integer, default=60)
    last_posted = Column(DateTime, nullable=True)
    # Toggle pool-level cron posting (Scheduler tab jobs can still post from this pool).
    auto_post_enabled = Column(Boolean, default=True, nullable=False)
    # When True, approved queue items are shuffled before building albums (FIFO otherwise).
    randomize_queue = Column(Boolean, default=False, nullable=False)
