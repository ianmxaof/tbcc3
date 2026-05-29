from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class PromoAffiliateLink(Base):
    """Dashboard: curated outbound promo URLs (affiliate programs, landing pages)."""

    __tablename__ = "promo_affiliate_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(512), nullable=False)
    url = Column(Text, nullable=False)
    # Optional shorter outbound link (manual paste or POST …/shorten). Insert from picker prefers this when set.
    short_url = Column(Text, nullable=True)
    payout_kind = Column(String(16), nullable=False, default="other")  # pps | revshare | cpa | other
    payout_detail = Column(String(64), nullable=True)
    priority_tier = Column(Integer, nullable=False, default=10)
    expires_at = Column(DateTime, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
