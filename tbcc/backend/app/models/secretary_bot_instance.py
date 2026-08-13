"""Inbound secretary clone fleet — BotFather tokens sharing one brain (Phase 2)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class SecretaryBotInstance(Base):
    __tablename__ = "secretary_bot_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(128), nullable=True)
    bot_username = Column(String(64), nullable=True, index=True)
    bot_token = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    notify_chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
