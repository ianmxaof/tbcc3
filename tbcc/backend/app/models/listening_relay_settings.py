import json

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .base import Base


class ListeningRelaySettings(Base):
    """
    Single-row settings: relay music / manual “now playing” events to a Telegram channel.

    Last.fm aggregates Spotify, SoundCloud (when linked), and more. YouTube and others can use
    the webhook + IFTTT or similar.
    """

    __tablename__ = "listening_relay_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    channel_id = Column(Integer, nullable=True)
    # When True, each scrobble/webhook posts once to a random AOF network channel (main chat).
    relay_random_network_channel = Column(Boolean, nullable=False, default=False)
    message_thread_id = Column(Integer, nullable=True)
    lastfm_username = Column(String(256), nullable=True)
    lastfm_api_key = Column(String(128), nullable=True)
    poll_interval_minutes = Column(Integer, nullable=False, default=3)
    last_poll_at = Column(DateTime, nullable=True)
    last_lastfm_signature = Column(String(512), nullable=True)
    message_template_html = Column(Text, nullable=True)
    # JSON list of HTML templates with same placeholders as message_template_html; when 2+ entries, rotate per send.
    message_template_variations = Column(Text, nullable=True)
    message_template_rotation_index = Column(Integer, nullable=True)
    # Appended below formatted Last.fm/webhook body (Telegram HTML). No placeholders — paste URLs or copy as-is.
    message_footer_html = Column(Text, nullable=True)
    # JSON list parallel to non-empty template variations; empty strings OK (no footer for that slot).
    message_footer_variations = Column(Text, nullable=True)
    # JSON list parallel to template slots: tap-to-copy <pre> block sent as a second message under the preview card.
    message_copy_block_variations = Column(Text, nullable=True)
    # sequential | random — how template/footer/copy slots are chosen per scrobble
    template_rotation_mode = Column(String(16), nullable=False, default="sequential")
    # JSON list parallel to template slots: copy-panel media, buttons, promo URLs (scheduler parity)
    message_slot_extras_json = Column(Text, nullable=True)
    ascii_art_enabled = Column(Boolean, nullable=False, default=False)
    ascii_art_min_interval = Column(Integer, nullable=False, default=3)
    ascii_art_max_interval = Column(Integer, nullable=False, default=6)
    ascii_art_scrobble_counter = Column(Integer, nullable=False, default=0)
    ascii_art_next_threshold = Column(Integer, nullable=True)
    ascii_art_library_json = Column(Text, nullable=True)
    tryptych_enabled = Column(Boolean, nullable=False, default=False)
    # When True, ASCII cadence posts 3 chained copy panels instead of one
    tryptych_on_ascii_beat = Column(Boolean, nullable=False, default=True)
    webhook_secret = Column(String(128), nullable=True)
    last_webhook_signature = Column(String(512), nullable=True)
    send_silent = Column(Boolean, nullable=False, default=True)
    buffer_relay_enabled = Column(Boolean, nullable=False, default=False)
    buffer_relay_min_interval_minutes = Column(Integer, nullable=False, default=360)
    buffer_relay_max_per_day_utc = Column(Integer, nullable=False, default=5)
    buffer_relay_utc_day = Column(String(10), nullable=True)
    buffer_relay_posts_today = Column(Integer, nullable=False, default=0)
    buffer_relay_last_post_at = Column(DateTime, nullable=True)
    # Pre-written X captions: consumed one per buffer relay trigger (like scheduled_text_posts.buffer_x_queue).
    buffer_x_queue_json = Column(Text, nullable=True)
    goblin_mode_enabled = Column(Boolean, nullable=False, default=False)
    goblin_spawn_chance = Column(Float, nullable=False, default=0.2)
    goblin_cooldown_minutes = Column(Integer, nullable=False, default=120)
    goblin_last_spawn_at = Column(DateTime, nullable=True)
    goblin_announce_ttl_seconds = Column(Integer, nullable=False, default=45)
    goblin_claims_cap = Column(Integer, nullable=False, default=5)
    goblin_max_per_day_utc = Column(Integer, nullable=False, default=3)
    goblin_utc_day = Column(String(10), nullable=True)
    goblin_spawns_today = Column(Integer, nullable=False, default=0)

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
                if len(out) >= 16:
                    break
            return out
        except (json.JSONDecodeError, TypeError):
            return []

    def set_buffer_x_queue(self, items: list[dict]) -> None:
        norm: list[dict] = []
        for x in items[:16]:
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
