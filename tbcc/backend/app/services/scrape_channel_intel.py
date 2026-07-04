"""Inbound Telegram channel backlog: forward policy, AOF lane, posting cadence."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from telethon.utils import get_peer_id

from app.models.scrape_channel_profile import ScrapeChannelProfile
from app.models.content_pool import ContentPool

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#[\w\u0080-\uFFFF]+", re.UNICODE)


def scraper_forward_only() -> bool:
    """
    When True (default), channel scrapes never call download_media — forward to Saved Messages only.
    No bytes are written to local disk; RAM download+reupload is also disabled.
    """
    return (os.getenv("TBCC_SCRAPER_FORWARD_ONLY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def auto_skip_forward_disabled() -> bool:
    return (os.getenv("TBCC_SCRAPER_SKIP_NOFORWARD") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def is_forward_restricted_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "chatforwardsrestricted" in name or "forwardrestricted" in name:
        return True
    if "can't forward" in text or "cannot forward" in text:
        return True
    if "forward" in text and ("restrict" in text or "protected" in text or "forbidden" in text):
        return True
    return False


def entity_forward_flag_disabled(entity) -> bool:
    """Best-effort channel/group no-forward flag from Telethon entity."""
    if getattr(entity, "noforwards", None) is True:
        return True
    if getattr(entity, "restrictions", None):
        try:
            if "noforwards" in str(entity.restrictions).lower():
                return True
        except Exception:
            pass
    return False


def pool_key_for_pool_id(db: Session, pool_id: int | None) -> tuple[str | None, str | None]:
    if not pool_id:
        return None, None
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    if not pool:
        return None, None
    from app.data.aof_network import AOF_NETWORK_CHANNELS

    for ch in AOF_NETWORK_CHANNELS:
        if ch.pool_name == pool.name:
            return ch.key, pool.name
    return None, pool.name


def extract_hashtags_from_texts(texts: list[str], *, limit: int = 32) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for raw in texts:
        for m in HASHTAG_RE.findall(raw or ""):
            key = m.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(m)
            if len(out) >= limit:
                return ", ".join(out)
    return ", ".join(out)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_posting_cadence(dates: list[datetime]) -> dict[str, Any]:
    if not dates:
        return {
            "posts_per_day": None,
            "posts_per_week": None,
            "posts_per_month": None,
            "messages_sampled": 0,
            "last_post_at": None,
            "cadence_span_days": None,
            "cadence_json": {},
        }
    norm = sorted(_aware(d) for d in dates)
    span_days = max(1.0, (norm[-1] - norm[0]).total_seconds() / 86400.0)
    count = len(norm)
    ppd = count / span_days
    by_month = Counter(d.strftime("%Y-%m") for d in norm)
    by_weekday = Counter(d.strftime("%A") for d in norm)
    return {
        "posts_per_day": round(ppd, 4),
        "posts_per_week": round(ppd * 7.0, 3),
        "posts_per_month": round(ppd * 30.0, 2),
        "messages_sampled": count,
        "last_post_at": norm[-1].replace(tzinfo=None),
        "cadence_span_days": round(span_days, 2),
        "cadence_json": {
            "by_month": dict(sorted(by_month.items())),
            "by_weekday": dict(by_weekday),
        },
    }


def upsert_channel_profile(
    db: Session,
    *,
    chat_id: int,
    source_id: int | None = None,
    title: str | None = None,
    username: str | None = None,
    identifier: str | None = None,
    forward_enabled: bool | None = None,
    skip_reason: str | None = None,
    pool_key: str | None = None,
    pool_name: str | None = None,
    category: str | None = None,
    folder_label: str | None = None,
    tags_sample: str | None = None,
    cadence: dict[str, Any] | None = None,
) -> ScrapeChannelProfile:
    row = db.query(ScrapeChannelProfile).filter(ScrapeChannelProfile.chat_id == int(chat_id)).first()
    now = datetime.utcnow()
    if not row:
        row = ScrapeChannelProfile(chat_id=int(chat_id), created_at=now)
        db.add(row)
    if source_id is not None:
        row.source_id = int(source_id)
    if title:
        row.title = title[:512]
    if username is not None:
        row.username = (username or "")[:128] or None
    if identifier:
        row.identifier = identifier[:256]
    if forward_enabled is not None:
        row.forward_enabled = bool(forward_enabled)
        row.forward_probe_at = now
    if skip_reason is not None:
        row.skip_reason = (skip_reason or "")[:256] or None
    if pool_key:
        row.pool_key = pool_key[:32]
    if pool_name:
        row.pool_name = pool_name[:128]
    if category:
        row.category = category[:64]
    if folder_label:
        row.folder_label = folder_label[:128]
    if tags_sample is not None:
        row.tags_sample = (tags_sample or "")[:2000] or None
    if cadence:
        row.posts_per_day = cadence.get("posts_per_day")
        row.posts_per_week = cadence.get("posts_per_week")
        row.posts_per_month = cadence.get("posts_per_month")
        row.messages_sampled = int(cadence.get("messages_sampled") or row.messages_sampled or 0)
        row.last_post_at = cadence.get("last_post_at")
        row.cadence_span_days = cadence.get("cadence_span_days")
        cj = cadence.get("cadence_json") or {}
        row.cadence_json = json.dumps(cj, separators=(",", ":")) if cj else row.cadence_json
    row.updated_at = now
    db.flush()
    return row


def profile_to_dict(row: ScrapeChannelProfile) -> dict[str, Any]:
    cadence = {}
    if row.cadence_json:
        try:
            cadence = json.loads(row.cadence_json)
        except json.JSONDecodeError:
            cadence = {}
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "source_id": row.source_id,
        "title": row.title,
        "username": row.username,
        "identifier": row.identifier,
        "forward_enabled": row.forward_enabled,
        "forward_probe_at": row.forward_probe_at.isoformat() if row.forward_probe_at else None,
        "skip_reason": row.skip_reason,
        "pool_key": row.pool_key,
        "pool_name": row.pool_name,
        "category": row.category,
        "folder_label": row.folder_label,
        "tags_sample": row.tags_sample,
        "posts_per_day": row.posts_per_day,
        "posts_per_week": row.posts_per_week,
        "posts_per_month": row.posts_per_month,
        "messages_sampled": row.messages_sampled,
        "last_post_at": row.last_post_at.isoformat() if row.last_post_at else None,
        "cadence_span_days": row.cadence_span_days,
        "cadence": cadence,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def probe_channel_forwardable(client, entity, *, probe_limit: int = 25) -> tuple[bool | None, str | None]:
    """
    Try forwarding one recent media message to Saved Messages.
    Returns (forward_enabled, skip_reason). None = could not probe (no media in window).
    """
    if entity_forward_flag_disabled(entity):
        return False, "channel_noforwards_flag"

    from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage

    async for message in client.iter_messages(entity, limit=max(5, min(probe_limit, 40))):
        if not message.media:
            continue
        if isinstance(message.media, MessageMediaWebPage):
            wp = message.media.webpage
            if wp is None or (not getattr(wp, "photo", None) and not getattr(wp, "document", None)):
                continue
        elif not isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
            continue
        try:
            fwd = await client.forward_messages("me", message)
            if fwd:
                try:
                    mid = fwd[0].id if isinstance(fwd, list) else fwd.id
                    await client.delete_messages("me", [mid])
                except Exception:
                    pass
            return True, None
        except Exception as e:
            if is_forward_restricted_error(e):
                return False, "forward_restricted"
            return False, type(e).__name__
    return None, "no_media_in_probe_window"


def chat_id_from_entity(entity) -> int:
    return int(get_peer_id(entity))
