from sqlalchemy import Column, Integer, String, DateTime, Boolean, UniqueConstraint
from datetime import datetime

from .base import Base


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (UniqueConstraint("file_unique_id", "pool_id", name="uq_media_file_unique_id_pool_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id = Column(Integer, nullable=False)
    file_id = Column(String, nullable=False)
    file_unique_id = Column(String, nullable=False)  # Dedup per (file_unique_id, pool_id)
    media_type = Column(String)  # photo, video, gif
    source_channel = Column(String)
    tags = Column(String)  # comma-separated
    pool_id = Column(Integer)
    status = Column(String, default="pending")  # pending|approved|rejected|posted
    created_at = Column(DateTime, default=datetime.utcnow)
