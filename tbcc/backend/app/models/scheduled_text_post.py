import json
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text

from .base import Base


class ScheduledTextPost(Base):
    __tablename__ = "scheduled_text_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    # When set, this row is part of a multi-channel campaign; scheduler fires the lowest-id row only.
    campaign_group_id = Column(String(36), nullable=True)
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
    # If True, ignore explicit media/promos and always pull this job's batch from pool_id.
    pool_only_mode = Column(Boolean, nullable=False, default=False)
    # Telegram send: no notification sound / fewer push interruptions for subscribers.
    send_silent = Column(Boolean, nullable=False, default=False)
    # After a successful send, pin the channel post (first album message). Requires pin rights.
    pin_after_send = Column(Boolean, nullable=False, default=False)
    # JSON list of caption strings; when 2+ entries, rotate in order each time the job posts
    content_variations = Column(Text, nullable=True)
    caption_rotation_index = Column(Integer, nullable=True)  # advances after each send; NULL starts at variation 0
    buttons = Column(Text, nullable=True)  # JSON: [{"text": "Label", "url": "https://..."}]
    # JSON list of public URLs (legacy single-album); superseded by album_variants_json when set
    attachment_urls_json = Column(Text, nullable=True)
    # JSON array of {"attachment_urls": [...], "media_ids": [...]} — aligned with caption rotation via modulo
    album_variants_json = Column(Text, nullable=True)
    # static | shuffle | carousel — reorder items in each send (carousel rotates starting index)
    album_order_mode = Column(String(16), nullable=True)
    album_carousel_index = Column(Integer, nullable=True)
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

    def _urls_from_attachment_urls_json_column(self) -> list[str]:
        """Legacy flat column attachment_urls_json."""
        if not self.attachment_urls_json:
            return []
        try:
            raw = json.loads(self.attachment_urls_json)
            if not isinstance(raw, list):
                return []
            out: list[str] = []
            for x in raw:
                if isinstance(x, str) and x.strip():
                    out.append(x.strip())
            return out[:10]
        except (json.JSONDecodeError, TypeError):
            return []

    def get_attachment_urls(self) -> list[str]:
        """First album variant promo URLs, or legacy flat list (backward compat for API)."""
        if self.album_variants_json:
            vars_ = self.get_album_variants()
            if vars_:
                urls = vars_[0].get("attachment_urls") or []
                return [u for u in urls if isinstance(u, str) and u.strip()][:10]
            return []
        return self._urls_from_attachment_urls_json_column()

    @staticmethod
    def _normalize_album_variant_entry(obj) -> dict:
        out: dict = {"attachment_urls": [], "media_ids": []}
        if not isinstance(obj, dict):
            return out
        raw_u = obj.get("attachment_urls")
        if isinstance(raw_u, list):
            out["attachment_urls"] = [str(x).strip() for x in raw_u if str(x).strip()][:10]
        raw_m = obj.get("media_ids")
        if isinstance(raw_m, list):
            for x in raw_m:
                try:
                    out["media_ids"].append(int(x))
                except (TypeError, ValueError):
                    pass
        return out

    def get_album_variants(self) -> list[dict]:
        """
        List of per-caption album specs: {attachment_urls, media_ids}.
        If album_variants_json is unset, synthesize one variant from legacy media_ids + attachment_urls_json.
        """
        if self.album_variants_json:
            try:
                raw = json.loads(self.album_variants_json)
                if isinstance(raw, list) and raw:
                    return [self._normalize_album_variant_entry(x) for x in raw]
            except (json.JSONDecodeError, TypeError):
                pass
        mids = self.get_media_ids()
        legacy_urls = self._urls_from_attachment_urls_json_column()
        if not mids and not legacy_urls:
            return []
        return [{"attachment_urls": legacy_urls, "media_ids": mids}]
