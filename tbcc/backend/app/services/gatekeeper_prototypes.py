"""Online per-lane CLIP embedding prototype bank — pure Python, no GPU fine-tune.

Gold labels: hub-topic deposits and operator approvals are positive; operator
reject writes a ``lanes=[]`` row and never moves a centroid. Age/zoo/seller
hard-block items are never labeled at all. Centroid = running sum / count per
lane, recomputed by exactly ONE full-table scan on a Redis cache miss — never
rebuilt on a timer, never trimmed-mean/variance (explicitly rejected in the
locked design). See docs/handoffs/2026-08-17_gatekeeper-lane-split-train.md.

No numpy — it is not a declared backend dependency (only present here
transitively), so centroid math is plain Python floats/lists to keep this
working on a lean island deploy.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CENTROID_REDIS_KEY = "tbcc:gk:centroids"
CENTROID_TTL_SECONDS = 86400


def prototype_min() -> int:
    raw = (os.getenv("TBCC_GATEKEEPER_PROTOTYPE_MIN") or "8").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na, nb = _norm(a), _norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return _dot(a, b) / (na * nb)


# ---------------------------------------------------------------------------
# Centroid cache — ONE full scan on a cache miss, invalidated on every
# embedding-bearing write. TTL is a safety net only, not the invalidation
# strategy (locked design B).
# ---------------------------------------------------------------------------


def _cache_get_sums() -> dict[str, dict[str, Any]] | None:
    try:
        raw = _redis().get(CENTROID_REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("centroid cache read failed", exc_info=True)
        return None


def _cache_set_sums(sums: dict[str, dict[str, Any]]) -> None:
    try:
        _redis().set(CENTROID_REDIS_KEY, json.dumps(sums), ex=CENTROID_TTL_SECONDS)
    except Exception:
        logger.debug("centroid cache write failed", exc_info=True)


def _cache_invalidate() -> None:
    try:
        _redis().delete(CENTROID_REDIS_KEY)
    except Exception:
        logger.debug("centroid cache invalidate failed", exc_info=True)


def _scan_running_sums(db: Session) -> dict[str, dict[str, Any]]:
    """ONE full-table scan (cache-miss path only) -> per-lane running sum + count."""
    from app.models.gatekeeper_lane_label import GatekeeperLaneLabel

    sums: dict[str, dict[str, Any]] = {}
    rows = (
        db.query(GatekeeperLaneLabel)
        .filter(GatekeeperLaneLabel.embedding_json.isnot(None))
        .all()
    )
    for row in rows or []:
        try:
            lanes = json.loads(row.lanes_json or "[]")
            vec = json.loads(row.embedding_json or "null")
        except Exception:
            continue
        if not isinstance(lanes, list) or not isinstance(vec, list) or not vec:
            continue
        try:
            vec = [float(v) for v in vec]
        except (TypeError, ValueError):
            continue
        for lane in lanes:
            lane = str(lane or "").strip().lower()
            if not lane:
                continue
            bucket = sums.setdefault(lane, {"sum": [0.0] * len(vec), "count": 0})
            if len(bucket["sum"]) != len(vec):
                continue  # dim mismatch guard — skip malformed row
            bucket["sum"] = [s + v for s, v in zip(bucket["sum"], vec)]
            bucket["count"] += 1
    return sums


def maybe_recalc(db: Session) -> dict[str, dict[str, Any]]:
    """Cache-hit -> return cached sums untouched. Cache-miss -> the one allowed
    full scan, then cache. Never a periodic job."""
    cached = _cache_get_sums()
    if cached is not None:
        return cached
    sums = _scan_running_sums(db)
    _cache_set_sums(sums)
    return sums


def load_centroids(db: Session) -> dict[str, list[float]]:
    """Per-lane centroid = running sum / count, only for lanes with >= PROTOTYPE_MIN labels."""
    sums = maybe_recalc(db)
    min_count = prototype_min()
    centroids: dict[str, list[float]] = {}
    for lane, bucket in sums.items():
        count = int(bucket.get("count") or 0)
        if count < min_count:
            continue
        vec = bucket.get("sum") or []
        if not vec:
            continue
        centroids[lane] = [v / count for v in vec]
    return centroids


def score_embedding(db: Session, vec: list[float]) -> list[tuple[str, float]]:
    """Ranked (lane, cosine) against every lane that has cleared PROTOTYPE_MIN labels."""
    centroids = load_centroids(db)
    scores = [(lane, cosine_similarity(vec, centroid)) for lane, centroid in centroids.items()]
    return sorted(scores, key=lambda kv: kv[1], reverse=True)


# ---------------------------------------------------------------------------
# Gold label recording
# ---------------------------------------------------------------------------


def _classification_gatekeeper(media: Any) -> dict[str, Any]:
    raw = getattr(media, "classification_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    gk = data.get("gatekeeper") if isinstance(data, dict) else None
    return gk if isinstance(gk, dict) else {}


def media_is_hard_blocked(media: Any) -> bool:
    """Age-adjacent / zoo / seller-proof items are never labeled — locked design C."""
    gk = _classification_gatekeeper(media)
    if str(gk.get("verdict") or "").strip().lower() == "reject":
        return True
    flags = list(gk.get("blocks") or []) + list(gk.get("warnings") or [])
    return any(str(f).startswith("hard_block:") for f in flags)


def _already_recorded(db: Session, *, file_unique_id: str, source: str, has_embedding: bool) -> bool:
    """Dedupe guard: apply_gatekeeper_after_ingest runs twice per item (ingest,
    then the CLIP-enriched pass), so the embedding-less hub_topic hook would
    otherwise write a duplicate row every time. One row per
    (file_unique_id, source, embedding-presence) is enough — the embedding
    upgrade (caption-only -> embedding-bearing) is still a distinct row."""
    from app.models.gatekeeper_lane_label import GatekeeperLaneLabel

    try:
        existing = (
            db.query(GatekeeperLaneLabel)
            .filter(GatekeeperLaneLabel.file_unique_id == file_unique_id)
            .filter(GatekeeperLaneLabel.source == source)
            .all()
        )
    except Exception:
        logger.debug("gatekeeper label dedupe check failed file_unique_id=%s", file_unique_id, exc_info=True)
        # A failed query (e.g. table not yet migrated) can leave the session in
        # a failed-transaction state on Postgres — roll back so the caller's
        # session (shared with apply_gatekeeper_after_ingest / operator_approve_media)
        # isn't poisoned for whatever runs after this.
        try:
            db.rollback()
        except Exception:
            pass
        return False
    for row in existing or []:
        row_has_embedding = bool(getattr(row, "embedding_json", None))
        if row_has_embedding == has_embedding:
            return True
    return False


def record_label(
    db: Session,
    *,
    media_id: int | None,
    file_unique_id: str,
    lanes: list[str],
    source: str,
    embedding: list[float] | None = None,
    hard_block: bool = False,
) -> dict[str, Any]:
    """Write one gold-label row. Skips age/zoo hard-blocked items entirely —
    never persisted under any source, positive or negative."""
    if hard_block:
        return {"ok": False, "skipped": True, "reason": "hard_block"}
    fid = (file_unique_id or "").strip()
    if not fid:
        return {"ok": False, "skipped": True, "reason": "no_file_unique_id"}

    has_embedding = bool(embedding)
    if _already_recorded(db, file_unique_id=fid, source=source, has_embedding=has_embedding):
        return {"ok": False, "skipped": True, "reason": "already_recorded"}

    from app.models.gatekeeper_lane_label import GatekeeperLaneLabel

    clean_lanes = sorted({(lane or "").strip().lower() for lane in (lanes or []) if (lane or "").strip()})
    vec = [float(v) for v in embedding] if embedding else None

    row = GatekeeperLaneLabel(
        media_id=int(media_id) if media_id else None,
        file_unique_id=fid,
        lanes_json=json.dumps(clean_lanes),
        source=source,
        embedding_json=json.dumps(vec) if vec else None,
        dim=len(vec) if vec else None,
        created_at=datetime.now(timezone.utc),
    )
    try:
        db.add(row)
        db.commit()
    except Exception:
        logger.debug("gatekeeper label write failed file_unique_id=%s", fid, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "skipped": True, "reason": "write_failed"}

    if vec and clean_lanes:
        _cache_invalidate()

    return {"ok": True, "id": getattr(row, "id", None), "lanes": clean_lanes, "has_embedding": bool(vec)}
