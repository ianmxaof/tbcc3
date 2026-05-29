from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class EmojiFactorySketchPage(Base):
    """Persistent design scratchpad pages (emoji pack workflow — Master composition)."""

    __tablename__ = "emoji_factory_sketch_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(256), nullable=True)
    body = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
