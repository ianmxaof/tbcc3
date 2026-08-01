"""Unified creative catalog — copy snippets and image prompt variations for RAG."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class CreativeCatalogEntry(Base):
    __tablename__ = "creative_catalog_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_type = Column(String(32), nullable=False, index=True)  # copy | image_prompt
    campaign = Column(String(128), nullable=True, index=True)
    catalog_key = Column(String(128), nullable=True, index=True)
    surface = Column(String(32), nullable=True, index=True)
    lane_key = Column(String(32), nullable=True, index=True)
    title = Column(String(256), nullable=True)
    body = Column(Text, nullable=True)
    master_json = Column(Text, nullable=True)
    subject_delta = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=True)
    prompt_gate_key = Column(String(128), nullable=True, index=True)
    asset_url = Column(String(1024), nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
