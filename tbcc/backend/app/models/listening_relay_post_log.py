"""Append-only log of listening-relay Telegram / Buffer fan-out posts."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class ListeningRelayPostLog(Base):
    __tablename__ = "listening_relay_post_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # lastfm | webhook | test
    trigger_kind = Column("trigger_kind", String(16), nullable=False, default="lastfm")
    status = Column(String(16), nullable=False, default="queued")  # queued | sent | failed
    source = Column(String(64), nullable=True)
    source_label = Column(String(64), nullable=True)
    artist = Column(String(512), nullable=True)
    title = Column(String(512), nullable=True)
    album = Column(String(512), nullable=True)
    url = Column(Text, nullable=True)
    channel_id = Column(Integer, nullable=True)
    message_thread_id = Column(Integer, nullable=True)
    random_lane = Column(Boolean, nullable=False, default=False)
    template_slot = Column(Integer, nullable=True)
    template_slots_total = Column(Integer, nullable=True)
    ascii_beat = Column(Boolean, nullable=False, default=False)
    tryptych = Column(Boolean, nullable=False, default=False)
    copy_followups_count = Column(Integer, nullable=False, default=0)
    send_silent = Column(Boolean, nullable=False, default=True)
    main_html_preview = Column(Text, nullable=True)
    telegram_message_id = Column(Integer, nullable=True)
    buffer_sent = Column(Boolean, nullable=False, default=False)
    discord_sent = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    extra_json = Column(Text, nullable=True)
