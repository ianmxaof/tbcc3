"""Idempotent seed: AOF X promo lines → caption_snippets + listening relay Buffer copy blocks."""

from __future__ import annotations

import json
import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.data.aof_x_promo_defaults import AOF_X_PROMO_DEFAULTS, AOF_X_PROMO_TITLE_PREFIX
from app.models.caption_snippet import CaptionSnippet
from app.models.listening_relay_settings import ListeningRelaySettings

logger = logging.getLogger(__name__)

LISTENING_RELAY_ROW_ID = 1
AOF_HUB_INVITE_MARKERS = (
    "https://t.me/aof_lootgod_bot?start=loot_free",
    "https://t.me/+" + "hMQzGs" + "BFjF02MDkx",
)


def _parse_copy_block_slots(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [str(raw).strip()] if str(raw).strip() else []
    if not isinstance(arr, list):
        return []
    return [str(x) if x is not None else "" for x in arr]


def _aof_promo_in_copy_blocks(raw: str | None) -> bool:
    return any(marker in slot for slot in _parse_copy_block_slots(raw) for marker in AOF_HUB_INVITE_MARKERS)


def seed_aof_x_promo_defaults(db: Session) -> dict[str, int]:
    """
    Insert missing caption snippets (by title) and relay copy-block variations when empty.
    Safe to run on every API startup.
    """
    tables = set(inspect(db.get_bind()).get_table_names())
    created_snippets = 0
    if "caption_snippets" in tables:
        existing_titles = {
            (r.title or "").strip()
            for r in db.query(CaptionSnippet)
            .filter(CaptionSnippet.title.isnot(None))
            .filter(CaptionSnippet.title.like(f"{AOF_X_PROMO_TITLE_PREFIX}%"))
            .all()
        }
    else:
        existing_titles = set()

    for item in AOF_X_PROMO_DEFAULTS:
        if "caption_snippets" not in tables:
            break
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "").strip()
        if not body or title in existing_titles:
            continue
        db.add(CaptionSnippet(title=title[:256], body=body[:16000]))
        existing_titles.add(title)
        created_snippets += 1

    seeded_relay_copy = 0
    if "listening_relay_settings" not in tables:
        if created_snippets:
            db.commit()
        return {"caption_snippets": created_snippets, "relay_copy_blocks": 0}

    row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == LISTENING_RELAY_ROW_ID).first()
    if row is None:
        row = ListeningRelaySettings(id=LISTENING_RELAY_ROW_ID)
        db.add(row)
        db.flush()

    promo_bodies = [(item.get("body") or "").strip() for item in AOF_X_PROMO_DEFAULTS]
    promo_bodies = [b for b in promo_bodies if b]
    existing_raw = getattr(row, "message_copy_block_variations", None)
    if promo_bodies and not _aof_promo_in_copy_blocks(existing_raw):
        existing = _parse_copy_block_slots(existing_raw)
        non_empty_existing = [s for s in existing if s.strip()]
        if non_empty_existing:
            row.message_copy_block_variations = json.dumps(promo_bodies + existing)
        else:
            row.message_copy_block_variations = json.dumps(promo_bodies)
        if int(row.message_template_rotation_index or 0) < 0:
            row.message_template_rotation_index = 0
        seeded_relay_copy = len(promo_bodies)

    if created_snippets or seeded_relay_copy:
        db.commit()
        logger.info(
            "seed_aof_x_promo_defaults: caption_snippets=%s relay_copy_blocks=%s",
            created_snippets,
            seeded_relay_copy,
        )
    return {"caption_snippets": created_snippets, "relay_copy_blocks": seeded_relay_copy}
