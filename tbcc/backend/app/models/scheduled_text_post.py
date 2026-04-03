import json
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text

from .base import Base


class ScheduledTextPost(Base):
    __tablename__ = "scheduled_text_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    channel_id = Column(Integer, nullable=False)
    # Telegram forum topic id (same as Bot API message_thread_id); NULL = post to main chat / non-forum channel
    message_thread_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)  # one-time: when to post; interval: optional first run
    sent_at = Column(DateTime, nullable=True)  # one-time: set when posted; interval: unused
    interval_minutes = Column(Integer, nullable=True)  # non-null = recurring
    last_posted_at = Column(DateTime, nullable=True)  # for recurring: last post time
    media_ids = Column(Text, nullable=True)  # JSON list of media table IDs
    pool_id = Column(Integer, nullable=True)  # optional: use pool's approved media
    # Per-job overrides when pool_id is set (if NULL, use ContentPool.album_size / randomize_queue)
    album_size = Column(Integer, nullable=True)
    pool_randomize = Column(Boolean, nullable=True)
    # JSON list of caption strings; when 2+ entries, rotate in order each time the job posts
    content_variations = Column(Text, nullable=True)
    caption_rotation_index = Column(Integer, nullable=True)  # advances after each send; NULL starts at variation 0
    buttons = Column(Text, nullable=True)  # JSON: [{"text": "Label", "url": "https://..."}]
    created_at = Column(DateTime, nullable=True)

    def get_media_ids(self) -> list[int]:
        if not self.media_ids:
            return []
        try:
            return json.loads(self.media_ids)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_buttons(self) -> list[dict]:
        if not self.buttons:
            return []
        try:
            return json.loads(self.buttons)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_content_variations(self) -> list[str]:
        """Non-empty caption strings for rotation (2+ enables A,B,A,B…)."""
        if not self.content_variations:
            return []
        try:
            raw = json.loads(self.content_variations)
            if not isinstance(raw, list):
                return []
            out = []
            for x in raw:
                if isinstance(x, str) and x.strip():
                    out.append(x.strip())
            return out
        except (json.JSONDecodeError, TypeError):
            return []
