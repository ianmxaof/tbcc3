"""Growth reaction proposals — turn ranked growth signals into reviewable draft actions.

Observe-only by design: a proposal is a *suggestion* with concrete params an
operator (or, after explicit approval, OpenClaw) could act on. Nothing here posts
to Telegram, changes schedules, or touches money. It mirrors the ops-flywheel
"report, then act only after operator OK" policy.

Storage is Redis-backed (no new table/migration): each proposal id is a stable
hash of the signal's identity, so a dismissal survives signal recomputation on
the next tick. Dismissed ids live in a Redis set.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services import content_signals as cs

logger = logging.getLogger(__name__)

REDIS_DISMISSED_SET = "tbcc:growth_signals:proposals_dismissed"

# Signal type -> (action_kind, param builder). Only the actionable core signals
# become proposals; observational ones (hub_web, industry_benchmark) do not.
_ACTIONABLE = {
    "peak_post_hour",
    "caption_slot_winner",
    "channel_view_leader",
    "conversion_hour",
    "boost_lane_export",
    "increase_pool_cadence",
    "export_to_surface",
    "lane_view_leader",
    "lane_conversion_leader",
    "pool_backlog_pressure",
    "cache_stale_risk",
    "surface_roi",
    "erome_market_anomaly",
    "market_intel_weekly_cycle",
    "bridge_undress_funnel",
    "boost_companion_cta",
}


def _identity(signal: dict[str, Any]) -> str:
    """Stable identity string for a signal, independent of volatile metrics.

    Uses only the fields that define *which* opportunity this is, not its current
    strength/avg_views, so the same recurring opportunity keeps the same id.
    """
    st = signal.get("signal_type")
    if st == "peak_post_hour":
        return f"peak_post_hour:{signal.get('hour_local')}"
    if st == "caption_slot_winner":
        return f"caption_slot_winner:{signal.get('scheduled_post_id')}:{signal.get('caption_slot_index')}"
    if st == "channel_view_leader":
        return f"channel_view_leader:{signal.get('channel_id')}"
    if st == "conversion_hour":
        return f"conversion_hour:{signal.get('hour_local')}"
    if st in ("boost_lane_export", "lane_view_leader", "increase_pool_cadence", "pool_backlog_pressure", "cache_stale_risk"):
        return f"{st}:{signal.get('network_key')}"
    if st in ("export_to_surface", "surface_roi"):
        return f"{st}:{signal.get('network_key')}:{','.join(signal.get('surfaces') or [])}"
    if st == "lane_conversion_leader":
        return f"lane_conversion_leader:{signal.get('network_key')}"
    if st == "erome_market_anomaly":
        return f"erome_market_anomaly:{signal.get('tag')}"
    if st == "market_intel_weekly_cycle":
        return f"market_intel_weekly_cycle:{signal.get('week_id') or signal.get('tag')}"
    if st == "bridge_undress_funnel":
        return f"bridge_undress_funnel:{signal.get('tag') or 'undress'}"
    if st == "boost_companion_cta":
        return "boost_companion_cta:companion"
    return f"{st}:{signal.get('hour_local') or signal.get('channel_id') or signal.get('network_key') or ''}"


def _proposal_id(signal: dict[str, Any]) -> str:
    return hashlib.sha256(_identity(signal).encode()).hexdigest()[:12]


def _build_action(signal: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map a signal to (action_kind, action_params) — metadata only, no execution."""
    st = signal["signal_type"]
    if st == "peak_post_hour":
        return "schedule_hour_bias", {
            "target_hour_local": signal.get("hour_local"),
            "suggested_note": (
                f"Bias recurring schedules toward hour {signal.get('hour_local')} local."
            ),
            "mcp_followup": "list_scheduled_posts (review interval_minutes / next run near this hour)",
        }
    if st == "caption_slot_winner":
        return "caption_slot_reuse", {
            "scheduled_post_id": signal.get("scheduled_post_id"),
            "caption_slot_index": signal.get("caption_slot_index"),
            "suggested_note": (
                f"Favor caption slot {signal.get('caption_slot_index')} on "
                f"«{signal.get('scheduler_name')}»."
            ),
            "mcp_followup": "list_scheduled_posts (inspect this job's caption rotation)",
        }
    if st == "channel_view_leader":
        return "increase_channel_frequency", {
            "channel_id": signal.get("channel_id"),
            "channel_name": signal.get("channel_name"),
            "suggested_note": (
                f"Consider more frequent posts / cross-promo on «{signal.get('channel_name')}»."
            ),
            "mcp_followup": "list_channels, list_scheduled_posts (raise cadence for this lane)",
        }
    if st == "conversion_hour":
        return "align_cta_window", {
            "target_hour_local": signal.get("hour_local"),
            "suggested_note": (
                f"Align high-intent CTAs (VIP/loot) to hour {signal.get('hour_local')} local."
            ),
            "mcp_followup": "list_scheduled_posts (time promo posts to this window)",
        }
    if st in ("boost_lane_export", "lane_view_leader"):
        return "boost_lane_export", {
            "network_key": signal.get("network_key"),
            "pool_id": signal.get("pool_id"),
            "surfaces": signal.get("surfaces") or ["telegram", "erome"],
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "GET /analytics/export-flywheel/proposals",
        }
    if st in ("increase_pool_cadence", "pool_backlog_pressure"):
        return "increase_pool_cadence", {
            "network_key": signal.get("network_key"),
            "pool_id": signal.get("pool_id"),
            "approved_depth": signal.get("approved_depth"),
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "post_pool or lower ContentPool.interval_minutes",
        }
    if st in ("export_to_surface", "surface_roi"):
        return "export_to_surface", {
            "network_key": signal.get("network_key"),
            "surfaces": signal.get("surfaces") or ["telegram"],
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "campaign deploy with selected surfaces",
        }
    if st == "cache_stale_risk":
        return "export_oldest_first", {
            "network_key": signal.get("network_key"),
            "pool_id": signal.get("pool_id"),
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "TBCC_EXPORT_FLYWHEEL_RANK_PICKS=1 (rank pool picks)",
        }
    if st == "lane_conversion_leader":
        return "boost_lane_export", {
            "network_key": signal.get("network_key"),
            "surfaces": ["telegram"],
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "VIP/loot CTAs on hot lane",
        }
    if st == "erome_market_anomaly":
        return "intel_tag_boost", {
            "tag": signal.get("tag"),
            "ratio": signal.get("ratio"),
            "surfaces": ["telegram", "buffer_x", "erome"],
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "GET /analytics/market-intel/upload-hints",
        }
    if st == "market_intel_weekly_cycle":
        return "intel_cycle_post", {
            "tag": signal.get("tag"),
            "week_id": signal.get("week_id"),
            "top_tags": signal.get("top_tags") or [],
            "surfaces": ["telegram", "buffer_x", "reddit"],
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "POST /analytics/market-intel/cycle/run",
        }
    if st == "bridge_undress_funnel":
        return "bridge_undress_funnel", {
            "suggested_note": signal.get("recommendation"),
            "hits_in_window": signal.get("hits_in_window"),
            "mcp_followup": "secretary /surge · companion post-credit CTAs · beacon wrap",
        }
    if st == "boost_companion_cta":
        return "boost_companion_cta", {
            "photos_sold": signal.get("photos_sold"),
            "suggested_note": signal.get("recommendation"),
            "mcp_followup": "companion exhaustion keyboard · Stars invoice path",
        }
    return "review", {"suggested_note": signal.get("recommendation")}


def propose_reactions(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: derive draft proposals from a computed signals report. No side effects."""
    tz = report.get("timezone")
    out: list[dict[str, Any]] = []
    for signal in report.get("signals") or []:
        st = signal.get("signal_type")
        if st not in _ACTIONABLE:
            continue
        action_kind, action_params = _build_action(signal)
        if "target_hour_local" in action_params or st == "peak_post_hour":
            action_params.setdefault("timezone", tz)
        out.append(
            {
                "id": _proposal_id(signal),
                "signal_type": st,
                "confidence": signal.get("confidence"),
                "strength": signal.get("strength"),
                "recommendation": signal.get("recommendation"),
                "action_kind": action_kind,
                "action_params": {k: v for k, v in action_params.items() if v is not None},
                "status": "pending",
            }
        )
    return out


def propose_funnel_signals(ops_report: dict[str, Any], undress_spike: dict[str, Any]) -> list[dict[str, Any]]:
    """Synthetic funnel signals for revenue brief + growth reaction (observe-only)."""
    out: list[dict[str, Any]] = []
    if undress_spike.get("spike_active") or int(undress_spike.get("hits_in_window") or 0) >= 3:
        out.append(
            {
                "signal_type": "bridge_undress_funnel",
                "confidence": "high" if undress_spike.get("spike_active") else "medium",
                "strength": float(undress_spike.get("hits_in_window") or 0),
                "hits_in_window": undress_spike.get("hits_in_window"),
                "tag": "undress",
                "recommendation": (
                    "Undress affiliate traffic is spiking — bridge to loot keys/VIP "
                    "(companion CTAs + /surge blast to mainhub + loot room)."
                ),
            }
        )
    companion = ops_report.get("companion") or {}
    sold = companion.get("photos_sold")
    if sold is not None and int(sold) == 0:
        out.append(
            {
                "signal_type": "boost_companion_cta",
                "confidence": "medium",
                "strength": 1.0,
                "photos_sold": 0,
                "recommendation": (
                    "Companion Stars photos_sold=0 — post-credit loot/VIP keyboard is the conversion gap."
                ),
            }
        )
    return out


def propose_reactions_with_funnel(
    report: dict[str, Any],
    *,
    ops_report: dict[str, Any] | None = None,
    undress_spike: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Merge content signals with funnel synthetic signals."""
    signals = list(report.get("signals") or [])
    if ops_report is not None:
        spike = undress_spike if undress_spike is not None else {}
        signals.extend(propose_funnel_signals(ops_report, spike))
    merged_report = {**report, "signals": signals}
    return propose_reactions(merged_report)


def _dismissed_ids() -> set[str]:
    try:
        r = cs._redis_client()
        members = r.smembers(REDIS_DISMISSED_SET)
        return set(members or [])
    except Exception as e:  # noqa: BLE001 - redis optional
        logger.debug("growth proposals dismissed read failed: %s", e)
        return set()


def list_proposals(db: Session, *, days: int | None = None) -> dict[str, Any]:
    """Pending (non-dismissed) proposals derived from the current signals report."""
    report = cs.compute_strong_signals(db, days=days) if days else cs.compute_strong_signals(db)
    from app.services.ops_picture_report import build_ops_picture_report
    from app.services.undress_surge import spike_state

    ops = build_ops_picture_report(db, days=days or 7)
    all_proposals = propose_reactions_with_funnel(
        report, ops_report=ops, undress_spike=spike_state()
    )
    dismissed = _dismissed_ids()
    pending = [p for p in all_proposals if p["id"] not in dismissed]
    return {
        "ok": True,
        "enabled": report.get("enabled", True),
        "computed_at": report.get("computed_at"),
        "proposal_count": len(pending),
        "dismissed_count": len(all_proposals) - len(pending),
        "proposals": pending,
    }


def dismiss_proposal(proposal_id: str) -> dict[str, Any]:
    """Mark a proposal dismissed so it stops surfacing (survives recompute)."""
    pid = (proposal_id or "").strip()
    if not pid:
        return {"ok": False, "error": "empty proposal id"}
    try:
        r = cs._redis_client()
        r.sadd(REDIS_DISMISSED_SET, pid)
        return {"ok": True, "id": pid, "dismissed": True}
    except Exception as e:  # noqa: BLE001
        logger.warning("growth proposal dismiss failed: %s", e)
        return {"ok": False, "id": pid, "error": str(e)}
