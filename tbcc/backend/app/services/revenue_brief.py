"""Daily LLM revenue brief — spectrum Top 5 (now / week / quarter) from structured ops data.

Growth reaction / export flywheel context (stale-but-useful):
- content_signals + growth_reaction: observe-only scheduling/content proposals; no auto-post.
- ops_flywheel: infra fixes with Secretary approval for destructive lanes.
- export_flywheel: observe mode — proposals only.
This brief ingests their outputs as evidence; it does not auto-execute growth proposals.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.services.traffic_pulse import traffic_pulse_snapshot
from app.services.undress_surge import spike_state

logger = logging.getLogger(__name__)

REDIS_DEDUPE = "tbcc:revenue_brief:sent"


def revenue_brief_enabled() -> bool:
    raw = (os.getenv("TBCC_REVENUE_BRIEF_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def revenue_brief_timezone() -> ZoneInfo:
    tz = (os.getenv("TBCC_REVENUE_BRIEF_TZ") or "America/Los_Angeles").strip()
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("America/Los_Angeles")


def revenue_brief_local_hour() -> int:
    raw = (os.getenv("TBCC_REVENUE_BRIEF_LOCAL_HOUR") or "9").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 9


def revenue_brief_local_minute() -> int:
    raw = (os.getenv("TBCC_REVENUE_BRIEF_LOCAL_MINUTE") or "30").strip()
    try:
        return max(0, min(59, int(raw)))
    except ValueError:
        return 30


def is_revenue_brief_due(now_utc: datetime | None = None) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(revenue_brief_timezone())
    return local.hour == revenue_brief_local_hour() and local.minute == revenue_brief_local_minute()


def _redis():
    from app.services.admin_inbox import _redis_client

    return _redis_client()


def build_revenue_brief_bundle(db: Session, *, days: int = 7) -> dict[str, Any]:
    from app.services.analytics_direction import (
        build_direction_evidence_bundle,
        rank_directions,
    )

    evidence = build_direction_evidence_bundle(db, days=days)
    ops = evidence.get("ops") or {}
    directions = rank_directions(evidence)
    growth = {"proposals": evidence.get("growth_proposals") or []}
    funnel_signals = evidence.get("funnel_signals") or []
    proposals = (growth.get("proposals") or [])[:3]
    income = ops.get("income") or {}
    companion = ops.get("companion") or {}
    bot_funnel = ops.get("bot_funnel") or {}
    return {
        "generated_at": evidence.get("generated_at"),
        "window_days": days,
        "income_usd": income.get("total_usd"),
        "income_stars": income.get("total_stars"),
        "companion_photos_sold": companion.get("photos_sold"),
        "companion_margin_unknown": companion.get("margin_unknown"),
        "bot_funnel": {
            k: bot_funnel.get(k)
            for k in ("attributed_revenue_pct", "touches", "revenue_usd")
            if bot_funnel.get(k) is not None
        },
        "blockers": (ops.get("blockers") or [])[:5],
        "gate_funnel_totals": (ops.get("gate_funnel") or {}).get("totals"),
        "undress_spike": spike_state(),
        "traffic_pulse": evidence.get("traffic_pulse") or traffic_pulse_snapshot(),
        "growth_proposals": proposals,
        "funnel_signals": funnel_signals,
        "directions": directions,
        "growth_flywheel_note": (
            "Growth proposals are observe-only; export flywheel observe; ops flywheel for infra."
        ),
    }


def _heuristic_brief(bundle: dict[str, Any]) -> str:
    from app.services.secretary_report_copy import format_heuristic_brief_html

    return format_heuristic_brief_html(bundle)


def html_escape(s: str) -> str:
    import html

    return html.escape(s)


def draft_revenue_brief_html(bundle: dict[str, Any], *, use_llm: bool = True) -> str:
    if not use_llm:
        return _heuristic_brief(bundle)
    try:
        from app.services.llm_completions import complete_chat_text_sync, resolve_text_llm_runtime

        runtime = resolve_text_llm_runtime()
        if not runtime.api_key:
            return _heuristic_brief(bundle)
        system = (
            "You are the AOF operator secretary. Output Telegram HTML (parse_mode=HTML) only — "
            "tags allowed: <b> <i> <u> <code> <blockquote>. No markdown. "
            "Start with: 💰 <b>Daily revenue brief</b> · <u>operator read</u> "
            "then a <b>Snapshot</b> of the real numbers (ledger, companion photos, pulse). "
            "Then exactly 5 numbered moves ranked by short-term $ first. "
            "Each move: N. <u>now|this week|this quarter</u> — <b>title</b> "
            "then a <blockquote> with one charitable plain-language explanation of the number "
            "AND one action the operator can do in the next hour "
            "(named command like /surge /sponsors /loot or a specific CTA). "
            "Include at least one week or quarter item when evidence supports compounding bets. "
            "Max 24 lines. Be specific to the JSON. Never invent revenue that is not in the bundle."
        )
        user = json.dumps(bundle, default=str)[:12000]
        text = complete_chat_text_sync(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=800,
            temperature=0.3,
            runtime=runtime,
        )
        body = (text or "").strip()
        if body and len(body) > 80:
            return body[:3900]
    except Exception as e:
        logger.warning("revenue brief LLM failed: %s", e)
    return _heuristic_brief(bundle)


def _already_sent_today() -> bool:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        r = _redis()
        val = r.get(REDIS_DEDUPE)
        if isinstance(val, bytes):
            val = val.decode()
        return val == day
    except Exception:
        return False


def _mark_sent_today() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        r = _redis()
        r.set(REDIS_DEDUPE, day, ex=60 * 60 * 48)
    except Exception:
        pass


def send_revenue_brief(db: Session, *, force: bool = False, use_llm: bool = True) -> dict[str, Any]:
    if not revenue_brief_enabled() and not force:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    if not force:
        if not is_revenue_brief_due():
            return {"ok": True, "skipped": True, "reason": "wrong_local_time"}
        if _already_sent_today():
            return {"ok": True, "skipped": True, "reason": "already_sent_today"}

    bundle = build_revenue_brief_bundle(db)
    html_body = draft_revenue_brief_html(bundle, use_llm=use_llm)

    try:
        from app.services.admin_inbox import push_admin_inbox_event

        ev = push_admin_inbox_event(
            category="system",
            severity="important",
            title="Daily revenue brief",
            body=html_body,
            meta={"code": "revenue_brief", "bundle": bundle},
            instant=True,
        )
    except Exception as e:
        logger.exception("revenue brief inbox failed")
        return {"ok": False, "error": str(e)[:300]}

    _mark_sent_today()
    return {"ok": True, "event_id": (ev or {}).get("id"), "chars": len(html_body), "bundle_keys": list(bundle.keys())}
