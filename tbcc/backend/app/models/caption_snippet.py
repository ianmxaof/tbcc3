from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class CaptionSnippet(Base):
    """Reusable caption lines for dashboard + extension (persisted in DB, not browser-only)."""

    __tablename__ = "caption_snippets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
