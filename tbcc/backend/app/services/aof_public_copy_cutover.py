"""DB-only refresh for the AOF Main -> Loot Room public funnel cutover."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.data.aof_x_promo_defaults import AOF_X_PROMO_DEFAULTS
from app.models.caption_snippet import CaptionSnippet
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.seed_aof_buffer_armory import build_armory_queue_items

LOOT_BOT_FREE_PULL_URL = "https://t.me/aof_lootgod_bot?start=loot_free"
LOOT_ROOM_PUBLIC_URL = "https://t.me/+NWathiLSqZ1lMzlh"
_LEGACY_MAIN_INVITE = "https://t.me/+" + "hMQzGs" + "BFjF02MDkx"
_LEGACY_MAIN_HANDLE = "aof" + "mainhub"

_STALE_MARKERS = (
    _LEGACY_MAIN_INVITE,
    _LEGACY_MAIN_HANDLE,
    "AOF Main",
    "Main Group",
    "MAIN COMMUNITY",
    "main hub",
    "main group",
    "private hub",
    "private Loot Room",
    "Daily promo / news",
)

_PROMO_BODY_MARKERS = (
    "The AOF network isn't standing still.",
    "the whole AOF map in one drop",
    "You see the posts. You don't see the engine.",
    "LOOT ROOM is the wildest lane",
    "Loot Bot is first contact",
)


def _tables(db: Session) -> set[str]:
    return set(inspect(db.get_bind()).get_table_names())


def _promo_defaults_by_title() -> dict[str, str]:
    return {
        (item.get("title") or "").strip(): (item.get("body") or "").strip()
        for item in AOF_X_PROMO_DEFAULTS
        if (item.get("title") or "").strip() and (item.get("body") or "").strip()
    }


def has_stale_public_copy(text: str | None) -> bool:
    blob = str(text or "")
    if not blob:
        return False
    low = blob.lower()
    return any(marker.lower() in low for marker in _STALE_MARKERS)


def replace_stale_public_copy(text: str | None) -> tuple[str, int]:
    out = str(text or "")
    if not out:
        return out, 0
    before = out
    replacements = (
        (_LEGACY_MAIN_INVITE, LOOT_ROOM_PUBLIC_URL),
        (_LEGACY_MAIN_HANDLE, "aof_lootgod_bot"),
        ("https://t.me/aof_lootgod_bot", LOOT_BOT_FREE_PULL_URL),
        ("AOF Main Hub", "AOF Loot Room"),
        ("AOF Main", "AOF VIP"),
        ("AOF MAIN GROUP", "AOF LOOT ROOM"),
        ("AOF MAIN", "AOF LOOT ROOM"),
        ("Main Group", "Loot Room"),
        ("MAIN COMMUNITY", "PUBLIC ENTRY"),
        ("main group", "Loot Room"),
        ("Main hub", "Loot entry"),
        ("main hub", "Loot entry"),
        ("Private hub", "Loot entry"),
        ("private hub", "Loot entry"),
        ("private Loot Room", "Loot Room"),
        ("Daily promo / news", "Public commons feed"),
    )
    for old, new in replacements:
        out = out.replace(old, new)
    return out, int(out != before)


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _promo_slot(slot: str) -> bool:
    if has_stale_public_copy(slot):
        return True
    return any(marker in slot for marker in _PROMO_BODY_MARKERS)


def _refresh_promo_slots(raw: str | None) -> tuple[str | None, int]:
    slots = [str(x) if x is not None else "" for x in _parse_json_list(raw)]
    defaults = [body for body in _promo_defaults_by_title().values() if body]
    if not defaults:
        return raw, 0

    promo_slots = [s for s in slots if _promo_slot(s)]
    if not promo_slots:
        return raw, 0

    custom = [s for s in slots if not _promo_slot(s)]
    updated = defaults + custom
    return json.dumps(updated), len(promo_slots)


def _replace_json_strings(value: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return replace_stale_public_copy(value)
    if isinstance(value, list):
        changed = 0
        out = []
        for item in value:
            new_item, n = _replace_json_strings(item)
            changed += n
            out.append(new_item)
        return out, changed
    if isinstance(value, dict):
        changed = 0
        out = {}
        for key, item in value.items():
            new_item, n = _replace_json_strings(item)
            changed += n
            out[key] = new_item
        return out, changed
    return value, 0


def _replace_json_column(raw: str | None) -> tuple[str | None, int]:
    if not raw:
        return raw, 0
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw, 0
    new_value, changes = _replace_json_strings(parsed)
    if not changes:
        return raw, 0
    return json.dumps(new_value), changes


def _queue_is_stale(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if has_stale_public_copy(str(item.get("text") or "")):
            return True
    return False


def refresh_caption_snippets(db: Session, *, execute: bool) -> dict[str, Any]:
    if "caption_snippets" not in _tables(db):
        return {"available": False, "updated": 0, "rows": []}
    defaults = _promo_defaults_by_title()
    rows: list[dict[str, Any]] = []
    for row in db.query(CaptionSnippet).filter(CaptionSnippet.title.in_(defaults.keys())).all():
        title = (row.title or "").strip()
        new_body = defaults.get(title, "")
        if not new_body or (row.body or "").strip() == new_body:
            continue
        rows.append({"id": row.id, "title": title})
        if execute:
            row.body = new_body[:16000]
    return {"available": True, "updated": len(rows) if execute else 0, "would_update": len(rows), "rows": rows}


def refresh_relay_copy_blocks(db: Session, *, execute: bool) -> dict[str, Any]:
    if "listening_relay_settings" not in _tables(db):
        return {"available": False, "updated": False, "replaced_slots": 0}
    row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
    if row is None:
        return {"available": True, "updated": False, "replaced_slots": 0, "missing": True}
    updated_raw, replaced = _refresh_promo_slots(row.message_copy_block_variations)
    if execute and replaced:
        row.message_copy_block_variations = updated_raw
        if int(row.message_template_rotation_index or 0) < 0:
            row.message_template_rotation_index = 0
    return {
        "available": True,
        "updated": bool(execute and replaced),
        "would_update": bool(replaced),
        "replaced_slots": replaced,
    }


def refresh_buffer_queues(db: Session, *, execute: bool) -> dict[str, Any]:
    items = build_armory_queue_items()
    report: dict[str, Any] = {
        "relay_would_update": False,
        "relay_updated": False,
        "scheduled_would_update": 0,
        "scheduled_updated": 0,
        "items": len(items),
    }
    if not items:
        return report

    tables = _tables(db)
    if "listening_relay_settings" in tables:
        relay = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
        if relay and _queue_is_stale(relay.get_buffer_x_queue()):
            report["relay_would_update"] = True
            if execute:
                relay.set_buffer_x_queue(items)
                report["relay_updated"] = True

    if "scheduled_text_posts" in tables:
        for post in db.query(ScheduledTextPost).all():
            if not _queue_is_stale(post.get_buffer_x_queue()):
                continue
            report["scheduled_would_update"] += 1
            if execute:
                post.set_buffer_x_queue(items)
                report["scheduled_updated"] += 1
    return report


def sweep_scheduled_public_copy(db: Session, *, execute: bool) -> dict[str, Any]:
    if "scheduled_text_posts" not in _tables(db):
        return {"available": False, "rows": 0, "would_update": 0, "updated": 0, "field_changes": 0}
    report = {"available": True, "rows": 0, "would_update": 0, "updated": 0, "field_changes": 0}
    for row in db.query(ScheduledTextPost).all():
        report["rows"] += 1
        changed = 0
        new_content, n = replace_stale_public_copy(row.content)
        changed += n
        new_vars, n = _replace_json_column(row.content_variations)
        changed += n
        new_buttons, n = _replace_json_column(row.buttons)
        changed += n
        new_surface, n = _replace_json_column(row.surface_copy_json)
        changed += n
        if not changed:
            continue
        report["would_update"] += 1
        report["field_changes"] += changed
        if execute:
            row.content = new_content
            row.content_variations = new_vars
            row.buttons = new_buttons
            row.surface_copy_json = new_surface
            report["updated"] += 1
    return report


def apply_public_copy_cutover(db: Session, *, execute: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {"execute": execute}
    for key, fn in (
        ("caption_snippets", refresh_caption_snippets),
        ("relay_copy_blocks", refresh_relay_copy_blocks),
        ("buffer_queues", refresh_buffer_queues),
        ("scheduled_public_copy", sweep_scheduled_public_copy),
    ):
        report[key] = fn(db, execute=execute)
        if execute:
            db.commit()
        else:
            db.rollback()
    db.expire_all()
    return report
