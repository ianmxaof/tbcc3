"""
Content growth signals — strongest analytics for the TBCC flywheel / reactionary content engine.

Computes ranked signals from delivery views + growth attribution. Does NOT instant-DM
(sales/errors use payment_admin_notify + ops flywheel). Outputs digest for inbox review
and flywheel tick JSON.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.growth_attribution_event import GrowthAttributionEvent
from app.models.media import Media
from app.models.post_delivery_metric import PostDeliveryMetric
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.content_performance import (
    SUGGESTED_PEAK_HOURS_ET,
    aggregate_views_by_hour,
    analytics_timezone_label,
    performance_enabled,
    refresh_delivery_views_sync,
)
from app.services.growth_attribution import (
    EVENT_LOOT_FREE_PULL,
    EVENT_LOOT_ROLL,
    EVENT_SUBSCRIPTION_CREATED,
)

logger = logging.getLogger(__name__)

SignalConfidence = Literal["high", "medium", "low"]

REDIS_LAST_DIGEST = "tbcc:growth_signals:last_digest"
REDIS_LAST_TICK = "tbcc:growth_signals:last_tick"


def signals_enabled() -> bool:
    return (os.getenv("TBCC_GROWTH_SIGNALS_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def flywheel_growth_tick_enabled() -> bool:
    """Growth lane in unified flywheel tick. TBCC_FLYWHEEL_GROWTH_TICK=1 by default."""
    raw = (os.getenv("TBCC_FLYWHEEL_GROWTH_TICK") or os.getenv("TBCC_OPENCLAW_GROWTH_TICK") or "1").strip()
    return raw.lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def openclaw_growth_tick_enabled() -> bool:
    """Deprecated alias — internal flywheel, not github.com/openclaw/openclaw."""
    return flywheel_growth_tick_enabled()


def _env_int(key: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def _env_float(key: str, default: float, *, lo: float, hi: float) -> float:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def signal_lookback_days() -> int:
    return _env_int("TBCC_SIGNAL_LOOKBACK_DAYS", 14, lo=3, hi=90)


def min_posts_per_hour() -> int:
    return _env_int("TBCC_SIGNAL_MIN_POSTS_PER_HOUR", 3, lo=1, hi=50)


def min_sends_per_slot() -> int:
    return _env_int("TBCC_SIGNAL_MIN_SENDS_PER_SLOT", 3, lo=2, hi=50)


def caption_win_ratio() -> float:
    return _env_float("TBCC_SIGNAL_CAPTION_WIN_RATIO", 1.5, lo=1.1, hi=5.0)


def min_views_for_ranking() -> int:
    return _env_int("TBCC_SIGNAL_MIN_VIEWS", 10, lo=1, hi=10000)


def min_conversions_per_hour() -> int:
    return _env_int("TBCC_SIGNAL_MIN_CONVERSIONS_PER_HOUR", 2, lo=1, hi=50)


def max_signals_returned() -> int:
    return _env_int("TBCC_SIGNAL_MAX_RESULTS", 8, lo=3, hi=25)


def skip_empty_growth_ticks() -> bool:
    """Skip growth tick / OpenClaw report when there is nothing actionable to compute."""
    return (os.getenv("TBCC_GROWTH_TICK_SKIP_EMPTY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def min_refreshable_deliveries() -> int:
    return _env_int("TBCC_GROWTH_TICK_MIN_REFRESHABLE_DELIVERIES", 3, lo=1, hi=200)


def min_view_rows_for_signals() -> int:
    return _env_int("TBCC_GROWTH_TICK_MIN_VIEW_ROWS", 3, lo=1, hi=500)


def growth_data_footprint(db: Session, *, days: int | None = None) -> dict[str, Any]:
    """Counts delivery / view / attribution rows in the signal lookback window."""
    window_days = days or signal_lookback_days()
    since = datetime.utcnow() - timedelta(days=window_days)
    attr_since = since

    total_deliveries = (
        db.query(PostDeliveryMetric).filter(PostDeliveryMetric.created_at >= since).count()
    )
    refreshable = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.telegram_message_id.isnot(None),
            PostDeliveryMetric.channel_identifier.isnot(None),
        )
        .count()
    )
    with_views = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
        )
        .count()
    )
    attribution_events = (
        db.query(GrowthAttributionEvent)
        .filter(GrowthAttributionEvent.created_at >= attr_since)
        .count()
    )
    return {
        "lookback_days": window_days,
        "total_deliveries": total_deliveries,
        "refreshable_deliveries": refreshable,
        "deliveries_with_views": with_views,
        "attribution_events": attribution_events,
        "thresholds": {
            "min_refreshable_deliveries": min_refreshable_deliveries(),
            "min_view_rows": min_view_rows_for_signals(),
            "min_conversions_per_hour": min_conversions_per_hour(),
        },
    }


def assess_growth_tick_eligibility(db: Session, *, days: int | None = None) -> dict[str, Any]:
    """
    Decide whether a growth tick (view refresh + signal rank + proposals) is worth running.
    Saves Telethon polls and OpenClaw tokens when the ledger is too sparse.
    """
    if not signals_enabled():
        return {"eligible": False, "reason": "signals_disabled", "footprint": {}}

    footprint = growth_data_footprint(db, days=days)
    min_refresh = min_refreshable_deliveries()
    min_views = min_view_rows_for_signals()
    min_attr = min_conversions_per_hour()

    can_refresh = footprint["refreshable_deliveries"] >= min_refresh
    can_rank_views = footprint["deliveries_with_views"] >= min_views
    can_rank_conversions = footprint["attribution_events"] >= min_attr
    eligible = can_refresh or can_rank_views or can_rank_conversions

    if not skip_empty_growth_ticks():
        eligible = True

    reason = "ok"
    if not eligible:
        reason = (
            "insufficient_data: need "
            f">={min_refresh} refreshable deliveries, "
            f">={min_views} rows with views, or "
            f">={min_attr} attribution events"
        )

    return {
        "eligible": eligible,
        "reason": reason,
        "can_refresh_views": can_refresh,
        "can_rank_signals": can_rank_views or can_rank_conversions,
        "footprint": footprint,
    }


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _confidence(sample: int, threshold: int, *, ratio: float = 1.0) -> SignalConfidence:
    if sample >= threshold * 2 and ratio >= 1.8:
        return "high"
    if sample >= threshold and ratio >= 1.3:
        return "medium"
    return "low"


def _strength_score(avg: float, sample: int, *, network_avg: float) -> float:
    if network_avg <= 0 or avg <= 0:
        return 0.0
    ratio = avg / network_avg
    import math

    sample_factor = min(1.0, math.log1p(sample) / math.log1p(10))
    raw = ratio * sample_factor
    return round(min(1.0, raw / 2.5), 3)


def _hour_label(h: int) -> str:
    return f"{h:02d}:00"


def _signals_peak_hours(db: Session, *, days: int, network_avg: float) -> list[dict[str, Any]]:
    hour_data = aggregate_views_by_hour(db, days=days)
    min_posts = min_posts_per_hour()
    min_views = min_views_for_ranking()
    out: list[dict[str, Any]] = []

    for row in hour_data.get("by_hour") or []:
        post_count = int(row.get("post_count") or 0)
        avg = row.get("avg_views")
        if post_count < min_posts or avg is None:
            continue
        avg_f = float(avg)
        if avg_f < min_views:
            continue
        h = int(row["hour_local"])
        ratio = avg_f / network_avg if network_avg > 0 else 1.0
        conf = _confidence(post_count, min_posts, ratio=ratio)
        out.append(
            {
                "signal_type": "peak_post_hour",
                "strength": _strength_score(avg_f, post_count, network_avg=network_avg),
                "confidence": conf,
                "hour_local": h,
                "avg_views": avg_f,
                "post_count": post_count,
                "vs_network_avg": round(ratio, 2),
                "recommendation": (
                    f"Bias recurring posts toward {_hour_label(h)} {analytics_timezone_label()} "
                    f"(avg {avg_f:.0f} views over {post_count} posts, {ratio:.1f}× network avg)."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x["post_count"])))
    return out


def _signals_caption_winners(db: Session, *, days: int, network_avg: float) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    sched_ids = (
        db.query(PostDeliveryMetric.scheduled_post_id)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.scheduled_post_id.isnot(None),
            PostDeliveryMetric.views_latest.isnot(None),
        )
        .distinct()
        .limit(40)
        .all()
    )
    min_sends = min_sends_per_slot()
    win_ratio = caption_win_ratio()
    out: list[dict[str, Any]] = []

    for (sid,) in sched_ids:
        if not sid:
            continue
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(sid)).first()
        if not post:
            continue
        rows = (
            db.query(PostDeliveryMetric)
            .filter(
                PostDeliveryMetric.scheduled_post_id == int(sid),
                PostDeliveryMetric.created_at >= since,
            )
            .all()
        )
        by_slot: dict[int, list[int]] = defaultdict(list)
        sends: dict[int, int] = defaultdict(int)
        for r in rows:
            slot = int(r.caption_slot_index or 0)
            sends[slot] += 1
            if r.views_latest is not None:
                by_slot[slot].append(int(r.views_latest))

        slot_avgs: dict[int, float] = {}
        for slot, vals in by_slot.items():
            if sends[slot] >= min_sends and vals:
                slot_avgs[slot] = sum(vals) / len(vals)

        if len(slot_avgs) < 2:
            continue

        sched_avg = sum(slot_avgs.values()) / len(slot_avgs)
        if sched_avg < min_views_for_ranking():
            continue

        for slot, avg in slot_avgs.items():
            ratio = avg / sched_avg
            if ratio < win_ratio:
                continue
            conf = _confidence(sends[slot], min_sends, ratio=ratio)
            name = (post.name or f"post#{post.id}").strip()
            out.append(
                {
                    "signal_type": "caption_slot_winner",
                    "strength": _strength_score(avg, sends[slot], network_avg=network_avg),
                    "confidence": conf,
                    "scheduled_post_id": int(sid),
                    "scheduler_name": name,
                    "caption_slot_index": slot,
                    "avg_views": round(avg, 1),
                    "send_count": sends[slot],
                    "vs_scheduler_avg": round(ratio, 2),
                    "recommendation": (
                        f"Caption slot {slot} on «{name}» averages {avg:.0f} views "
                        f"({ratio:.1f}× other slots) — favor this rotation index."
                    ),
                }
            )
    out.sort(key=lambda x: (-float(x["strength"]), -float(x.get("avg_views") or 0)))
    return out


def _signals_channel_leaders(db: Session, *, days: int, network_avg: float) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
            PostDeliveryMetric.channel_id.isnot(None),
        )
        .all()
    )
    by_ch: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        by_ch[int(r.channel_id)].append(int(r.views_latest or 0))

    ch_map = {
        c.id: c.name or c.identifier or str(c.id)
        for c in db.query(Channel).filter(Channel.id.in_(list(by_ch.keys()))).all()
    }
    min_posts = min_posts_per_hour()
    out: list[dict[str, Any]] = []

    for cid, vals in by_ch.items():
        if len(vals) < min_posts:
            continue
        avg = sum(vals) / len(vals)
        if avg < min_views_for_ranking():
            continue
        ratio = avg / network_avg if network_avg > 0 else 1.0
        if ratio < 1.2:
            continue
        conf = _confidence(len(vals), min_posts, ratio=ratio)
        cname = ch_map.get(cid, str(cid))
        out.append(
            {
                "signal_type": "channel_view_leader",
                "strength": _strength_score(avg, len(vals), network_avg=network_avg),
                "confidence": conf,
                "channel_id": cid,
                "channel_name": cname,
                "avg_views": round(avg, 1),
                "post_count": len(vals),
                "vs_network_avg": round(ratio, 2),
                "recommendation": (
                    f"Lane «{cname}» leads at {avg:.0f} avg views ({ratio:.1f}× network) — "
                    "prioritize deposits and cross-promo here."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x["post_count"])))
    return out


def _signals_conversion_hours(db: Session, *, days: int) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(GrowthAttributionEvent)
        .filter(
            GrowthAttributionEvent.created_at >= since,
            GrowthAttributionEvent.event_type.in_(
                (EVENT_SUBSCRIPTION_CREATED, EVENT_LOOT_ROLL, EVENT_LOOT_FREE_PULL)
            ),
            GrowthAttributionEvent.posted_hour_local.isnot(None),
        )
        .all()
    )
    by_hour: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        h = int(r.posted_hour_local or 0)
        by_hour[h][r.event_type] += 1
        by_hour[h]["_total"] += 1

    min_conv = min_conversions_per_hour()
    out: list[dict[str, Any]] = []
    for h, counts in by_hour.items():
        total = int(counts.get("_total") or 0)
        subs = int(counts.get(EVENT_SUBSCRIPTION_CREATED) or 0)
        if total < min_conv:
            continue
        strength = min(1.0, round((subs * 2 + total) / 20, 3))
        conf: SignalConfidence = "high" if subs >= 2 else "medium" if subs >= 1 else "low"
        out.append(
            {
                "signal_type": "conversion_hour",
                "strength": strength,
                "confidence": conf,
                "hour_local": h,
                "subscription_count": subs,
                "loot_activity_count": int(counts.get(EVENT_LOOT_ROLL) or 0)
                + int(counts.get(EVENT_LOOT_FREE_PULL) or 0),
                "total_events": total,
                "recommendation": (
                    f"Conversions cluster at {_hour_label(h)} {analytics_timezone_label()} "
                    f"({subs} subs, {total} loot/sub events) — align high-intent CTAs to this window."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x.get("subscription_count") or 0)))
    return out


def _network_avg_views(db: Session, *, days: int) -> float:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PostDeliveryMetric.views_latest)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
        )
        .all()
    )
    vals = [int(v[0]) for v in rows if v and v[0] is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _attribution_network_key(row: GrowthAttributionEvent) -> str | None:
    raw = getattr(row, "context_json", None)
    if not raw:
        return None
    try:
        ctx = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    nk = (ctx.get("network_key") or ctx.get("lane") or "").strip().lower()
    return nk or None


def _channel_id_to_network_key(db: Session) -> dict[int, str]:
    from app.data.aof_network import AOF_NETWORK_CHANNELS

    ch_ids: dict[int, str] = {}
    for nc in AOF_NETWORK_CHANNELS:
        ch = db.query(Channel).filter(Channel.identifier == nc.identifier).first()
        if ch:
            ch_ids[int(ch.id)] = nc.key
    return ch_ids


def _signals_lane_view_leaders(db: Session, *, days: int, network_avg: float) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
            PostDeliveryMetric.network_key.isnot(None),
            PostDeliveryMetric.surface.in_(("telegram", None)),
        )
        .all()
    )
    by_lane: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        nk = (r.network_key or "").strip().lower()
        if nk:
            by_lane[nk].append(int(r.views_latest or 0))

    out: list[dict[str, Any]] = []
    for nk, vals in by_lane.items():
        if len(vals) < min_posts_per_hour():
            continue
        avg = sum(vals) / len(vals)
        if avg < min_views_for_ranking():
            continue
        ratio = avg / network_avg if network_avg > 0 else 1.0
        if ratio < 1.15:
            continue
        out.append(
            {
                "signal_type": "lane_view_leader",
                "strength": _strength_score(avg, len(vals), network_avg=network_avg),
                "confidence": _confidence(len(vals), min_posts_per_hour(), ratio=ratio),
                "network_key": nk,
                "avg_views": round(avg, 1),
                "post_count": len(vals),
                "vs_network_avg": round(ratio, 2),
                "recommendation": (
                    f"Lane «{nk}» leads at {avg:.0f} avg Telegram views ({ratio:.1f}× network) — "
                    "boost exports for this category."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x["post_count"])))
    return out


def _signals_lane_conversion_leaders(db: Session, *, days: int) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(GrowthAttributionEvent)
        .filter(
            GrowthAttributionEvent.created_at >= since,
            GrowthAttributionEvent.event_type.in_(
                (EVENT_SUBSCRIPTION_CREATED, EVENT_LOOT_ROLL, EVENT_LOOT_FREE_PULL)
            ),
        )
        .all()
    )
    ch_map = _channel_id_to_network_key(db)
    by_lane: dict[str, int] = defaultdict(int)
    subs_by_lane: dict[str, int] = defaultdict(int)
    for r in rows:
        nk = _attribution_network_key(r)
        if not nk and r.channel_id:
            nk = ch_map.get(int(r.channel_id))
        if not nk:
            continue
        by_lane[nk] += 1
        if r.event_type == EVENT_SUBSCRIPTION_CREATED:
            subs_by_lane[nk] += 1

    out: list[dict[str, Any]] = []
    for nk, total in by_lane.items():
        if total < min_conversions_per_hour():
            continue
        subs = subs_by_lane.get(nk, 0)
        strength = min(1.0, round((subs * 2 + total) / 15, 3))
        out.append(
            {
                "signal_type": "lane_conversion_leader",
                "strength": strength,
                "confidence": "high" if subs >= 2 else "medium",
                "network_key": nk,
                "subscription_count": subs,
                "total_events": total,
                "recommendation": (
                    f"Lane «{nk}» drives {subs} subs / {total} loot events — prioritize VIP/loot exports here."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x.get("subscription_count") or 0)))
    return out


def _signals_pool_backlog_pressure(db: Session) -> list[dict[str, Any]]:
    from app.data.export_lane_policy import all_lane_policies
    from app.services.export_flywheel_service import approved_pool_depth, pool_id_for_network_key

    out: list[dict[str, Any]] = []
    for nk, policy in all_lane_policies().items():
        pid = pool_id_for_network_key(db, nk)
        if not pid:
            continue
        depth = approved_pool_depth(db, pid)
        min_depth = policy.min_pool_depth_before_export
        if depth < min_depth * 2:
            continue
        ratio = depth / max(1, min_depth)
        out.append(
            {
                "signal_type": "pool_backlog_pressure",
                "strength": min(1.0, round(ratio / 4, 3)),
                "confidence": "high" if depth >= min_depth * 3 else "medium",
                "network_key": nk,
                "pool_id": pid,
                "approved_depth": depth,
                "min_depth_policy": min_depth,
                "recommendation": (
                    f"Pool «{nk}» backlog {depth} approved (policy min {min_depth}) — increase export cadence."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x.get("approved_depth") or 0)))
    return out


def _signals_cache_stale_risk(db: Session) -> list[dict[str, Any]]:
    from app.services.export_flywheel_service import pool_id_for_network_key

    from app.data.export_lane_policy import all_lane_policies

    out: list[dict[str, Any]] = []
    for nk in all_lane_policies().keys():
        pid = pool_id_for_network_key(db, nk)
        if not pid:
            continue
        oldest = (
            db.query(Media)
            .filter(Media.pool_id == pid, Media.status == "approved")
            .order_by(Media.id.asc())
            .first()
        )
        if not oldest:
            continue
        created = getattr(oldest, "created_at", None)
        if not created:
            continue
        age_h = (datetime.utcnow() - created).total_seconds() / 3600.0
        if age_h < 24:
            continue
        strength = min(1.0, round(age_h / 168, 3))
        out.append(
            {
                "signal_type": "cache_stale_risk",
                "strength": strength,
                "confidence": "medium" if age_h >= 72 else "low",
                "network_key": nk,
                "pool_id": pid,
                "oldest_age_hours": round(age_h, 1),
                "recommendation": (
                    f"Lane «{nk}» has approved items aging {age_h:.0f}h — export oldest-first to keep flow fresh."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -float(x.get("oldest_age_hours") or 0)))
    return out


def _signals_surface_roi(db: Session, *, days: int) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.views_latest.isnot(None),
            PostDeliveryMetric.network_key.isnot(None),
        )
        .all()
    )
    by_lane_surf: dict[tuple[str, str], list[int]] = defaultdict(list)
    for r in rows:
        nk = (r.network_key or "").strip().lower()
        surf = (r.surface or "telegram").strip() or "telegram"
        if nk:
            by_lane_surf[(nk, surf)].append(int(r.views_latest or 0))

    out: list[dict[str, Any]] = []
    lanes = {nk for nk, _ in by_lane_surf.keys()}
    for nk in lanes:
        tg_vals = by_lane_surf.get((nk, "telegram"), [])
        er_vals = by_lane_surf.get((nk, "erome"), [])
        buf_vals = by_lane_surf.get((nk, "buffer_x"), [])
        if not tg_vals:
            continue
        tg_avg = sum(tg_vals) / len(tg_vals)
        surfaces: list[str] = ["telegram"]
        rec_parts = [f"Telegram baseline {tg_avg:.0f} views"]
        strength = 0.4
        if er_vals:
            er_avg = sum(er_vals) / len(er_vals)
            if er_avg > tg_avg * 1.1:
                surfaces.append("erome")
                strength = max(strength, min(1.0, er_avg / max(tg_avg, 1)))
                rec_parts.append(f"Erome {er_avg:.0f}")
        if buf_vals:
            buf_avg = sum(buf_vals) / len(buf_vals)
            if buf_avg > tg_avg * 1.05:
                surfaces.append("buffer_x")
                strength = max(strength, min(1.0, buf_avg / max(tg_avg, 1)))
                rec_parts.append(f"Buffer/X {buf_avg:.0f}")
        if len(surfaces) <= 1:
            continue
        out.append(
            {
                "signal_type": "surface_roi",
                "strength": round(strength, 3),
                "confidence": "medium",
                "network_key": nk,
                "surfaces": surfaces,
                "recommendation": (
                    f"Lane «{nk}» ROI favors {', '.join(surfaces)} ({'; '.join(rec_parts)})."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), x.get("network_key") or ""))
    return out


def _signals_market_intel(*, days: int = 14) -> list[dict[str, Any]]:
    """Erome browse-intel anomalies — tag velocity vs historical median."""
    try:
        from app.services.erome_browse_intel import aggregate_tag_scores, load_recent_rows
    except Exception:
        return []

    rows = [r for r in load_recent_rows(days=days) if str(r.get("platform") or "erome") == "erome"]
    if len(rows) < 20:
        return []
    tag_scores = aggregate_tag_scores(rows, platform="erome")
    if not tag_scores:
        return []

    out: list[dict[str, Any]] = []
    buckets: dict[str, list[float]] = {}
    for row in rows:
        vpd = row.get("views_per_day_proxy")
        if vpd is None:
            continue
        for tag in row.get("tags") or []:
            buckets.setdefault(tag, []).append(float(vpd))

    medians = {t: sorted(v)[len(v) // 2] for t, v in buckets.items() if len(v) >= 5}
    if not medians:
        return []
    global_median = sorted(medians.values())[len(medians) // 2]

    for tag, recent_score in sorted(tag_scores.items(), key=lambda x: -x[1])[:12]:
        hist = medians.get(tag, global_median)
        if hist <= 0:
            continue
        ratio = recent_score / hist
        if ratio < 1.35:
            continue
        strength = min(1.0, (ratio - 1.0) / 2.0)
        out.append(
            {
                "signal_type": "erome_market_anomaly",
                "strength": round(strength, 3),
                "confidence": "high" if ratio >= 2.0 else "medium",
                "tag": tag,
                "trigger_metric": "tag_score_vs_median_vpd",
                "current_value": round(recent_score, 1),
                "historical_median": round(hist, 1),
                "ratio": round(ratio, 2),
                "recommended_action": "BOOST_LANE_EXPORT" if ratio >= 2.0 else "INCREASE_POOL_CADENCE",
                "recommendation": (
                    f"Erome tag «{tag}» scoring {recent_score:.0f} vs median {hist:.0f} "
                    f"({ratio:.1f}×) — bias pool picks + upload tags."
                ),
            }
        )
    return out[:5]


def compute_strong_signals(db: Session, *, days: int | None = None) -> dict[str, Any]:
    """Ranked strongest content/growth signals (no side effects)."""
    days = days or signal_lookback_days()
    if not signals_enabled():
        return {"ok": True, "enabled": False, "signals": []}

    net_avg = _network_avg_views(db, days=days)
    peaks = _signals_peak_hours(db, days=days, network_avg=net_avg)
    captions = _signals_caption_winners(db, days=days, network_avg=net_avg)
    channels = _signals_channel_leaders(db, days=days, network_avg=net_avg)
    conversions = _signals_conversion_hours(db, days=days)
    lane_views = _signals_lane_view_leaders(db, days=days, network_avg=net_avg)
    lane_conversions = _signals_lane_conversion_leaders(db, days=days)
    backlog = _signals_pool_backlog_pressure(db)
    stale = _signals_cache_stale_risk(db)
    surface_roi = _signals_surface_roi(db, days=days)
    export_lane = []
    for s in lane_views[:3]:
        export_lane.append(
            {
                **s,
                "signal_type": "boost_lane_export",
                "recommendation": s.get("recommendation") or f"Boost exports for lane «{s.get('network_key')}».",
            }
        )
    for s in backlog[:3]:
        export_lane.append({**s, "signal_type": "increase_pool_cadence"})
    for s in surface_roi[:3]:
        export_lane.append({**s, "signal_type": "export_to_surface"})

    hub_web: list[dict[str, Any]] = []
    ga4_meta: dict[str, Any] = {"configured": False}
    try:
        from app.services.ga4_hub_analytics import (
            ga4_status,
            hub_device_signals,
            hub_geo_signals,
            hub_traffic_signals,
        )

        ga4_meta = ga4_status()
        if ga4_meta.get("configured"):
            hub_web = hub_traffic_signals(days=min(days, 14))
            hub_web.extend(hub_device_signals(days=min(days, 14)))
            hub_web.extend(hub_geo_signals(days=min(days, 14)))
    except Exception as e:
        ga4_meta = {"configured": False, "error": str(e)}

    industry: list[dict[str, Any]] = []
    try:
        from app.services.industry_intelligence import benchmark_informed_signals

        industry = benchmark_informed_signals(db)
    except Exception as e:
        logger.debug("industry benchmark signals: %s", e)

    market_intel = _signals_market_intel(days=min(days, 14))
    weekly_cycle: list[dict[str, Any]] = []
    try:
        from app.services.market_intel_cycle import cycle_signal_from_last_record

        sig = cycle_signal_from_last_record()
        if sig:
            weekly_cycle = [sig]
    except Exception as e:
        logger.debug("weekly cycle signal: %s", e)

    merged: list[dict[str, Any]] = []
    for bucket in (
        peaks,
        captions,
        channels,
        conversions,
        lane_views,
        lane_conversions,
        backlog,
        stale,
        surface_roi,
        export_lane,
        hub_web,
        industry,
        market_intel,
        weekly_cycle,
    ):
        merged.extend(bucket)

    filtered = [
        s
        for s in merged
        if s.get("confidence") in ("high", "medium")
        or float(s.get("strength") or 0) >= 0.55
    ]
    filtered.sort(key=lambda x: (-float(x.get("strength") or 0), str(x.get("signal_type"))))
    cap = max_signals_returned()
    top = filtered[:cap]

    return {
        "ok": True,
        "enabled": True,
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "lookback_days": days,
        "timezone": analytics_timezone_label(),
        "network_avg_views": round(net_avg, 1),
        "sample_thresholds": {
            "min_posts_per_hour": min_posts_per_hour(),
            "min_sends_per_slot": min_sends_per_slot(),
            "caption_win_ratio": caption_win_ratio(),
            "min_views": min_views_for_ranking(),
            "min_conversions_per_hour": min_conversions_per_hour(),
        },
        "reference_peak_hours_et": [{"start": s, "end": e % 24} for s, e in SUGGESTED_PEAK_HOURS_ET],
        "ga4_hub": ga4_meta,
        "signal_count": len(top),
        "signals": top,
    }


def _digest_hash(payload: dict[str, Any]) -> str:
    core = json.dumps(payload.get("signals") or [], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(core.encode()).hexdigest()[:16]


def format_signals_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TBCC growth signals",
        "",
        f"Lookback: {report.get('lookback_days')}d · tz={report.get('timezone')} · "
        f"network avg views={report.get('network_avg_views')}",
        "",
    ]
    signals = report.get("signals") or []
    if not signals:
        lines.append("_No high-confidence signals yet — need more deliveries with view refresh._")
        return "\n".join(lines)

    for i, s in enumerate(signals, 1):
        lines.append(
            f"{i}. **{s.get('signal_type')}** ({s.get('confidence')}, strength={s.get('strength')})"
        )
        lines.append(f"   {s.get('recommendation')}")
        lines.append("")
    return "\n".join(lines)


def tick_growth_signals(
    db: Session,
    *,
    refresh_views: bool = True,
    push_inbox_on_change: bool = True,
) -> dict[str, Any]:
    """
    Flywheel growth tick: refresh views → compute signals → inbox digest if changed.
    No instant DM; analytics-only lane.
    """
    if not signals_enabled():
        return {"ok": True, "enabled": False, "skipped": True}

    eligibility = assess_growth_tick_eligibility(db)
    if not eligibility.get("eligible"):
        return {
            "ok": True,
            "enabled": True,
            "skipped": True,
            "skip_reason": eligibility.get("reason"),
            "eligibility": eligibility,
            "digest_changed": False,
            "view_refresh": {"skipped": True, "reason": eligibility.get("reason")},
            "report": {"ok": True, "enabled": True, "signals": []},
            "markdown": "_Growth tick skipped — insufficient delivery/view/attribution data._",
            "proposed_actions": [],
        }

    view_refresh: dict[str, Any] = {"skipped": True}
    if refresh_views and performance_enabled() and eligibility.get("can_refresh_views"):
        try:
            view_refresh = refresh_delivery_views_sync(db, limit=200)
        except Exception as e:
            view_refresh = {"ok": False, "error": str(e)}
    elif refresh_views and performance_enabled() and not eligibility.get("can_refresh_views"):
        view_refresh = {
            "skipped": True,
            "reason": "insufficient_refreshable_deliveries",
            "footprint": eligibility.get("footprint"),
        }

    report = compute_strong_signals(db)
    digest = _digest_hash(report)
    prev = None
    try:
        r = _redis_client()
        prev = r.get(REDIS_LAST_DIGEST)
        r.set(REDIS_LAST_DIGEST, digest)
        r.set(REDIS_LAST_TICK, str(time.time()))
    except Exception as e:
        logger.debug("growth signals redis: %s", e)

    changed = prev is not None and prev != digest

    # Draft reaction proposals only when the digest changes — observe-only, no
    # execution. Lazy import avoids a circular dependency (growth_reaction imports
    # this module).
    proposed_actions: list[dict[str, Any]] = []
    if changed and report.get("signals"):
        try:
            from app.services.growth_reaction import propose_reactions

            proposed_actions = propose_reactions(report)
        except Exception as e:
            logger.debug("growth reaction proposals: %s", e)

    inbox_event = None
    if push_inbox_on_change and report.get("signals") and changed:
        try:
            from app.services.admin_inbox import push_admin_inbox_event

            preview = format_signals_markdown({**report, "signals": report["signals"][:5]})
            inbox_event = push_admin_inbox_event(
                category="system",
                severity="info",
                title=f"Growth signals ({len(report['signals'])} strong)",
                body=preview[:1200],
                meta={
                    "code": "growth_signals_digest",
                    "digest": digest,
                    "signal_count": len(report["signals"]),
                    "top_signal": report["signals"][0] if report["signals"] else None,
                },
                instant=False,
            )
        except Exception as e:
            logger.warning("growth signals inbox push failed: %s", e)

    return {
        "ok": True,
        "enabled": True,
        "digest": digest,
        "digest_changed": changed,
        "view_refresh": view_refresh,
        "report": report,
        "markdown": format_signals_markdown(report),
        "proposed_actions": proposed_actions,
        "inbox_event_id": (inbox_event or {}).get("id") if inbox_event else None,
    }


def growth_signals_status() -> dict[str, Any]:
    last_tick = None
    last_digest = None
    try:
        r = _redis_client()
        last_tick = r.get(REDIS_LAST_TICK)
        last_digest = r.get(REDIS_LAST_DIGEST)
    except Exception:
        pass
    ga4_hub: dict[str, Any] = {"configured": False}
    try:
        from app.services.ga4_hub_analytics import ga4_status

        ga4_hub = ga4_status()
    except Exception:
        pass
    return {
        "enabled": signals_enabled(),
        "flywheel_growth_tick": flywheel_growth_tick_enabled(),
        "openclaw_growth_tick": flywheel_growth_tick_enabled(),  # deprecated alias
        "lookback_days": signal_lookback_days(),
        "ga4_hub": ga4_hub,
        "thresholds": {
            "min_posts_per_hour": min_posts_per_hour(),
            "min_sends_per_slot": min_sends_per_slot(),
            "caption_win_ratio": caption_win_ratio(),
            "min_views": min_views_for_ranking(),
            "min_conversions_per_hour": min_conversions_per_hour(),
        },
        "last_tick_unix": float(last_tick) if last_tick else None,
        "last_digest": last_digest,
    }


def growth_signals_eligibility(db: Session) -> dict[str, Any]:
    """Public eligibility probe for OpenClaw / dashboard — no side effects."""
    out = assess_growth_tick_eligibility(db)
    out["skip_empty_ticks"] = skip_empty_growth_ticks()
    return out
