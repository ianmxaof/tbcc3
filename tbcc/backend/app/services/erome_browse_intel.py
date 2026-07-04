"""Ingest Erome browse-intel snapshots from Tampermonkey export or API POST."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.erome_upload_analytics import analytics_dir

logger = logging.getLogger(__name__)

_LEDGER_NAME = "browse-intel.jsonl"
_TIMESERIES_NAME = "market-intel-timeseries.jsonl"
_DROP_NAME = "browse-intel-drop.jsonl"
_DONE_SUFFIX = ".ingested"

_ALBUM_ID_RE = re.compile(r"/a/([^/?#]+)", re.I)


def browse_intel_enabled() -> bool:
    return (os.getenv("TBCC_EROME_BROWSE_INTEL_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def browse_intel_lookback_days() -> int:
    raw = (os.getenv("TBCC_EROME_BROWSE_INTEL_LOOKBACK_DAYS") or "30").strip()
    try:
        return max(1, min(180, int(raw)))
    except ValueError:
        return 30


def ledger_path() -> Path:
    return analytics_dir() / _LEDGER_NAME


def drop_path() -> Path:
    return analytics_dir() / _DROP_NAME


def timeseries_path() -> Path:
    return analytics_dir() / _TIMESERIES_NAME


def _append_timeseries(row: dict[str, Any]) -> None:
    path = timeseries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _album_id(url: str) -> str:
    m = _ALBUM_ID_RE.search(url or "")
    return (m.group(1) if m else "").strip().lower()


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    url = str(row.get("album_url") or row.get("url") or "").strip()
    if not url:
        return None
    album_id = str(row.get("album_id") or _album_id(url) or "").strip().lower()
    if not album_id:
        return None
    captured = _parse_ts(str(row.get("captured_at") or "")) or datetime.now(timezone.utc)
    views = row.get("views")
    likes = row.get("likes")
    try:
        views_i = int(views) if views is not None else None
    except (TypeError, ValueError):
        views_i = None
    try:
        likes_i = int(likes) if likes is not None else None
    except (TypeError, ValueError):
        likes_i = None
    tags_raw = row.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip().lower() for t in re.split(r"[,;]+", tags_raw) if t.strip()]
    else:
        tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]
    ctx = row.get("page_context") if isinstance(row.get("page_context"), dict) else {}
    engagement_bps = row.get("engagement_bps")
    if engagement_bps is None and views_i and likes_i:
        engagement_bps = int(round((likes_i / views_i) * 100_000))
    platform = str(row.get("platform") or "erome").strip().lower() or "erome"
    age_days = row.get("uploaded_at_approx_days_ago")
    try:
        age_days_f = float(age_days) if age_days is not None else None
    except (TypeError, ValueError):
        age_days_f = None
    vpd = row.get("views_per_day_proxy")
    if vpd is None and views_i and age_days_f and age_days_f > 0:
        vpd = round(views_i / age_days_f, 1)
    try:
        vpd_f = float(vpd) if vpd is not None else None
    except (TypeError, ValueError):
        vpd_f = None
    media_seq = row.get("media_sequence")
    if isinstance(media_seq, list):
        media_seq = [str(x).strip().lower() for x in media_seq if str(x).strip()][:30]
    else:
        media_seq = None
    uploader = (str(row.get("uploader") or "").strip()[:80] or None)
    is_verified = bool(row.get("is_uploader_verified")) if row.get("is_uploader_verified") is not None else None
    out: dict[str, Any] = {
        "platform": platform,
        "captured_at": captured.isoformat().replace("+00:00", "Z"),
        "album_url": url,
        "album_id": album_id,
        "entity_id": album_id,
        "entity_url": url,
        "page_context": ctx,
        "context": ctx,
        "views": views_i,
        "likes": likes_i,
        "score": likes_i,
        "videos": int(row.get("videos") or 0),
        "images": int(row.get("images") or 0),
        "total_duration_sec": int(row.get("total_duration_sec") or 0),
        "avg_duration_sec": int(row.get("avg_duration_sec") or 0),
        "longest_clip_sec": int(row.get("longest_clip_sec") or 0),
        "title": (str(row.get("title") or "").strip()[:200] or None),
        "tags": tags[:30],
        "format_bucket": (str(row.get("format_bucket") or "unknown").strip().lower() or "unknown"),
        "engagement_bps": int(engagement_bps or 0),
        "uploaded_at_approx_days_ago": age_days_f,
        "views_per_day_proxy": vpd_f,
        "uploader": uploader,
        "is_uploader_verified": is_verified,
        "media_sequence": media_seq,
    }
    return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _dedupe_key(row: dict[str, Any]) -> str:
    day = str(row.get("captured_at") or "")[:10]
    return f"{row.get('album_id')}:{day}"


def ingest_rows(raw_rows: list[dict[str, Any]], *, max_ledger_rows: int = 100_000) -> dict[str, Any]:
    """Append normalized browse-intel rows; dedupe album_id+day against ledger tail."""
    if not browse_intel_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    normalized: list[dict[str, Any]] = []
    rejected = 0
    for raw in raw_rows:
        row = _normalize_row(raw)
        if row:
            normalized.append(row)
        else:
            rejected += 1
    if not normalized:
        return {"ok": True, "appended": 0, "rejected": rejected, "scanned": len(raw_rows)}

    path = ledger_path()
    existing = _read_jsonl(path)
    seen = {_dedupe_key(r) for r in existing[-50_000:]}
    appended: list[dict[str, Any]] = []
    for row in normalized:
        key = _dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        appended.append(row)

    if appended:
        merged = (existing + appended)[-max_ledger_rows:]
        _write_jsonl(path, merged)
    for row in normalized:
        _append_timeseries(row)

    return {
        "ok": True,
        "appended": len(appended),
        "rejected": rejected,
        "scanned": len(raw_rows),
        "ledger_rows": len(_read_jsonl(path)),
        "ledger_path": str(path),
    }


def sync_from_drop_file() -> dict[str, Any]:
    """Ingest ``browse-intel-drop.jsonl`` if present (Tampermonkey export drop folder)."""
    drop = drop_path()
    if not drop.is_file():
        return {"ok": True, "skipped": True, "reason": "no_drop_file", "drop_path": str(drop)}
    rows = _read_jsonl(drop)
    result = ingest_rows(rows)
    done = drop.with_suffix(drop.suffix + _DONE_SUFFIX)
    try:
        drop.rename(done)
    except OSError:
        drop.unlink(missing_ok=True)
    result["drop_processed"] = str(done)
    return result


def load_recent_rows(*, days: int | None = None, max_rows: int = 50_000) -> list[dict[str, Any]]:
    if not browse_intel_enabled():
        return []
    days = days if days is not None else browse_intel_lookback_days()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = _read_jsonl(ledger_path())
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        ts = _parse_ts(str(row.get("captured_at") or ""))
        if ts and ts < since:
            continue
        out.append(row)
        if len(out) >= max_rows:
            break
    out.reverse()
    return out


def aggregate_tag_scores(
    rows: list[dict[str, Any]] | None = None,
    *,
    platform: str | None = "erome",
) -> dict[str, float]:
    """Tag -> weighted score (median views × engagement factor)."""
    rows = rows if rows is not None else load_recent_rows()
    if platform:
        rows = [r for r in rows if str(r.get("platform") or "erome").lower() == platform.lower()]
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        views = row.get("views")
        if views is None or int(views) <= 0:
            continue
        views_f = float(views)
        eng = int(row.get("engagement_bps") or 0)
        eng_factor = 1.0 + min(0.5, eng / 200_000.0)
        score = views_f * eng_factor
        for tag in row.get("tags") or []:
            t = str(tag).strip().lower()
            if t:
                buckets[t].append(score)
    out: dict[str, float] = {}
    for tag, vals in buckets.items():
        if not vals:
            continue
        vals.sort()
        mid = vals[len(vals) // 2]
        out[tag] = float(mid)
    return out


def aggregate_format_scores(rows: list[dict[str, Any]] | None = None) -> dict[str, float]:
    rows = rows if rows is not None else load_recent_rows()
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        views = row.get("views")
        if views is None or int(views) <= 0:
            continue
        bucket = str(row.get("format_bucket") or "unknown").strip().lower() or "unknown"
        buckets[bucket].append(float(views))
    return {k: sorted(v)[len(v) // 2] for k, v in buckets.items() if v}


def top_quartile_tags(tag_scores: dict[str, float] | None = None) -> set[str]:
    tag_scores = tag_scores if tag_scores is not None else aggregate_tag_scores()
    if not tag_scores:
        return set()
    vals = sorted(tag_scores.values())
    if not vals:
        return set()
    cutoff = vals[max(0, (len(vals) * 3) // 4 - 1)]
    return {t for t, s in tag_scores.items() if s >= cutoff}


def intel_summary(*, days: int | None = None) -> dict[str, Any]:
    rows = load_recent_rows(days=days)
    tag_scores = aggregate_tag_scores(rows)
    format_scores = aggregate_format_scores(rows)
    top_tags = sorted(tag_scores.items(), key=lambda x: -x[1])[:25]
    top_formats = sorted(format_scores.items(), key=lambda x: -x[1])
    tq = top_quartile_tags(tag_scores)
    return {
        "ok": True,
        "enabled": browse_intel_enabled(),
        "lookback_days": days if days is not None else browse_intel_lookback_days(),
        "row_count": len(rows),
        "tag_count": len(tag_scores),
        "top_quartile_tag_count": len(tq),
        "top_tags": [{"tag": t, "score": round(s, 1)} for t, s in top_tags],
        "format_scores": {k: round(v, 1) for k, v in top_formats},
        "top_quartile_tags": sorted(tq)[:40],
        "ledger_path": str(ledger_path()),
        "drop_path": str(drop_path()),
    }


def media_tag_intel_multiplier(media_tags: str | None, tag_scores: dict[str, float] | None = None) -> float:
    """Boost multiplier for pool media based on tag overlap with browse intel."""
    tag_scores = tag_scores if tag_scores is not None else aggregate_tag_scores()
    if not tag_scores:
        return 1.0
    tags = [t.strip().lower() for t in (media_tags or "").split(",") if t.strip()]
    if not tags:
        return 1.0
    hits = [tag_scores[t] for t in tags if t in tag_scores]
    if not hits:
        return 1.0
    max_score = max(tag_scores.values())
    if max_score <= 0:
        return 1.0
    avg_hit = sum(hits) / len(hits)
    ratio = avg_hit / max_score
    return 0.55 + 1.45 * ratio
