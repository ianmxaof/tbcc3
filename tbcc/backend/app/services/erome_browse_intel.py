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


def repair_comma_decimal_m_views(views: int | None, likes: int | None) -> int | None:
    """Undo extension bug: ``4,7M`` parsed as ``47M`` (comma stripped before K/M).

    Signal: views are an exact multi-million (≥10M) with sub-normal engagement vs
    typical Erome like/view rates (~20–250 bps). Correct ``4.7M`` stores as 4700000
    (not divisible by 1e6).
    """
    if views is None:
        return None
    try:
        v = int(views)
    except (TypeError, ValueError):
        return None
    if v < 10_000_000 or v % 1_000_000 != 0:
        return v
    try:
        likes_i = int(likes) if likes is not None else 0
    except (TypeError, ValueError):
        likes_i = 0
    if likes_i > 0:
        eng_bps = (likes_i / v) * 100_000.0
        if eng_bps >= 40.0:
            return v
    return v // 10


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
    views_i = repair_comma_decimal_m_views(views_i, likes_i)
    tags_raw = row.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip().lower() for t in re.split(r"[,;]+", tags_raw) if t.strip()]
    else:
        tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]
    ctx = row.get("page_context") if isinstance(row.get("page_context"), dict) else {}
    engagement_bps = row.get("engagement_bps")
    if views_i and likes_i:
        # Recompute after view repair so bps match corrected counts.
        engagement_bps = int(round((likes_i / views_i) * 100_000))
    platform = str(row.get("platform") or "erome").strip().lower() or "erome"
    age_days = row.get("uploaded_at_approx_days_ago")
    try:
        age_days_f = float(age_days) if age_days is not None else None
    except (TypeError, ValueError):
        age_days_f = None
    vpd = row.get("views_per_day_proxy")
    if views_i and age_days_f and age_days_f > 0:
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


def _with_repaired_views(row: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy with comma-decimal M inflate corrected (read path for old ledger)."""
    try:
        views_i = int(row["views"]) if row.get("views") is not None else None
    except (TypeError, ValueError):
        views_i = None
    try:
        likes_i = int(row["likes"]) if row.get("likes") is not None else None
    except (TypeError, ValueError):
        likes_i = None
    fixed = repair_comma_decimal_m_views(views_i, likes_i)
    if fixed is None or fixed == views_i:
        return row
    out = dict(row)
    out["views"] = fixed
    if fixed and likes_i:
        out["engagement_bps"] = int(round((likes_i / fixed) * 100_000))
    try:
        age = (
            float(out["uploaded_at_approx_days_ago"])
            if out.get("uploaded_at_approx_days_ago") is not None
            else None
        )
    except (TypeError, ValueError):
        age = None
    if fixed and age and age > 0:
        out["views_per_day_proxy"] = round(fixed / age, 1)
    return out


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
        out.append(_with_repaired_views(row))
        if len(out) >= max_rows:
            break
    out.reverse()
    return out


def aggregate_tag_scores(
    rows: list[dict[str, Any]] | None = None,
    *,
    platform: str | None = None,
) -> dict[str, float]:
    """Tag -> weighted score (median views × engagement factor).

    ``platform=None`` (default) merges all platforms so ThisVid/Motherless/FetLife
    context tags can contribute to pool rank. Pass ``platform=\"erome\"`` for
    Erome-only upload/market-cycle logic.
    """
    rows = rows if rows is not None else load_recent_rows()
    if platform:
        rows = [r for r in rows if str(r.get("platform") or "erome").lower() == platform.lower()]
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        views = row.get("views")
        views_f: float | None = None
        try:
            if views is not None and int(views) > 0:
                views_f = float(views)
        except (TypeError, ValueError):
            views_f = None
        if views_f is None:
            # RSS / context platforms often lack view counts — soft proxies.
            vpd = row.get("views_per_day_proxy")
            age = row.get("uploaded_at_approx_days_ago")
            try:
                if vpd is not None and float(vpd) > 0:
                    views_f = float(vpd) * 10.0
                elif age is not None and float(age) > 0:
                    views_f = max(1.0, 100.0 / max(0.5, float(age)))
                elif row.get("tags"):
                    views_f = 50.0
            except (TypeError, ValueError):
                views_f = 50.0 if row.get("tags") else None
        if views_f is None or views_f <= 0:
            continue
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
    """Backward-compat: format_bucket → median views (upload hints / cycles)."""
    stats = aggregate_format_stats(rows)
    return {k: float(v["median_views"]) for k, v in stats.items() if v.get("median_views")}


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    return float(vals[len(vals) // 2])


def aggregate_format_stats(
    rows: list[dict[str, Any]] | None = None,
    *,
    platform: str | None = "erome",
    min_n: int = 3,
) -> dict[str, dict[str, Any]]:
    """Per format_bucket: n, median_views, median_likes (for discovery UI)."""
    rows = rows if rows is not None else load_recent_rows()
    if platform:
        rows = [r for r in rows if str(r.get("platform") or "erome").lower() == platform.lower()]
    view_buckets: dict[str, list[float]] = defaultdict(list)
    like_buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        bucket = str(row.get("format_bucket") or "unknown").strip().lower() or "unknown"
        try:
            views = row.get("views")
            if views is not None and int(views) > 0:
                view_buckets[bucket].append(float(views))
        except (TypeError, ValueError):
            pass
        try:
            likes = row.get("likes")
            if likes is not None and int(likes) >= 0:
                like_buckets[bucket].append(float(likes))
        except (TypeError, ValueError):
            pass
    keys = set(view_buckets) | set(like_buckets)
    out: dict[str, dict[str, Any]] = {}
    for k in keys:
        views = view_buckets.get(k) or []
        likes = like_buckets.get(k) or []
        n = max(len(views), len(likes))
        if n < max(1, int(min_n)):
            continue
        out[k] = {
            "n": n,
            "n_views": len(views),
            "n_likes": len(likes),
            "median_views": _median(views),
            "median_likes": _median(likes),
        }
    return out


def format_discoveries(
    rows: list[dict[str, Any]] | None = None,
    *,
    platform: str | None = "erome",
    min_n: int = 5,
) -> dict[str, Any]:
    """
    Turn ledger stats into suite UI actions.

    Example: if mixed_album median likes beat other formats → recommend
    ``show_most_liked_mixed`` on Erome search pages.
    """
    stats = aggregate_format_stats(rows, platform=platform, min_n=min_n)
    if not stats:
        return {
            "ok": True,
            "preferred_format_bucket": None,
            "preferred_metric": None,
            "suite_actions": [],
            "format_stats": {},
            "reason": "insufficient_samples",
        }

    # Prefer likes when enough buckets have like samples; else views.
    like_ready = {k: v for k, v in stats.items() if v.get("median_likes") is not None and (v.get("n_likes") or 0) >= min_n}
    metric = "median_likes" if like_ready else "median_views"
    pool = like_ready if like_ready else {k: v for k, v in stats.items() if v.get("median_views") is not None}
    if not pool:
        return {
            "ok": True,
            "preferred_format_bucket": None,
            "preferred_metric": None,
            "suite_actions": [],
            "format_stats": stats,
            "reason": "no_metric",
        }

    ranked = sorted(
        pool.items(),
        key=lambda kv: float(kv[1].get(metric) or 0),
        reverse=True,
    )
    best_bucket, best_row = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    best_val = float(best_row.get(metric) or 0)
    second_val = float(runner_up[1].get(metric) or 0) if runner_up else 0.0
    lift = (best_val / second_val) if second_val > 0 else None

    actions: list[dict[str, Any]] = []
    if best_bucket == "mixed_album" and (platform or "erome") == "erome":
        actions.append(
            {
                "id": "show_most_liked_mixed",
                "suite": "erome",
                "surfaces": ["search", "explore", "user"],
                "label": "Show most liked mixed albums",
                "format_bucket": "mixed_album",
                "sort": "likes",
                "filter": "mixed",
                "confidence": "high" if lift and lift >= 1.15 else "medium",
                "evidence": {
                    "metric": metric,
                    "median": best_val,
                    "n": best_row.get("n"),
                    "lift_vs_runner_up": round(lift, 3) if lift else None,
                    "runner_up": runner_up[0] if runner_up else None,
                },
            }
        )
    elif best_bucket == "multi_video" and (platform or "erome") == "erome":
        actions.append(
            {
                "id": "show_most_liked_multi_video",
                "suite": "erome",
                "surfaces": ["search", "explore"],
                "label": "Show most liked multi-video albums",
                "format_bucket": "multi_video",
                "sort": "likes",
                "filter": "multi_video",
                "confidence": "medium",
                "evidence": {
                    "metric": metric,
                    "median": best_val,
                    "n": best_row.get("n"),
                    "lift_vs_runner_up": round(lift, 3) if lift else None,
                },
            }
        )

    return {
        "ok": True,
        "preferred_format_bucket": best_bucket,
        "preferred_metric": metric,
        "preferred_median": best_val,
        "suite_actions": actions,
        "format_stats": stats,
        "ranked_formats": [
            {"format_bucket": k, "median": float(v.get(metric) or 0), "n": v.get("n")} for k, v in ranked
        ],
    }


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
    discoveries = format_discoveries(rows, platform="erome")
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
        "format_stats": discoveries.get("format_stats") or {},
        "discoveries": discoveries,
        "suite_actions": discoveries.get("suite_actions") or [],
        "preferred_format_bucket": discoveries.get("preferred_format_bucket"),
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
