"""Weekly market-intel cycle — fuse Erome + Reddit rows into an actionable conclusion.

Runs on a calendar-week window (default 7 days, evaluated Monday). When sample
thresholds pass and the leading tag is stable vs the prior week, the cycle is
*complete* with a confidence score suitable for growth proposals or gated auto-post.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.erome_browse_intel import (
    aggregate_tag_scores,
    load_recent_rows,
)
from app.services.erome_upload_analytics import analytics_dir

logger = logging.getLogger(__name__)

_LEDGER_NAME = "market-intel-cycle.jsonl"


def cycle_enabled() -> bool:
    return (os.getenv("TBCC_MARKET_INTEL_CYCLE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def cycle_window_days() -> int:
    raw = (os.getenv("TBCC_MARKET_INTEL_CYCLE_WINDOW_DAYS") or "7").strip()
    try:
        return max(1, min(28, int(raw)))
    except ValueError:
        return 7


def cycle_min_erome_rows() -> int:
    raw = (os.getenv("TBCC_MARKET_INTEL_CYCLE_MIN_EROME_ROWS") or "50").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 50


def cycle_min_reddit_rows() -> int:
    raw = (os.getenv("TBCC_MARKET_INTEL_CYCLE_MIN_REDDIT_ROWS") or "20").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 20


def cycle_confidence_min() -> float:
    raw = (os.getenv("TBCC_MARKET_INTEL_CYCLE_CONFIDENCE_MIN") or "0.65").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.65


def cycle_ledger_path() -> Path:
    return analytics_dir() / _LEDGER_NAME


def week_id(dt: datetime | None = None) -> str:
    """ISO week label, e.g. ``2026-W27``."""
    dt = dt or datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_cycle_ledger(*, max_rows: int = 104) -> list[dict[str, Any]]:
    return _read_jsonl(cycle_ledger_path())[-max_rows:]


def get_last_cycle_record(*, before_week: str | None = None) -> dict[str, Any] | None:
    """Most recent cycle record, optionally excluding the current week id."""
    records = load_cycle_ledger()
    for row in reversed(records):
        wid = str(row.get("week_id") or "")
        if before_week and wid == before_week:
            continue
        return row
    return None


def get_cycle_record_for_week(target_week: str | None = None) -> dict[str, Any] | None:
    target = target_week or week_id()
    for row in reversed(load_cycle_ledger()):
        if str(row.get("week_id") or "") == target:
            return row
    return None


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_v = max(scores.values())
    if max_v <= 0:
        return {k: 0.0 for k in scores}
    return {k: float(v) / max_v for k, v in scores.items()}


def _reddit_tag_hits(rows: list[dict[str, Any]]) -> dict[str, int]:
    hits: dict[str, int] = {}
    for row in rows:
        for tag in row.get("tags") or []:
            t = str(tag).strip().lower()
            if t:
                hits[t] = hits.get(t, 0) + 1
    return hits


def compute_trend_scores(
    erome_rows: list[dict[str, Any]],
    reddit_rows: list[dict[str, Any]],
    *,
    erome_weight: float = 0.55,
    reddit_weight: float = 0.25,
    cross_weight: float = 0.20,
) -> list[dict[str, Any]]:
    """Rank tags by fused Erome score + Reddit mention density + cross-platform overlap."""
    erome_raw = aggregate_tag_scores(erome_rows, platform="erome")
    erome_norm = _normalize_scores(erome_raw)
    reddit_hits = _reddit_tag_hits(reddit_rows)
    reddit_norm = _normalize_scores({k: float(v) for k, v in reddit_hits.items()})

    tags = set(erome_norm) | set(reddit_norm)
    ranked: list[dict[str, Any]] = []
    for tag in tags:
        e = erome_norm.get(tag, 0.0)
        r = reddit_norm.get(tag, 0.0)
        cross = 1.0 if e > 0 and r > 0 else 0.0
        trend = erome_weight * e + reddit_weight * r + cross_weight * cross
        ranked.append(
            {
                "tag": tag,
                "trend_score": round(trend, 4),
                "erome_score": round(erome_raw.get(tag, 0.0), 1),
                "erome_normalized": round(e, 4),
                "reddit_hits": reddit_hits.get(tag, 0),
                "reddit_normalized": round(r, 4),
                "cross_platform": bool(cross),
            }
        )
    ranked.sort(key=lambda x: (-float(x["trend_score"]), -float(x["erome_score"]), x["tag"]))
    return ranked


def _leader_stable(
    top_tag: str | None,
    prior: dict[str, Any] | None,
) -> tuple[bool, str]:
    if not top_tag:
        return False, "no_leader"
    if not prior:
        return True, "first_cycle"
    prior_top = (prior.get("top_tags") or [{}])[0]
    prior_tag = str(prior_top.get("tag") or "")
    if prior_tag == top_tag:
        return True, "same_leader_as_prior_week"
    prior_top3 = {str(t.get("tag") or "") for t in (prior.get("top_tags") or [])[:3]}
    if top_tag in prior_top3:
        return True, "leader_in_prior_top3"
    return False, "leader_changed"


def evaluate_weekly_cycle(*, force: bool = False) -> dict[str, Any]:
    """Evaluate the rolling weekly window; append ledger row when forced or newly complete."""
    now = datetime.now(timezone.utc)
    wid = week_id(now)
    window_days = cycle_window_days()

    if not cycle_enabled():
        return {
            "ok": True,
            "enabled": False,
            "skipped": True,
            "reason": "disabled",
            "week_id": wid,
        }

    existing = get_cycle_record_for_week(wid)
    if existing and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_evaluated_this_week",
            "week_id": wid,
            "record": existing,
        }

    rows = load_recent_rows(days=window_days)
    erome_rows = [r for r in rows if str(r.get("platform") or "erome") == "erome"]
    reddit_rows = [r for r in rows if str(r.get("platform") or "") == "reddit"]

    min_erome = cycle_min_erome_rows()
    min_reddit = cycle_min_reddit_rows()
    sample_ok = len(erome_rows) >= min_erome and len(reddit_rows) >= min_reddit

    ranked = compute_trend_scores(erome_rows, reddit_rows)
    top_tags = ranked[:8]
    leader = top_tags[0]["tag"] if top_tags else None

    prior = get_last_cycle_record(before_week=wid)
    stable, stability_reason = _leader_stable(leader, prior)

    # Confidence: sample coverage + leader strength + stability + cross-platform leader
    sample_factor = min(1.0, len(erome_rows) / max(min_erome, 1)) * 0.5
    sample_factor += min(1.0, len(reddit_rows) / max(min_reddit, 1)) * 0.5
    sample_factor = min(1.0, sample_factor)
    leader_strength = float(top_tags[0]["trend_score"]) if top_tags else 0.0
    cross_bonus = 0.1 if top_tags and top_tags[0].get("cross_platform") else 0.0
    stability_bonus = 0.15 if stable else 0.0
    confidence = min(
        1.0,
        sample_factor * 0.45 + leader_strength * 0.35 + cross_bonus + stability_bonus,
    )
    if not sample_ok:
        confidence = min(confidence, 0.4)

    complete = bool(
        sample_ok
        and leader
        and stable
        and confidence >= cycle_confidence_min()
    )

    reasons: list[str] = []
    if not sample_ok:
        reasons.append(
            f"insufficient_samples (erome={len(erome_rows)}/{min_erome}, "
            f"reddit={len(reddit_rows)}/{min_reddit})"
        )
    if not stable:
        reasons.append(f"unstable_leader ({stability_reason})")
    if leader and confidence < cycle_confidence_min():
        reasons.append(f"confidence_below_min ({confidence:.2f} < {cycle_confidence_min():.2f})")
    if complete:
        reasons.append("weekly_cycle_complete")

    saturated: list[str] = []
    try:
        from app.services.erome_upload_policy import intel_upload_hints

        hints = intel_upload_hints()
        saturated = list(hints.get("saturated_tags") or [])
    except Exception as e:
        logger.debug("intel_upload_hints in cycle: %s", e)

    if leader and leader in saturated:
        confidence = max(0.0, confidence - 0.12)
        reasons.append(f"leader_saturated ({leader})")
        if confidence < cycle_confidence_min():
            complete = False

    record: dict[str, Any] = {
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "week_id": wid,
        "window_days": window_days,
        "complete": complete,
        "confidence": round(confidence, 3),
        "confidence_min": cycle_confidence_min(),
        "leader_tag": leader,
        "top_tags": top_tags,
        "row_counts": {"erome": len(erome_rows), "reddit": len(reddit_rows), "total": len(rows)},
        "min_rows": {"erome": min_erome, "reddit": min_reddit},
        "stability": {"stable": stable, "reason": stability_reason},
        "prior_week_id": prior.get("week_id") if prior else None,
        "reasons": reasons,
        "saturated_tags": saturated[:12],
    }

    if force or complete or not existing:
        _append_jsonl(cycle_ledger_path(), record)

    return {
        "ok": True,
        "enabled": True,
        "week_id": wid,
        "complete": complete,
        "confidence": record["confidence"],
        "leader_tag": leader,
        "top_tags": top_tags[:5],
        "row_counts": record["row_counts"],
        "reasons": reasons,
        "record": record,
    }


def cycle_signal_from_last_record() -> dict[str, Any] | None:
    """Growth-signal shaped dict from the latest weekly cycle record."""
    rec = get_cycle_record_for_week() or get_last_cycle_record()
    if not rec or not rec.get("complete"):
        return None
    leader = rec.get("leader_tag")
    if not leader:
        return None
    conf = float(rec.get("confidence") or 0)
    strength = min(1.0, conf)
    return {
        "signal_type": "market_intel_weekly_cycle",
        "strength": round(strength, 3),
        "confidence": "high" if conf >= 0.8 else "medium",
        "tag": leader,
        "week_id": rec.get("week_id"),
        "top_tags": [t.get("tag") for t in (rec.get("top_tags") or [])[:5]],
        "recommended_action": "INTEL_CYCLE_POST",
        "recommendation": (
            f"Weekly intel cycle complete (week {rec.get('week_id')}): "
            f"lead tag «{leader}» — bias pool picks + Buffer/Reddit surfaces."
        ),
    }
