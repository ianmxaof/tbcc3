"""Mirror MEGA pack destinations to Keep2Share and annotate loot modifiers."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.loot import LootModifier
from app.services.aof_packs_post_copy import parse_pack_source_note
from app.services.keep2share_client import (
    K2sNotConfiguredError,
    is_k2s_host,
    move_files_to_folder,
    public_file_url,
    remote_upload_add,
    wait_remote_upload,
)
from app.services.k2s_lane_folders import get_lane_folder_id, infer_lane_from_text, mirror_enabled
from app.services.mega_link_extract import classify_url_host

logger = logging.getLogger(__name__)

_K2S_FILE_ID_RE = re.compile(r"\|k2s_file_id=([^|]+)")
_K2S_URL_RE = re.compile(r"\|k2s_url=([^|]+)")
_K2S_LANE_RE = re.compile(r"\|k2s_lane=([^|]+)")
_K2S_MIRROR_RE = re.compile(r"\|k2s_mirror=(pending|done|failed)(?:\|[^|]*)?")


def _is_mega_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return "mega.nz" in host or "mega.co.nz" in host


def parse_k2s_tokens(note: str | None) -> dict[str, str | None]:
    raw = note or ""
    def _m(pattern: re.Pattern[str]) -> str | None:
        m = pattern.search(raw)
        return m.group(1).strip() if m else None

    return {
        "k2s_file_id": _m(_K2S_FILE_ID_RE),
        "k2s_url": _m(_K2S_URL_RE),
        "k2s_lane": _m(_K2S_LANE_RE),
        "k2s_mirror": _m(_K2S_MIRROR_RE),
    }


def merge_k2s_source_note(
    note: str,
    *,
    k2s_file_id: str | None = None,
    k2s_url: str | None = None,
    k2s_lane: str | None = None,
    k2s_mirror: str | None = None,
) -> str:
    base = (note or "").strip()
    for pattern in (_K2S_FILE_ID_RE, _K2S_URL_RE, _K2S_LANE_RE, _K2S_MIRROR_RE):
        base = pattern.sub("", base)
    if k2s_file_id:
        base = f"{base}|k2s_file_id={k2s_file_id[:32]}"
    if k2s_url:
        base = f"{base}|k2s_url={k2s_url[:200]}"
    if k2s_lane:
        base = f"{base}|k2s_lane={k2s_lane[:32]}"
    if k2s_mirror:
        base = f"{base}|k2s_mirror={k2s_mirror[:32]}"
    return base[:2000]


def destination_url_from_modifier(mod: LootModifier) -> str | None:
    meta = parse_pack_source_note(mod.source_note)
    if meta.destination_url:
        return meta.destination_url
    for token in (mod.source_note or "").split("|"):
        if token.startswith("dest="):
            return token[5:].strip() or None
    return None


def should_mirror_modifier(mod: LootModifier) -> tuple[bool, str | None]:
    if not mirror_enabled():
        return False, "mirror_disabled"
    if (mod.kind or "").strip().lower() != "mega_pack":
        return False, "not_mega_pack"
    tokens = parse_k2s_tokens(mod.source_note)
    if tokens.get("k2s_file_id") and tokens.get("k2s_mirror") == "done":
        return False, "already_mirrored"
    if tokens.get("k2s_mirror") == "pending":
        return False, "mirror_pending"
    dest = destination_url_from_modifier(mod)
    if not dest:
        return False, "no_destination"
    if is_k2s_host(dest):
        return False, "already_k2s"
    if not _is_mega_url(dest):
        return False, "not_mega"
    return True, None


def mirror_source_url_to_k2s(
    source_url: str,
    *,
    lane: str = "packs",
    label: str | None = None,
) -> dict[str, Any]:
    """Remote-upload one URL and optionally file into lane folder."""
    url = (source_url or "").strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "invalid_url"}
    if not mirror_enabled():
        return {"ok": False, "error": "mirror_disabled"}
    lane_key = (lane or "packs").strip().lower()
    folder_id = get_lane_folder_id(lane_key, create=True)
    try:
        accepted, rejected = remote_upload_add([url])
    except K2sNotConfiguredError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not accepted:
        return {"ok": False, "error": "upload_rejected", "rejected": rejected}
    remote_id = accepted[0]["id"]
    result = wait_remote_upload(remote_id)
    if not result.ok or not result.file_id:
        return {
            "ok": False,
            "error": result.error or "mirror_failed",
            "remote_id": remote_id,
        }
    if folder_id:
        move_files_to_folder([result.file_id], folder_id)
    pub = result.public_url or public_file_url(result.file_id)
    return {
        "ok": True,
        "k2s_file_id": result.file_id,
        "k2s_url": pub,
        "k2s_lane": lane_key,
        "remote_id": remote_id,
        "label": label,
    }


def apply_mirror_result_to_modifier(db: Session, mod: LootModifier, mirror: dict[str, Any]) -> LootModifier:
    if mirror.get("ok"):
        note = merge_k2s_source_note(
            mod.source_note or "",
            k2s_file_id=str(mirror.get("k2s_file_id") or ""),
            k2s_url=str(mirror.get("k2s_url") or ""),
            k2s_lane=str(mirror.get("k2s_lane") or ""),
            k2s_mirror="done",
        )
    else:
        err = str(mirror.get("error") or "failed")[:40]
        note = merge_k2s_source_note(mod.source_note or "", k2s_mirror=f"failed:{err}")
    mod.source_note = note[:2000]
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return mod


def mirror_modifier_by_id(db: Session, modifier_id: int, *, lane: str | None = None) -> dict[str, Any]:
    mod = db.query(LootModifier).filter(LootModifier.id == int(modifier_id)).first()
    if not mod:
        return {"ok": False, "error": "modifier_not_found"}
    ok, reason = should_mirror_modifier(mod)
    if not ok and reason not in ("mirror_pending",):
        return {"ok": False, "skipped": True, "reason": reason, "modifier_id": mod.id}
    dest = destination_url_from_modifier(mod)
    if not dest:
        return {"ok": False, "error": "no_destination"}
    lane_key = lane or parse_k2s_tokens(mod.source_note).get("k2s_lane")
    if not lane_key:
        lane_key = infer_lane_from_text(mod.label, mod.source_note, mod.kind)
    mod.source_note = merge_k2s_source_note(mod.source_note or "", k2s_lane=lane_key, k2s_mirror="pending")
    db.add(mod)
    db.commit()
    result = mirror_source_url_to_k2s(dest, lane=lane_key, label=mod.label)
    apply_mirror_result_to_modifier(db, mod, result)
    out = dict(result)
    out["modifier_id"] = mod.id
    return out


def maybe_enqueue_k2s_mirror(
    modifier_id: int,
    *,
    lane: str | None = None,
    label: str | None = None,
    source_note: str | None = None,
) -> bool:
    if not mirror_enabled():
        return False
    lane_key = lane or infer_lane_from_text(label, source_note)
    try:
        from app.workers.k2s_mirror_worker import mirror_pack_to_k2s

        mirror_pack_to_k2s.delay(int(modifier_id), lane_key)
        return True
    except Exception as e:
        logger.warning("k2s mirror enqueue failed mod=%s: %s", modifier_id, e)
        return False


def check_file_host_url(url: str) -> dict[str, Any]:
    """Unified dead-link probe for ingest ops."""
    u = (url or "").strip()
    if not u.startswith("http"):
        return {"ok": False, "error": "invalid_url"}
    kind = classify_url_host(u)
    if is_k2s_host(u):
        from app.services.keep2share_client import check_url_alive, parse_k2s_file_id

        alive, reason = check_url_alive(u)
        return {
            "ok": alive,
            "host_kind": "k2s",
            "file_id": parse_k2s_file_id(u),
            "reason": reason,
        }
    from app.services.mega_link_pipeline import validate_file_host_has_content

    ok, reason = validate_file_host_has_content(u)
    return {"ok": ok, "host_kind": kind, "reason": reason}
