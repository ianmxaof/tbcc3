from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from .base import Base


class CaptureArchiveEntry(Base):
    """Server-side master archive (URLs + usernames), merged with extension sync and media imports."""

    __tablename__ = "capture_archive_entries"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_capture_archive_kind_value"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(16), nullable=False)  # url | username
    value = Column(Text, nullable=False)
    source = Column(String(80), nullable=True)
    ref = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    origin = Column(String(32), nullable=True)  # extension | media_library | import
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
