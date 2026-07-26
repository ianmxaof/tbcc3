"""DM outreach consent — human-gate ('I'm not a robot') opt-in for paced bot DMs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from .base import Base


class FunnelDmConsent(Base):
    __tablename__ = "funnel_dm_consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(Integer, nullable=False, unique=True, index=True)
    gate_target = Column(String(32), nullable=False, default="loot_room")
    source = Column(String(64), nullable=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    invite_url = Column(String(512), nullable=True)
    dm_opt_in = Column(Boolean, nullable=False, default=True)
    acknowledged_at = Column(DateTime, nullable=False, server_default=func.now())
    created_at = Column(DateTime, nullable=False, server_default=func.now())
