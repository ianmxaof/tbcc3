import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from app.models.base import Base


class TargetStatus(enum.Enum):
    new = "new"
    contacted = "contacted"
    engaging = "engaging"
    converted = "converted"
    dead = "dead"


class ColdTarget(Base):
    __tablename__ = "cold_targets"

    id = Column(Integer, primary_key=True)
    telegram_username = Column(String, nullable=True)
    telegram_user_id = Column(String, nullable=True)

    source = Column(String, nullable=True)
    assigned_userbot_id = Column(Integer, ForeignKey("userbot_accounts.id"), nullable=True)

    status = Column(Enum(TargetStatus), default=TargetStatus.new, nullable=False)
    first_contact_at = Column(DateTime, nullable=True)
    last_contact_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(String, nullable=True)
