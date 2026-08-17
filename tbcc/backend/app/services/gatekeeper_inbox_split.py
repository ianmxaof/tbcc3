"""Mixed-bulk AOF INBOX split — classify per item, auto-route when confident.

Consumes the caption/CLIP lane signal built in Phase 1
(``app.data.clip_slug_lane_map``) plus real per-slug CLIP scores (never a
bare slug list — see ``resolve_proposed_lanes``) to implement locked rule E
from ``docs/handoffs/2026-08-17_gatekeeper-lane-split-train.md``:

- Confident single lane -> approve + route into the Storage Hub lane topic
  (same Telethon path as an operator approve: ``enqueue_lane_route_for_media``).
- Two+ strong lanes, or low confidence -> quarantine stays quarantine;
  ``set_picked_lanes`` preselects the review card so the operator taps once.
- Hard-blocked (age/zoo/seller) or scrape-origin media never auto-routes.

No Telethon calls happen in this module — ``enqueue_lane_route_for_media``
defers the actual forward to the existing Celery task. This runs inline from
``media_gatekeeper.apply_gatekeeper_after_ingest``, which is already called
twice per Storage Hub inbox deposit: once at ingest (caption only) and again
from ``auto_tag_enrich`` once CLIP labels are available (if enrich is on).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_SPLIT_MARK_PREFIX = "tbcc:gk:inbox_split"
_SPLIT_MARK_TTL_SECONDS = 86400 * 30


def inbox_split_enabled() -> bool:
    return (os.getenv("TBCC_GATEKEEPER_INBOX_SPLIT") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def auto_split_min() -> float:
    try:
        return float(os.getenv("TBCC_GATEKEEPER_AUTO_SPLIT_MIN") or "0.28")
    except ValueError:
        return 0.28


def auto_split_margin() -> float:
    try:
        return float(os.getenv("TBCC_GATEKEEPER_AUTO_SPLIT_MARGIN") or "0.04")
    except ValueError:
        return 0.04


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _split_mark_key(media_id: int) -> str:
    return f"{_SPLIT_MARK_PREFIX}:{int(media_id)}"


def _split_already_routed(media_id: int) -> bool:
    """True once auto-route has actually forwarded this item — guards against a
    duplicate Telegram forward when apply_gatekeeper_after_ingest runs a second
    time (e.g. the later CLIP-enriched pass from auto_tag_enrich)."""
    try:
        return bool(_redis().get(_split_mark_key(media_id)))
    except Exception:
        logger.debug("inbox split marker read failed media_id=%s", media_id, exc_info=True)
        return False


def _mark_split_routed(media_id: int) -> None:
    try:
        _redis().set(_split_mark_key(media_id), "1", ex=_SPLIT_MARK_TTL_SECONDS)
    except Exception:
        logger.debug("inbox split marker write failed media_id=%s", media_id, exc_info=True)


def _classification_dict(media: Any) -> dict[str, Any]:
    raw = getattr(media, "classification_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _classification_gatekeeper(media: Any) -> dict[str, Any]:
    gk = _classification_dict(media).get("gatekeeper")
    return gk if isinstance(gk, dict) else {}


def _parse_clip_labels(enrich: dict[str, Any] | None) -> tuple[list[str], dict[str, float]]:
    clip_labels = (enrich or {}).get("clip_labels") or []
    scores_map: dict[str, float] = {}
    slugs: list[str] = []
    for row in clip_labels:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        try:
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        slugs.append(slug)
        scores_map[slug] = score
    return slugs, scores_map


def _clip_top_lane(enrich: dict[str, Any] | None) -> str | None:
    from app.data.clip_slug_lane_map import map_clip_slugs_to_lanes

    slugs, scores_map = _parse_clip_labels(enrich)
    if not slugs:
        return None
    ranked = map_clip_slugs_to_lanes(slugs, scores=scores_map)
    return ranked[0][0] if ranked else None


def clip_and_prototype_top_lanes(
    enrich: dict[str, Any] | None, prototype_scores: list[tuple[str, float]] | None
) -> tuple[str | None, str | None]:
    """Top lane from CLIP-only ranking vs. top lane from the prototype bank —
    the pair rule E's agreement boost / disagreement guard compares."""
    proto_ranked = prototype_scores or []
    proto_top = proto_ranked[0][0] if proto_ranked else None
    return _clip_top_lane(enrich), proto_top


def prototype_disagrees_with_clip(
    enrich: dict[str, Any] | None, prototype_scores: list[tuple[str, float]] | None
) -> bool:
    clip_top, proto_top = clip_and_prototype_top_lanes(enrich, prototype_scores)
    return bool(clip_top) and bool(proto_top) and clip_top != proto_top


def resolve_proposed_lanes(
    media: Any,
    enrich: dict[str, Any] | None,
    caption: str,
    *,
    prototype_scores: list[tuple[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Ranked AOF split lanes blended from caption + real-scored CLIP labels +
    (Phase 3) the prototype bank, when centroids exist for enough lanes.

    ``enrich.clip_labels`` must be ``[{"slug": str, "score": float}, ...]`` —
    real per-slug CLIP confidence from the sidecar. A bare slug list is never
    accepted here; callers that only have slugs with no score should not pass
    ``clip_labels`` at all (caption-only signal still works via ``map_text_to_lanes``).

    ``prototype_scores`` — ranked ``[(lane, cosine), ...]`` from
    ``gatekeeper_prototypes.score_embedding`` — is caller-supplied rather than
    computed here so this stays a pure function with no DB/Redis access, and so
    callers only pay for a centroid load when a CLIP embedding is actually in
    hand (never on the caption-only ingest-time pass).
    """
    from app.data.clip_slug_lane_map import caption_confidence, map_clip_slugs_to_lanes, map_text_to_lanes

    filename = str(getattr(media, "filename", "") or "")
    lane_rows: dict[str, dict[str, Any]] = {}

    conf = caption_confidence(caption, filename)
    if conf > 0:
        for lane in map_text_to_lanes(caption, filename):
            lane_rows[lane] = {"lane": lane, "score": conf, "source": "caption"}

    slugs, scores_map = _parse_clip_labels(enrich)
    clip_ranked = map_clip_slugs_to_lanes(slugs, scores=scores_map) if slugs else []
    clip_top_lane = clip_ranked[0][0] if clip_ranked else None
    for lane, score in clip_ranked:
        existing = lane_rows.get(lane)
        if existing is None:
            lane_rows[lane] = {"lane": lane, "score": score, "source": "clip"}
        elif score > existing["score"]:
            lane_rows[lane] = {"lane": lane, "score": score, "source": "mixed"}
        else:
            existing["source"] = "mixed"

    proto_ranked = prototype_scores or []
    proto_top_lane = proto_ranked[0][0] if proto_ranked else None
    for lane, score in proto_ranked:
        existing = lane_rows.get(lane)
        if existing is None:
            lane_rows[lane] = {"lane": lane, "score": score, "source": "prototype"}
        elif score > existing["score"]:
            lane_rows[lane] = {"lane": lane, "score": score, "source": "mixed"}
        else:
            existing["source"] = "mixed"

    agree = bool(clip_top_lane) and bool(proto_top_lane) and clip_top_lane == proto_top_lane
    if agree and clip_top_lane in lane_rows:
        boosted = min(1.0, float(lane_rows[clip_top_lane]["score"]) * 1.15)
        lane_rows[clip_top_lane]["score"] = boosted

    return sorted(lane_rows.values(), key=lambda row: row["score"], reverse=True)


def _is_hard_blocked(gk: dict[str, Any]) -> bool:
    if str(gk.get("verdict") or "").strip().lower() == "reject":
        return True
    flags = list(gk.get("blocks") or []) + list(gk.get("warnings") or [])
    return any(str(f).startswith("hard_block:") for f in flags)


def _apply_auto_route(db: Session, media: Any, lane: str) -> None:
    from app.services.export_flywheel_service import pool_id_for_network_key
    from app.services.gatekeeper_review import enqueue_lane_route_for_media

    media.status = "approved"
    pid = pool_id_for_network_key(db, lane)
    if pid:
        media.pool_id = int(pid)
    data = _classification_dict(media)
    data["gatekeeper_split"] = {
        "action": "auto_route",
        "lane": lane,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    media.classification_json = json.dumps(data, ensure_ascii=False)
    db.commit()
    enqueue_lane_route_for_media(int(media.id), [lane])


def maybe_auto_split_inbox(
    db: Session,
    media_id: int,
    *,
    caption: str = "",
    enrich: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rule E — auto-route when confident, else preselect lanes for the operator."""
    from app.models.media import Media
    from app.services.gatekeeper_lane_picker import set_picked_lanes
    from app.services.media_gatekeeper import INGEST_ORIGIN_STORAGE_HUB, resolve_ingest_origin

    if not inbox_split_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled", "media_id": media_id}

    media = db.query(Media).filter(Media.id == int(media_id)).first()
    if not media:
        return {"ok": False, "skipped": True, "reason": "not_found", "media_id": media_id}

    gk = _classification_gatekeeper(media)
    lane_fit = (gk.get("globs") or {}).get("lane_fit") or {}
    expected = str(lane_fit.get("expected") or "").strip().lower()
    if expected != "inbox":
        return {"ok": False, "skipped": True, "reason": "not_inbox", "media_id": media_id}

    origin = resolve_ingest_origin(db, source_channel=getattr(media, "source_channel", None))
    if origin != INGEST_ORIGIN_STORAGE_HUB:
        return {"ok": False, "skipped": True, "reason": "not_trusted_hub_origin", "media_id": media_id}

    if _is_hard_blocked(gk):
        return {"ok": False, "skipped": True, "reason": "hard_block", "media_id": media_id}

    # Prototype scoring only when a real CLIP embedding is in hand — never on
    # the caption-only ingest-time pass, so a bulk dump doesn't force a
    # centroid load (full table scan on a Redis cache miss) per item.
    embedding = (enrich or {}).get("clip_embedding")
    prototype_scores: list[tuple[str, float]] | None = None
    if isinstance(embedding, list) and embedding:
        try:
            from app.services.gatekeeper_prototypes import score_embedding

            prototype_scores = score_embedding(db, embedding)
        except Exception:
            logger.debug("prototype score skipped media_id=%s", media_id, exc_info=True)
            prototype_scores = None

    proposed = resolve_proposed_lanes(media, enrich, caption, prototype_scores=prototype_scores)
    if not proposed:
        return {"ok": False, "skipped": True, "reason": "no_signal", "media_id": media_id}

    clip_top, proto_top = clip_and_prototype_top_lanes(enrich, prototype_scores)
    disagree = prototype_disagrees_with_clip(enrich, prototype_scores)

    top = proposed[0]
    second_score = float(proposed[1]["score"]) if len(proposed) > 1 else 0.0
    margin = float(top["score"]) - second_score
    # Disagreement is an override, not a missing boost — CLIP and the
    # prototype bank picking different top lanes must force the
    # non-auto-route path regardless of how the arithmetic lands.
    confident = (
        not disagree and float(top["score"]) >= auto_split_min() and margin >= auto_split_margin()
    )

    if confident:
        if _split_already_routed(media_id):
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_routed",
                "media_id": media_id,
                "proposed": proposed,
            }
        _mark_split_routed(media_id)
        _apply_auto_route(db, media, str(top["lane"]))
        return {
            "ok": True,
            "action": "auto_route",
            "lane": top["lane"],
            "score": top["score"],
            "margin": margin,
            "media_id": media_id,
            "proposed": proposed,
        }

    if disagree and clip_top and proto_top:
        lanes = sorted({clip_top, proto_top})
    else:
        strong = [row for row in proposed if float(row["score"]) >= auto_split_min()]
        lanes = [row["lane"] for row in (strong if len(strong) >= 2 else proposed)][:2]
    set_picked_lanes(int(media_id), lanes)
    return {
        "ok": True,
        "action": "quarantine_preselect",
        "lanes": lanes,
        "media_id": media_id,
        "proposed": proposed,
        "prototype_disagrees": disagree,
    }
