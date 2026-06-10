from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class MacroSearchSourceSubmission(Base):
    """Community-suggested macro model-search sources awaiting admin approval."""

    __tablename__ = "macro_search_source_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    url_template = Column(Text, nullable=False)
    sample_username = Column(String(64), nullable=True)
    sample_search_url = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending")  # pending | approved | rejected
    submitted_by = Column(String(32), nullable=True)
    reviewed_by = Column(String(32), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
