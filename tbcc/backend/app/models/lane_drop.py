"""Lane Drop Checkpoint — approve merchandise before dedicated lane channel post."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from .base import Base


class LaneDrop(Base):
    """One merchandise drop waiting for (or past) human checkpoint."""

    __tablename__ = "lane_drops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    network_key = Column(String(64), nullable=False, index=True)
    # pending_checkpoint | approved | rejected | posted_glimpse
    status = Column(String(32), nullable=False, default="pending_checkpoint", index=True)
    title = Column(String(256), nullable=True)
    # Absolute or relative paths after robocopy fan-out
    promo_path = Column(Text, nullable=True)
    lane_path = Column(Text, nullable=True)
    vault_path = Column(Text, nullable=True)
    # JSON list of promo file paths chosen for 3-of-N glimpse (optional)
    glimpse_manifest_json = Column(Text, nullable=True)
    destination_url = Column(String(1024), nullable=True)
    primary_gate_url = Column(String(1024), nullable=True)
    source_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
