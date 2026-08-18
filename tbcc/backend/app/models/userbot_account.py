import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text
from app.models.base import Base


class WarmupState(enum.Enum):
    cold = "cold"
    warming = "warming"
    warm = "warm"


class UserbotAccount(Base):
    __tablename__ = "userbot_accounts"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    session_file_path = Column(String, nullable=False)
    proxy_json = Column(Text, nullable=True)

    warmup_state = Column(Enum(WarmupState), default=WarmupState.cold, nullable=False)
    daily_message_count = Column(Integer, default=0, nullable=False)
    max_daily_limit = Column(Integer, default=30, nullable=False)

    is_banned = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)

    def reset_daily_counts(self):
        self.daily_message_count = 0
