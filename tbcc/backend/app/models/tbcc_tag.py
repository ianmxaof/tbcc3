"""Structured tags for media (auto + manual). Legacy Media.tags string is kept in sync."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from datetime import datetime

from .base import Base


class TbccTag(Base):
    __tablename__ = "tbcc_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    # Optional UI grouping: "type", "source", "topic", etc.
    category = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MediaTagLink(Base):
    __tablename__ = "media_tag_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_id = Column(Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id = Column(Integer, ForeignKey("tbcc_tags.id", ondelete="CASCADE"), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=1.0)
    # rule = pattern-based; model = future ML; manual = user/dashboard
    source = Column(String(16), nullable=False, default="rule")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("media_id", "tag_id", name="uq_media_tag_link"),)
