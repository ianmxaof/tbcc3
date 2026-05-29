"""Singleton DB overrides for the AOF Loot Overseer bot (`python -m bots.loot_bot`)."""

import json

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
    # Main AOF community group — daily loot game promo posts from @aof_lootgod_bot (Celery).
    aof_group_chat_id = Column(BigInteger, nullable=True)
    aof_group_message_thread_id = Column(Integer, nullable=True)
    daily_promo_enabled = Column(Boolean, nullable=False, default=False)
    daily_promo_hour_utc = Column(Integer, nullable=True)  # 0–23; beat runs hourly and sends when hour matches
    daily_promo_intro_html = Column(Text, nullable=True)
    # After each daily Telegram promo: mirror to Buffer → X (same pattern as scheduled posts).
    buffer_mirror_enabled = Column(Boolean, nullable=False, default=False)
    buffer_publish_now = Column(Boolean, nullable=False, default=False)
    buffer_x_queue_json = Column(Text, nullable=True)
    config_poll_seconds = Column(Integer, nullable=True)
    narrative_enabled = Column(Boolean, nullable=False, default=False)
    narrative_system_prompt = Column(Text, nullable=True)
    loot_referral_enabled = Column(Boolean, nullable=False, default=True)
    referral_bonus_pulls = Column(Integer, nullable=True)
    drop_spoiler_default = Column(Boolean, nullable=False, default=True)
    runtime_adapter = Column(String(32), nullable=True)
    runtime_cmd_start = Column(Text, nullable=True)
    runtime_cmd_stop = Column(Text, nullable=True)
    runtime_cmd_restart = Column(Text, nullable=True)
    runtime_cmd_reload = Column(Text, nullable=True)
    runtime_cmd_status = Column(Text, nullable=True)
    operator_notes = Column(Text, nullable=True)

    def get_buffer_x_queue(self) -> list[dict]:
        if not self.buffer_x_queue_json:
            return []
        try:
            raw = json.loads(self.buffer_x_queue_json)
            if not isinstance(raw, list):
                return []
            out: list[dict] = []
            for x in raw:
                if not isinstance(x, dict):
                    continue
                t = str(x.get("text") or "").strip()
                if not t:
                    continue
                entry: dict = {"text": t}
                iu = str(x.get("image_url") or "").strip()
                if iu.startswith("https://"):
                    entry["image_url"] = iu
                out.append(entry)
                if len(out) >= 10:
                    break
            return out
        except (json.JSONDecodeError, TypeError):
            return []

    def set_buffer_x_queue(self, items: list[dict]) -> None:
        norm: list[dict] = []
        for x in items[:10]:
            if not isinstance(x, dict):
                continue
            t = str(x.get("text") or "").strip()
            if not t:
                continue
            entry: dict = {"text": t[:2800]}
            iu = str(x.get("image_url") or "").strip()
            if iu.startswith("https://"):
                entry["image_url"] = iu[:2048]
            norm.append(entry)
        self.buffer_x_queue_json = json.dumps(norm) if norm else None
