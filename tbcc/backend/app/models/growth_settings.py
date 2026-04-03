"""Single-row app config for referrals + landing bulletin (dashboard-editable, env fallback)."""

from sqlalchemy import Column, Integer, String, Text

from .base import Base


class GrowthSettings(Base):
    __tablename__ = "growth_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Landing bulletin (Telegram)
    landing_bulletin_chat_id = Column(String(256), nullable=True)
    landing_bulletin_message_thread_id = Column(Integer, nullable=True)
    landing_bulletin_hour_utc = Column(Integer, nullable=True)
    landing_bulletin_bot_username = Column(String(128), nullable=True)
    landing_bulletin_intro = Column(Text, nullable=True)
    # Referral copy (payment bot / API)
    referral_group_invite_link = Column(String(512), nullable=True)
    referral_group_name = Column(String(256), nullable=True)
    referral_reward_days = Column(Integer, nullable=True)
    referral_mode = Column(String(32), nullable=True)  # community | premium
    # Milestone FOMO line to group/chat
    milestone_progress_chat_id = Column(String(256), nullable=True)
