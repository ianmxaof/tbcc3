"""Curated external industry priors (IIU-style) for signals and category crosswalk."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .base import Base


class IndustryBenchmark(Base):
    __tablename__ = "industry_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    title = Column(String(256), nullable=False)
    topic_type = Column(String(32), nullable=False, default="category")
    summary = Column(Text, nullable=False)
    demand_index = Column(Float, nullable=True)
    benchmark_json = Column(Text, nullable=True)
    source_url = Column(String(512), nullable=True)
    source_label = Column(String(64), nullable=True, default="IIU")
    effective_year = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
