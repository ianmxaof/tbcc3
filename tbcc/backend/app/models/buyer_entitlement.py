"""Buyer entitlement ledger — channel-independent access (ban recovery)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func

from .base import Base


class BuyerEntitlement(Base):
    """One grant of paid access for a Telegram user (independent of chat membership)."""

    __tablename__ = "buyer_entitlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    kind = Column(String(32), nullable=False, index=True)
    # Network lane key (milf, big_tits, …) when kind=lane_pass; null for global products
    network_key = Column(String(64), nullable=True, index=True)
    plan_id = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="active", index=True)  # active|expired|revoked
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)  # null = open-ended (VIP / packs)
    primary_channel_ident = Column(String(64), nullable=True)
    backup_channel_ident = Column(String(64), nullable=True)
    last_invite_url = Column(String(512), nullable=True)
    last_reissued_at = Column(DateTime, nullable=True)
    source_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
