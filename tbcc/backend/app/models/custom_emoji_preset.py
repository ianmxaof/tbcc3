from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class CustomEmojiPreset(Base):
    """Reusable custom-emoji HTML banner (tg-emoji tags) for captions and relays."""

    __tablename__ = "custom_emoji_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    html_fragment = Column(Text, nullable=False)
    source_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
