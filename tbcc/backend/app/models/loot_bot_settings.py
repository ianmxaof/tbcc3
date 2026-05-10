"""Singleton DB overrides for the AOF Loot Overseer bot (`python -m bots.loot_bot`)."""

from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Text

from .base import Base


class LootBotSettings(Base):
    __tablename__ = "loot_bot_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    # Optional dashboard override; if null, bot uses TBCC_LOOT_BOT_TOKEN from env.
    bot_token = Column(Text, nullable=True)
    # Username without @; falls back to TBCC_LOOT_BOT_USERNAME.
    bot_username = Column(String(64), nullable=True)
    # Primary private group invite (t.me/+…); falls back to TBCC_LOOT_ROOM_INVITE_URL.
    primary_loot_room_invite_url = Column(Text, nullable=True)
    primary_loot_room_chat_id = Column(BigInteger, nullable=True)
    config_poll_seconds = Column(Integer, nullable=True)
    narrative_enabled = Column(Boolean, nullable=False, default=False)
    narrative_system_prompt = Column(Text, nullable=True)
    drop_spoiler_default = Column(Boolean, nullable=False, default=True)
    runtime_adapter = Column(String(32), nullable=True)
    runtime_cmd_start = Column(Text, nullable=True)
    runtime_cmd_stop = Column(Text, nullable=True)
    runtime_cmd_restart = Column(Text, nullable=True)
    runtime_cmd_reload = Column(Text, nullable=True)
    runtime_cmd_status = Column(Text, nullable=True)
    operator_notes = Column(Text, nullable=True)
