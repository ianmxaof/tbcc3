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
_ACTIONABLE = {"peak_post_hour", "caption_slot_winner", "channel_view_leader", "conversion_hour"}


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
    return f"{st}:{signal.get('hour_local') or signal.get('channel_id') or ''}"


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
    all_proposals = propose_reactions(report)
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
