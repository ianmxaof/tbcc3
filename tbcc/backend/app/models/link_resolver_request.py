"""Queued ad-link resolution jobs (Bypass.vip / similar)."""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class LinkResolverRequest(Base):
    __tablename__ = "link_resolver_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(36), unique=True, nullable=False, index=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    tier = Column(String(16), nullable=False, default="free")  # free|premium
    input_url = Column(Text, nullable=False)
    normalized_url = Column(String(2048), nullable=True)
    status = Column(String(32), nullable=False, default="queued")  # queued|running|succeeded|failed|blocked
    reason_code = Column(String(64), nullable=True)
    final_url = Column(Text, nullable=True)
    risk_level = Column(String(16), nullable=True)  # low|medium|high
    provider_latency_ms = Column(Integer, nullable=True)
    error_detail = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
