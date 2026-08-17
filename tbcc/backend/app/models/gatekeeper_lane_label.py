"""Gold lane labels for the gatekeeper prototype bank — hub-topic deposits,
operator approve/reject. See app.services.gatekeeper_prototypes."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class GatekeeperLaneLabel(Base):
    """One row per gold label. No unique on media_id — operator can relabel,
    and the same media can pick up a caption-only row then a later
    embedding-bearing row once CLIP is available."""

    __tablename__ = "gatekeeper_lane_labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_id = Column(BigInteger, nullable=True)
    file_unique_id = Column(String(128), nullable=False, index=True)
    # JSON list of network_keys — empty list "[]" for operator_reject.
    lanes_json = Column(Text, nullable=False)
    # hub_topic | operator_approve | operator_reject
    source = Column(String(32), nullable=False)
    # JSON float list (512-d ViT-B/32), unquantized. Null when caption-only.
    embedding_json = Column(Text, nullable=True)
    dim = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
