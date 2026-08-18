"""Conversion playbooks — learned behavioral trajectories of converted clients.

Read-only with respect to the Format Engine: the playbook system observes a
conversion (demonstrated purchase commitment) and snapshot the trajectory that
led there, then matches similar future clients to re-apply the winning pattern.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class ConversionPlaybook(Base):
    """One row per captured conversion trajectory."""

    __tablename__ = "conversion_playbooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=True, index=True)
    # JSON array of phases the user passed through, e.g. ["introduction", "engagement"].
    phase_trajectory = Column(Text, nullable=True)
    # JSON snapshot of psych_markers at the moment of conversion.
    psych_markers_at_conversion = Column(Text, nullable=True)
    message_count_at_conversion = Column(Integer, nullable=True)
    payment_lane_used = Column(String(16), nullable=True)  # "stars" | "private"
    behavioral_directive_at_conversion = Column(String(512), nullable=True)
    conversion_outcome = Column(String(32), nullable=True)  # stars_purchase | zelle_crypto | unknown
    format_summary = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    times_matched = Column(Integer, nullable=False, default=0)