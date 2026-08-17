"""Apply media_gatekeeper_spec verdicts at ingest time."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.media_gatekeeper_spec import (
    MediaGatekeeperInput,
    MediaVerdict,
    evaluate_media,
    merge_gatekeeper_json,
)
from app.services.storage_deposit_auto_approve import is_storage_hub_source_label

logger = logging.getLogger(__name__)

INGEST_ORIGIN_SCRAPE = "scrape"
INGEST_ORIGIN_STORAGE_HUB = "storage_hub"
INGEST_ORIGIN_OTHER = "other"


def gatekeeper_enabled() -> bool:
    return (os.getenv("TBCC_MEDIA_GATEKEEPER_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def is_scrape_origin_source(db: Session, source_label: str | None) -> bool:
    """True when source_label matches a SCRP-named Source row (inbound scrape)."""
    ident = (source_label or "").strip()
    if not ident or ident.startswith("telegram:"):
        return False
    from app.models.source import Source

    row = (
        db.query(Source)
        .filter(Source.identifier == ident, Source.source_type == "telegram_channel")
        .first()
    )
    if not row:
        return False
    name = str(getattr(row, "name", "") or "").strip().upper()
    return name.startswith("SCRP") or name.startswith("SCRP [")


def resolve_ingest_origin(
    db: Session,
    *,
    source_channel: str | None,
    source_label: str | None = None,
) -> str:
    if is_storage_hub_source_label(source_channel):
        return INGEST_ORIGIN_STORAGE_HUB
    if is_scrape_origin_source(db, source_label or source_channel):
        return INGEST_ORIGIN_SCRAPE
    return INGEST_ORIGIN_OTHER


def source_trusted_for_gatekeeper(ingest_origin: str) -> bool:
    """Storage Hub deposits are operator-curated; scrape-origin is never trusted."""
    return ingest_origin == INGEST_ORIGIN_STORAGE_HUB


def expected_lane_for_pool(db: Session, pool_id: int | None) -> str | None:
    if not pool_id:
        return None
    from app.services.scrape_channel_intel import pool_key_for_pool_id

    key, _name = pool_key_for_pool_id(db, int(pool_id))
    return key


def expected_lane_for_storage_source(source_channel: str | None) -> str | None:
    """Parse network_key from telegram:-1003812457581#topic:3779 style labels."""
    raw = (source_channel or "").strip()
    if "#topic:" not in raw.lower():
        return None
    try:
        tid = int(raw.rsplit(":", 1)[-1])
    except ValueError:
        return None
    from app.data.aof_storage_hub_map import network_key_for_storage_topic

    return network_key_for_storage_topic(tid)


def telegram_message_metadata(message: Any | None) -> dict[str, Any]:
    """Best-effort caption + dimensions from a Telethon Message."""
    out: dict[str, Any] = {
        "caption": "",
        "width": None,
        "height": None,
        "duration_seconds": None,
        "filesize_bytes": None,
        "is_letterbox": False,
    }
    if message is None:
        return out
    out["caption"] = str(
        getattr(message, "message", None) or getattr(message, "text", None) or ""
    )
    media = getattr(message, "media", None)
    if media is None:
        return out
    try:
        from telethon.tl.types import (
            DocumentAttributeVideo,
            MessageMediaDocument,
            MessageMediaPhoto,
        )
    except ImportError:
        return out

    if isinstance(media, MessageMediaPhoto):
        sizes = getattr(media.photo, "sizes", None) or []
        best_w = best_h = 0
        for sz in sizes:
            w = getattr(sz, "w", None) or getattr(sz, "width", None)
            h = getattr(sz, "h", None) or getattr(sz, "height", None)
            if w and h and int(w) * int(h) > best_w * best_h:
                best_w, best_h = int(w), int(h)
        if best_w and best_h:
            out["width"] = best_w
            out["height"] = best_h
    elif isinstance(media, MessageMediaDocument):
        doc = media.document
        if doc:
            out["filesize_bytes"] = getattr(doc, "size", None)
            for attr in getattr(doc, "attributes", None) or []:
                if isinstance(attr, DocumentAttributeVideo):
                    out["duration_seconds"] = float(getattr(attr, "duration", 0) or 0)
                    out["width"] = int(getattr(attr, "w", 0) or 0) or None
                    out["height"] = int(getattr(attr, "h", 0) or 0) or None
                    break
    w, h = out.get("width"), out.get("height")
    if w and h and int(w) > int(h) * 1.35:
        out["is_letterbox"] = True
    return out


def parse_source_channel_id(source_label: str | None) -> int | None:
    raw = (source_label or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def gatekeeper_verdict_from_media(media: Any) -> str | None:
    raw = getattr(media, "classification_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            gk = data.get("gatekeeper")
            if isinstance(gk, dict):
                v = (gk.get("verdict") or "").strip().lower()
                return v or None
    except Exception:
        return None
    return None


def build_gatekeeper_input(
    db: Session,
    media: Any,
    *,
    caption: str = "",
    message: Any | None = None,
    source_label: str | None = None,
    enrich: dict[str, Any] | None = None,
) -> MediaGatekeeperInput:
    meta = telegram_message_metadata(message)
    cap = (caption or meta.get("caption") or "").strip()
    origin = resolve_ingest_origin(
        db,
        source_channel=getattr(media, "source_channel", None),
        source_label=source_label,
    )
    trusted = source_trusted_for_gatekeeper(origin)
    expected = expected_lane_for_storage_source(getattr(media, "source_channel", None))
    if not expected:
        expected = expected_lane_for_pool(db, getattr(media, "pool_id", None))
    if not expected:
        from app.services.tbcc_caption_stamp import parse_tbcc_lane_from_caption

        expected = parse_tbcc_lane_from_caption(cap)

    enrich = enrich or {}
    nsfw_tier = enrich.get("nsfw_tier") or getattr(media, "nsfw_tier", None)
    clip_slug = enrich.get("clip_slug")
    clip_confident = bool(enrich.get("clip_confident"))

    source_id = parse_source_channel_id(source_label or getattr(media, "source_channel", None))

    return MediaGatekeeperInput(
        media_type=str(getattr(media, "media_type", "") or ""),
        caption=cap,
        filename="",
        source_channel_id=source_id,
        file_unique_id=str(getattr(media, "file_unique_id", "") or ""),
        expected_lane=expected,
        is_duplicate_in_pool=False,
        duration_seconds=meta.get("duration_seconds"),
        width=meta.get("width"),
        height=meta.get("height"),
        filesize_bytes=meta.get("filesize_bytes"),
        nsfw_tier=str(nsfw_tier) if nsfw_tier else None,
        clip_slug=str(clip_slug) if clip_slug else None,
        clip_confident=clip_confident,
        source_trusted=trusted,
        is_letterbox=bool(meta.get("is_letterbox")),
    )


def apply_verdict_to_media(db: Session, media: Any, verdict: MediaVerdict) -> None:
    existing: dict[str, Any] = {}
    raw = getattr(media, "classification_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            pass
    merged = merge_gatekeeper_json(existing, verdict)
    media.classification_json = json.dumps(merged, ensure_ascii=False)
    if verdict.verdict == "approve":
        media.status = "approved"
    elif verdict.verdict == "reject":
        media.status = "rejected"
    else:
        media.status = "pending"
    db.commit()


def apply_gatekeeper_after_ingest(
    db: Session,
    media_id: int,
    *,
    caption: str = "",
    message: Any | None = None,
    source_label: str | None = None,
    enrich: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run gatekeeper on a freshly indexed Media row."""
    from app.models.media import Media

    if not gatekeeper_enabled():
        return {"applied": False, "reason": "disabled", "media_id": media_id}

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"applied": False, "reason": "not_found", "media_id": media_id}

    origin = resolve_ingest_origin(
        db,
        source_channel=media.source_channel,
        source_label=source_label,
    )
    inp = build_gatekeeper_input(
        db,
        media,
        caption=caption,
        message=message,
        source_label=source_label,
        enrich=enrich,
    )
    verdict = evaluate_media(inp)
    apply_verdict_to_media(db, media, verdict)

    expected_lane_key = (inp.expected_lane or "").strip().lower()
    split_out: dict[str, Any] | None = None
    if expected_lane_key == "inbox":
        # Runs regardless of verdict — an untagged trusted-hub inbox deposit
        # already reaches approve on quality alone (no lane assigned), which
        # is the majority mixed-dump case. Split must not skip approved rows
        # or most of the dump never splits. Runs BEFORE the quarantine-review
        # enqueue below: auto-route already forwards + approves the item, so
        # a review card must not also go out for it (operator approve on that
        # card would re-forward since gatekeeper.verdict is untouched by the
        # split's sibling classification_json key).
        try:
            from app.services.gatekeeper_inbox_split import maybe_auto_split_inbox

            split_out = maybe_auto_split_inbox(db, int(media_id), caption=inp.caption, enrich=enrich)
        except Exception:
            logger.debug("inbox split skipped media_id=%s", media_id, exc_info=True)
    else:
        from app.data.clip_slug_lane_map import SPLIT_LANE_KEYS

        if expected_lane_key in SPLIT_LANE_KEYS:
            # Named-topic deposit -> expected_lane is gold (locked design C).
            # Caption-only here (no embedding); auto_tag_enrich adds an
            # embedding-bearing row once/if CLIP is available.
            try:
                from app.services.gatekeeper_prototypes import media_is_hard_blocked, record_label

                embedding = (enrich or {}).get("clip_embedding")
                record_label(
                    db,
                    media_id=int(media_id),
                    file_unique_id=str(getattr(media, "file_unique_id", "") or ""),
                    lanes=[expected_lane_key],
                    source="hub_topic",
                    embedding=embedding if isinstance(embedding, list) else None,
                    hard_block=media_is_hard_blocked(media),
                )
            except Exception:
                logger.debug("gold label record skipped media_id=%s", media_id, exc_info=True)

    split_routed = bool(split_out) and (
        split_out.get("action") == "auto_route" or split_out.get("reason") == "already_routed"
    )
    if verdict.verdict == "quarantine" and not split_routed:
        try:
            from app.services.gatekeeper_review import enqueue_quarantine_review

            enqueue_quarantine_review(int(media_id))
        except Exception:
            logger.debug("quarantine review enqueue skipped media_id=%s", media_id, exc_info=True)
    logger.info(
        "gatekeeper media_id=%s origin=%s verdict=%s score=%s",
        media_id,
        origin,
        verdict.verdict,
        verdict.quality_score,
    )
    return {
        "applied": True,
        "media_id": media_id,
        "ingest_origin": origin,
        **verdict.to_dict(),
    }


def should_attempt_storage_auto_approve(
    db: Session,
    media_id: int,
    *,
    source_label: str | None = None,
) -> bool:
    """Whether maybe_auto_approve_storage_deposit_media may run for this row."""
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return False
    if resolve_ingest_origin(
        db,
        source_channel=media.source_channel,
        source_label=source_label,
    ) == INGEST_ORIGIN_SCRAPE:
        return False
    if not is_storage_hub_source_label(media.source_channel):
        return False
    if not gatekeeper_enabled():
        return True
    verdict = gatekeeper_verdict_from_media(media)
    return verdict == "approve"
