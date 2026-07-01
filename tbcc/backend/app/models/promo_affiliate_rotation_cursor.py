from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from .base import Base


class PromoAffiliateRotationCursor(Base):
    """Round-robin cursor per placement (+ optional network channel key)."""

    __tablename__ = "promo_affiliate_rotation_cursors"
    __table_args__ = (UniqueConstraint("placement", "network_key", name="uq_promo_affiliate_rotation_cursor"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    placement = Column(String(32), nullable=False)
    network_key = Column(String(32), nullable=False, default="")
    cursor_index = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
