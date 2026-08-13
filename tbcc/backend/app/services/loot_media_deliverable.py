"""Whether loot roll media can be delivered (bytes on disk or live Saved Messages ref)."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models.media import Media
from app.services.local_media_storage import is_local_pool_media, local_media_path, read_local_media_bytes
from app.services.saved_messages_policy import loot_local_bytes_only

logger = logging.getLogger(__name__)


def loot_media_has_local_bytes(media: Media) -> bool:
    if not (is_local_pool_media(media) or str(getattr(media, "file_id", "") or "").startswith("local:")):
        return False
    if local_media_path(media):
        return True
    return bool(read_local_media_bytes(media))


def is_loot_media_roll_candidate(media: Media) -> bool:
    """
    Eligible for roll selection.

    When TBCC_LOOT_LOCAL_BYTES_ONLY=1 (default): only rows with bytes on disk.
    Legacy mode: Saved Messages refs allowed until audit quarantines them.
    """
    if (media.status or "").strip().lower() != "approved":
        return False
    if loot_media_has_local_bytes(media):
        return True
    if loot_local_bytes_only():
        return False
    tg_id = int(getattr(media, "telegram_message_id", 0) or 0)
    return tg_id > 0


def filter_roll_candidates(rows: list[Media]) -> list[Media]:
    return [r for r in rows if is_loot_media_roll_candidate(r)]


def quarantine_stale_saved_message(db: Session, media: Media, *, reason: str = "saved_message_missing") -> None:
    """Remove dead Saved Messages refs from the loot roll pool."""
    row = db.query(Media).filter(Media.id == int(media.id)).first()
    if not row:
        return
    if (row.status or "").strip().lower() != "approved":
        return
    row.status = "rejected"
    tags = (row.tags or "").strip()
    if "stale_saved_msg" not in [t.strip() for t in tags.split(",") if t.strip()]:
        row.tags = f"{tags},stale_saved_msg".strip(",") if tags else "stale_saved_msg"
    note = {
        "loot_audit": {
            "reason": reason,
            "telegram_message_id": int(row.telegram_message_id or 0),
        }
    }
    try:
        prior = json.loads(row.classification_json or "{}")
        if not isinstance(prior, dict):
            prior = {}
    except json.JSONDecodeError:
        prior = {}
    prior.update(note)
    row.classification_json = json.dumps(prior, separators=(",", ":"))
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("quarantine stale loot media failed id=%s", row.id)
