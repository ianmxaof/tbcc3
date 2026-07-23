"""Click beacon links + hits (iplogger-inspired; no GPS)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from .base import Base


class ClickLink(Base):
    __tablename__ = "click_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(32), nullable=False, unique=True, index=True)
    destination_url = Column(String(2048), nullable=False)
    label = Column(String(128), nullable=True)
    active = Column(Integer, nullable=False, default=1)  # 1/0 for sqlite-friendly bool
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ClickLinkHit(Base):
    __tablename__ = "click_link_hits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    link_id = Column(Integer, ForeignKey("click_links.id"), nullable=False, index=True)
    campaign_id = Column(String(128), nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    referer = Column(String(512), nullable=True)
    country = Column(String(8), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
