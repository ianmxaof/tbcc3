"""Vision-LLM lane classification decisions — shadow-mode logging only.

One row per media item classified against the canonical AOF lane taxonomy
(``app.services.aof_lane_tag_map.CANONICAL_LANE_KEYS``). Does not drive routing;
see ``app.services.media_lane_vision_classify``.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .base import Base


class MediaLaneVisionDecision(Base):
    """One row per media_id — idempotent, never re-classified once logged."""

    __tablename__ = "media_lane_vision_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_id = Column(Integer, nullable=False, index=True)
    lane_key = Column(String(32), nullable=True)
    nsfw_tier = Column(String(16), nullable=True)
    # Reserved: today's vision prompt returns no numeric confidence.
    confidence = Column(Float, nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
