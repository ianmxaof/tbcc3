"""FAQ knowledge chunks for secretary RAG retrieval."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class SecretaryKnowledgeEntry(Base):
    __tablename__ = "secretary_knowledge_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=True)
    body = Column(Text, nullable=False)
    tags = Column(String(500), nullable=True)
    source_path = Column(String(512), nullable=True)
    chunk_index = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
