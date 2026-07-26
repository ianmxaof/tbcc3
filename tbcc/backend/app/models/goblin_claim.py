"""Telemetry for goblin drop claims."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer

from .base import Base


class GoblinClaim(Base):
    __tablename__ = "goblin_claim"

    id = Column(Integer, primary_key=True, autoincrement=True)
    drop_id = Column(Integer, ForeignKey("goblin_drop.id"), nullable=False, index=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    claimed_at = Column(DateTime, nullable=False)
    latency_ms = Column(Integer, nullable=True)
