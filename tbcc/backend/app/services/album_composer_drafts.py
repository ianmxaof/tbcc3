"""Persistent album composer workshop drafts (JSON on disk)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DRAFTS_PATH = _TBCC_ROOT / "data" / "album-composer-drafts.json"
_MAX_DRAFTS = 48


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_raw() -> dict[str, Any]:
    if not _DRAFTS_PATH.is_file():
        return {"drafts": []}
    try:
        data = json.loads(_DRAFTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("drafts"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"drafts": []}


def _write_raw(data: dict[str, Any]) -> None:
    _DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DRAFTS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def list_drafts() -> list[dict[str, Any]]:
    raw = _read_raw()
    drafts = [d for d in raw.get("drafts", []) if isinstance(d, dict)]
    drafts.sort(key=lambda d: str(d.get("updated_at") or d.get("created_at") or ""), reverse=True)
    return drafts[:_MAX_DRAFTS]


def get_draft(draft_id: str) -> dict[str, Any] | None:
    for d in list_drafts():
        if str(d.get("id")) == draft_id:
            return d
    return None


def save_draft(payload: dict[str, Any], *, draft_id: str | None = None) -> dict[str, Any]:
    raw = _read_raw()
    drafts = [d for d in raw.get("drafts", []) if isinstance(d, dict)]
    now = _now_iso()
    did = (draft_id or payload.get("id") or "").strip() or uuid.uuid4().hex[:12]
    row = {
        "id": did,
        "name": str(payload.get("name") or "Untitled draft")[:80],
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
        "items": payload.get("items") or [],
        "caption": str(payload.get("caption") or ""),
        "buttons": payload.get("buttons") or [],
        "promo_enabled": bool(payload.get("promo_enabled", True)),
        "send_silent": bool(payload.get("send_silent", False)),
        "channel_id": payload.get("channel_id"),
        "thread_id": payload.get("thread_id"),
        "crop": payload.get("crop"),
        "watermark_skip": bool(payload.get("watermark_skip", False)),
        "watermark_enabled": payload.get("watermark_enabled"),
        "watermark_text": str(payload.get("watermark_text") or ""),
        "watermark_text_secondary": str(payload.get("watermark_text_secondary") or ""),
        "watermark_text_tertiary": str(payload.get("watermark_text_tertiary") or ""),
        "watermark_opacity": payload.get("watermark_opacity"),
        "watermark_color": payload.get("watermark_color"),
        "watermark_strip_previous": payload.get("watermark_strip_previous"),
    }
    replaced = False
    for i, d in enumerate(drafts):
        if str(d.get("id")) == did:
            row["created_at"] = d.get("created_at") or now
            drafts[i] = row
            replaced = True
            break
    if not replaced:
        drafts.insert(0, row)
    drafts = drafts[:_MAX_DRAFTS]
    _write_raw({"drafts": drafts})
    return row


def delete_draft(draft_id: str) -> bool:
    raw = _read_raw()
    drafts = [d for d in raw.get("drafts", []) if isinstance(d, dict)]
    kept = [d for d in drafts if str(d.get("id")) != draft_id]
    if len(kept) == len(drafts):
        return False
    _write_raw({"drafts": kept})
    return True
