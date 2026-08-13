"""Analytics direction — deterministic Top 5 investment ranking from TBCC evidence.

Composes ops picture, growth signals, proposals, funnel signals, and demand gaps.
Observe-only: no auto-schedule, auto-post, or bot starts.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.growth_reaction import list_proposals, propose_funnel_signals
from app.services.ops_picture_report import build_ops_picture_report
from app.services.traffic_pulse import traffic_pulse_snapshot
from app.services.undress_surge import spike_state

logger = logging.getLogger(__name__)

POOL_THIN_APPROVED = int(os.getenv("TBCC_DIRECTION_POOL_THIN", "500") or "500")
DIRECTION_COUNT = 5

_HORIZON_ORDER = {"ST": 0, "LT": 1, "OPS": 2}
_BLOCKER_HORIZON = {
    "revenue_stall": "ST",
    "companion_zero": "ST",
    "post_failures": "ST",
    "import_failures": "OPS",
    "attribution_blind": "LT",
    "external_untracked": "LT",
    "gate_no_touches": "ST",
}
_BLOCKER_REVERSIBILITY = {
    "revenue_stall": "config",
    "companion_zero": "config",
    "post_failures": "config",
    "import_failures": "config",
    "attribution_blind": "config",
    "external_untracked": "trivial",
    "gate_no_touches": "config",
}


def _tbcc_root() -> Path:
    env = (os.getenv("TBCC_ROOT") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def _sprint_in_flight_labels() -> list[str]:
    path = _tbcc_root() / "docs" / "SPRINT_STATE.md"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    labels: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("| Item"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            if line.strip().startswith("|------"):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts:
                labels.append(parts[0])
    return labels


def _sprint_alignment(title: str, labels: list[str]) -> str:
    if not labels:
        return "orthogonal"
    title_l = title.lower()
    for label in labels:
        label_l = label.lower()
        tokens = [t for t in re.split(r"[\s/\-+]+", label_l) if len(t) > 3]
        if any(t in title_l for t in tokens):
            return "aligned"
        if any(t in label_l for t in title_l.split() if len(t) > 4):
            return "aligned"
    return "gap"


def _pct_delta(current: float | int | None, prior: float | int | None) -> float | None:
    if current is None or prior is None:
        return None
    try:
        c, p = float(current), float(prior)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None if c == 0 else 100.0
    return round((c - p) / abs(p) * 100, 1)


def _window_income_usd(db: Session, *, days: int, offset_days: int = 0) -> float:
    from app.models.income_entry import IncomeEntry

    now = datetime.utcnow()
    end = now - timedelta(days=offset_days)
    start = end - timedelta(days=days)
    rows = (
        db.query(IncomeEntry)
        .filter(IncomeEntry.earned_at >= start, IncomeEntry.earned_at < end)
        .all()
    )
    total = 0.0
    for row in rows:
        cents = getattr(row, "amount_usd_cents", None) or getattr(row, "usd_cents", None) or 0
        total += float(cents or 0) / 100.0
    return round(total, 2)


def _compute_trends(db: Session, ops: dict[str, Any], *, days: int) -> dict[str, Any]:
    income = ops.get("income") or {}
    companion = ops.get("companion") or {}
    posts = ops.get("posts") or {}
    current_usd = float(income.get("total_usd") or 0)
    prior_usd = _window_income_usd(db, days=days, offset_days=days)
    current_sold = int(companion.get("photos_sold") or 0)
    prior_companion = None
    try:
        from app.services.companion_cogs import companion_margin_summary

        prior_companion = companion_margin_summary(db, days=days * 2)
        if prior_companion:
            full_sold = int(prior_companion.get("photos_sold") or 0)
            prior_sold = max(0, full_sold - current_sold)
        else:
            prior_sold = None
    except Exception:
        prior_sold = None

    ok_rate = None
    outbound = int(posts.get("outbound_total") or 0)
    if outbound > 0:
        failed = int(posts.get("outbound_failed") or 0)
        ok_rate = round((outbound - failed) / outbound * 100, 1)

    return {
        "income_usd": current_usd,
        "income_usd_prior_window": prior_usd,
        "income_usd_delta_pct": _pct_delta(current_usd, prior_usd),
        "companion_photos_sold": current_sold,
        "companion_photos_sold_prior_est": prior_sold,
        "companion_photos_sold_delta_pct": _pct_delta(current_sold, prior_sold),
        "post_ok_rate_pct": ok_rate,
    }


def _evidence_summary(ops: dict[str, Any]) -> dict[str, Any]:
    income = ops.get("income") or {}
    companion = ops.get("companion") or {}
    pools = ops.get("pools") or {}
    posts = ops.get("posts") or {}
    return {
        "income_usd": income.get("total_usd"),
        "income_stars": income.get("total_stars"),
        "companion_photos_sold": companion.get("photos_sold"),
        "pool_approved": pools.get("approved_total"),
        "post_failure_pct": posts.get("failure_pct"),
        "blocker_count": len(ops.get("blockers") or []),
    }


def _detect_contradictions(
    ops: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    approved = int((ops.get("pools") or {}).get("approved_total") or 0)
    thin = approved < POOL_THIN_APPROVED
    for p in proposals:
        kind = p.get("action_kind") or p.get("kind") or ""
        if thin and kind in ("increase_pool_cadence", "increase_channel_frequency"):
            contradictions.append(
                {
                    "code": "thin_pool_vs_post_more",
                    "message": (
                        f"Pool approved={approved} (<{POOL_THIN_APPROVED}) conflicts with "
                        f"«{kind}» — refill or pause auto-post first."
                    ),
                    "proposal_id": p.get("id"),
                }
            )
    posts = ops.get("posts") or {}
    if float(posts.get("failure_pct") or 0) >= 20:
        for p in proposals:
            if (p.get("action_kind") or "") == "schedule_hour_bias":
                contradictions.append(
                    {
                        "code": "post_failures_vs_schedule_bias",
                        "message": "High post failure rate — fix scheduler errors before hour bias.",
                        "proposal_id": p.get("id"),
                    }
                )
                break
    return contradictions


def build_direction_evidence_bundle(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Compose read-only evidence for direction ranking."""
    ops = build_ops_picture_report(db, days=days)
    from app.services import content_signals as cs

    signals_report = cs.compute_strong_signals(db, days=days)
    growth = list_proposals(db, days=days)
    funnel_signals = propose_funnel_signals(ops, spike_state())
    traffic = traffic_pulse_snapshot()
    trends = _compute_trends(db, ops, days=days)
    contradictions = _detect_contradictions(ops, growth.get("proposals") or [])

    category_demand: dict[str, Any] = {"ok": False}
    try:
        from app.services.category_demand_crosswalk import compute_category_demand_crosswalk

        category_demand = compute_category_demand_crosswalk(db)
    except Exception as e:
        category_demand = {"ok": False, "error": str(e)[:200]}

    export_proposals: list[dict[str, Any]] = []
    try:
        from app.services.export_flywheel_service import build_export_proposals

        export_proposals = build_export_proposals(db)[:5]
    except Exception as e:
        logger.debug("export proposals skipped: %s", e)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "ops": ops,
        "signals": (signals_report.get("signals") or [])[:8],
        "growth_proposals": growth.get("proposals") or [],
        "funnel_signals": funnel_signals,
        "export_proposals": export_proposals,
        "traffic_pulse": traffic,
        "trends": trends,
        "contradictions": contradictions,
        "category_demand": category_demand,
        "evidence_summary": _evidence_summary(ops),
        "sprint_labels": _sprint_in_flight_labels(),
    }


def _dedupe_key(direction: dict[str, Any]) -> str:
    kind = direction.get("action_kind") or direction.get("source_id") or ""
    entity = (
        direction.get("network_key")
        or direction.get("hour_local")
        or direction.get("blocker_id")
        or direction.get("title", "")[:40]
    )
    return f"{kind}:{entity}"


def _blocker_direction(b: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    bid = b.get("id") or "blocker"
    title = str(b.get("what") or bid)
    sev = b.get("severity") or "medium"
    score = 1200 if sev == "high" else 700
    return {
        "source": "blocker",
        "source_id": bid,
        "blocker_id": bid,
        "action_kind": f"fix_{bid}",
        "title": title,
        "rationale": str(b.get("why") or ""),
        "evidence": [str(b.get("evidence") or "")],
        "horizon": _BLOCKER_HORIZON.get(bid, "ST"),
        "category": "fix",
        "confidence": "high" if sev == "high" else "medium",
        "reversibility": _BLOCKER_REVERSIBILITY.get(bid, "config"),
        "mcp_followup": "GET /analytics/ops-picture · tbcc-stack-cli Status",
        "sprint_alignment": _sprint_alignment(title, labels),
        "_score": score,
    }


def _proposal_direction(p: dict[str, Any], labels: list[str], *, penalty: int = 0) -> dict[str, Any]:
    kind = p.get("action_kind") or p.get("kind") or "review"
    params = p.get("action_params") or p
    title = str(p.get("recommendation") or kind)[:200]
    strength = float(p.get("strength") or 0.5)
    conf = p.get("confidence") or "medium"
    conf_boost = {"high": 80, "medium": 40, "low": 10}.get(str(conf), 40)
    category = "pause" if kind == "increase_pool_cadence" and penalty else "grow"
    if kind in ("export_to_surface", "boost_lane_export"):
        category = "invest"
    horizon = "LT" if category == "invest" else "ST"
    return {
        "source": "growth_proposal",
        "source_id": p.get("id"),
        "action_kind": kind,
        "title": title,
        "rationale": str(params.get("suggested_note") or title),
        "evidence": [
            f"strength={strength:.2f}",
            f"signal_type={p.get('signal_type') or kind}",
        ],
        "horizon": horizon,
        "category": category,
        "confidence": str(conf),
        "reversibility": "trivial",
        "mcp_followup": str(params.get("mcp_followup") or "growth_signal_proposals"),
        "network_key": p.get("network_key") or params.get("network_key"),
        "hour_local": p.get("hour_local") or params.get("target_hour_local"),
        "sprint_alignment": _sprint_alignment(title, labels),
        "_score": int(strength * 100) + conf_boost - penalty,
    }


def _funnel_direction(s: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    st = s.get("signal_type") or "funnel"
    title = str(s.get("recommendation") or st)
    strength = float(s.get("strength") or 1.0)
    return {
        "source": "funnel_signal",
        "source_id": st,
        "action_kind": st,
        "title": title[:200],
        "rationale": title,
        "evidence": [f"hits={s.get('hits_in_window')}", f"photos_sold={s.get('photos_sold')}"],
        "horizon": "ST",
        "category": "grow",
        "confidence": str(s.get("confidence") or "medium"),
        "reversibility": "trivial",
        "mcp_followup": "secretary /surge · companion CTAs",
        "sprint_alignment": _sprint_alignment(title, labels),
        "_score": int(900 + strength * 10) if st == "bridge_undress_funnel" else 650,
    }


def _pool_pressure_direction(ops: dict[str, Any], labels: list[str]) -> dict[str, Any] | None:
    approved = int((ops.get("pools") or {}).get("approved_total") or 0)
    if approved >= POOL_THIN_APPROVED:
        return None
    title = f"Refill loot pools — approved={approved} below {POOL_THIN_APPROVED}"
    return {
        "source": "pool_pressure",
        "source_id": "pool_thin",
        "action_kind": "pool_refill",
        "title": title,
        "rationale": "Thin approved queue risks empty rolls and stalled lane auto-post.",
        "evidence": [f"pool_approved={approved}", f"threshold={POOL_THIN_APPROVED}"],
        "horizon": "ST",
        "category": "fix",
        "confidence": "high",
        "reversibility": "config",
        "mcp_followup": "loot_durability_check.py --apply-refill --unpause",
        "sprint_alignment": _sprint_alignment("loot pool import starvation", labels),
        "_score": 950,
    }


def _demand_gap_directions(category_demand: dict[str, Any], labels: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for gap in (category_demand.get("gaps") or [])[:3]:
        slug = gap.get("slug") or gap.get("category") or "category"
        title = f"Close demand gap: {slug}"
        out.append(
            {
                "source": "category_demand",
                "source_id": slug,
                "action_kind": "intel_tag_boost",
                "title": title,
                "rationale": str(gap.get("note") or gap.get("recommendation") or "Supply below benchmark demand."),
                "evidence": [f"gap_score={gap.get('gap_score')}", f"demand_index={gap.get('demand_index')}"],
                "horizon": "LT",
                "category": "invest",
                "confidence": "medium",
                "reversibility": "config",
                "mcp_followup": "Field Intel ingest · pool tag scores",
                "sprint_alignment": _sprint_alignment(title, labels),
                "_score": 400 + int(float(gap.get("gap_score") or 0)),
            }
        )
    return out


def _export_direction(p: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    kind = p.get("kind") or "export"
    nk = p.get("network_key") or ""
    title = str(p.get("recommendation") or f"Export flywheel: {kind} {nk}".strip())
    return {
        "source": "export_flywheel",
        "source_id": p.get("id"),
        "action_kind": kind,
        "title": title[:200],
        "rationale": title,
        "evidence": [f"network_key={nk}", f"confidence={p.get('confidence')}"],
        "horizon": "LT",
        "category": "invest",
        "confidence": str(p.get("confidence") or "medium"),
        "reversibility": "config",
        "mcp_followup": "export-flywheel proposals · deploy_campaign_post",
        "network_key": nk,
        "sprint_alignment": _sprint_alignment(title, labels),
        "_score": 350 + int(float(p.get("strength") or 0) * 50),
    }


def _fallback_direction(labels: list[str]) -> dict[str, Any]:
    title = "Maintain checkout + schedulers — no critical blockers"
    return {
        "source": "fallback",
        "source_id": "maintain",
        "action_kind": "maintain_revenue_ops",
        "title": title,
        "rationale": "Keep loot/VIP fulfillment and lane auto-post healthy while testing growth bets.",
        "evidence": ["blocker_count=0"],
        "horizon": "ST",
        "category": "grow",
        "confidence": "low",
        "reversibility": "trivial",
        "mcp_followup": "analytics_weekly_summary · tbcc_health",
        "sprint_alignment": _sprint_alignment("revenue island", labels),
        "_score": 100,
    }


def rank_directions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge evidence into ranked directions (max 5)."""
    ops = bundle.get("ops") or {}
    labels = bundle.get("sprint_labels") or []
    contradictions = {c.get("proposal_id") for c in (bundle.get("contradictions") or [])}
    penalty_ids = contradictions

    candidates: list[dict[str, Any]] = []

    for b in ops.get("blockers") or []:
        candidates.append(_blocker_direction(b, labels))

    pool_dir = _pool_pressure_direction(ops, labels)
    if pool_dir:
        candidates.append(pool_dir)

    for s in bundle.get("funnel_signals") or []:
        candidates.append(_funnel_direction(s, labels))

    thin = int((ops.get("pools") or {}).get("approved_total") or 0) < POOL_THIN_APPROVED
    for p in bundle.get("growth_proposals") or []:
        penalty = 200 if (p.get("id") in penalty_ids or thin) and (
            (p.get("action_kind") or "") in ("increase_pool_cadence", "increase_channel_frequency")
        ) else 0
        candidates.append(_proposal_direction(p, labels, penalty=penalty))

    for p in bundle.get("export_proposals") or []:
        candidates.append(_export_direction(p, labels))

    candidates.extend(_demand_gap_directions(bundle.get("category_demand") or {}, labels))

    if not candidates:
        candidates.append(_fallback_direction(labels))

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for c in sorted(
        candidates,
        key=lambda d: (-int(d.get("_score") or 0), _HORIZON_ORDER.get(d.get("horizon") or "OPS", 9)),
    ):
        key = _dedupe_key(c)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    if not any(c.get("source") == "blocker" for c in deduped[:DIRECTION_COUNT]):
        if not deduped or deduped[0].get("_score", 0) < 200:
            deduped.append(_fallback_direction(labels))
            deduped = sorted(
                deduped,
                key=lambda d: (-int(d.get("_score") or 0), _HORIZON_ORDER.get(d.get("horizon") or "OPS", 9)),
            )

    out: list[dict[str, Any]] = []
    for i, d in enumerate(deduped[:DIRECTION_COUNT], start=1):
        row = {k: v for k, v in d.items() if not k.startswith("_")}
        row["rank"] = i
        out.append(row)
    return out


def format_direction_markdown(bundle: dict[str, Any], directions: list[dict[str, Any]]) -> str:
    lines = [
        f"# TBCC analytics direction ({bundle.get('window_days')}d)",
        "",
        "## Evidence",
    ]
    summary = bundle.get("evidence_summary") or {}
    for k, v in summary.items():
        lines.append(f"- **{k}**: {v}")
    trends = bundle.get("trends") or {}
    if trends.get("income_usd_delta_pct") is not None:
        lines.append(f"- **income_usd_delta_pct**: {trends['income_usd_delta_pct']}%")
    lines.append("")
    lines.append("## Directions")
    for d in directions:
        lines.append(
            f"{d['rank']}. **[{d['horizon']}]** {d['title']} "
            f"({d['category']}, {d['confidence']}) — {d.get('rationale', '')[:120]}"
        )
        if d.get("mcp_followup"):
            lines.append(f"   - follow-up: `{d['mcp_followup']}`")
    contradictions = bundle.get("contradictions") or []
    lines.append("")
    lines.append("## Contradictions")
    if contradictions:
        for c in contradictions:
            lines.append(f"- {c.get('message')}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def format_direction_html(directions: list[dict[str, Any]], *, narrative: str | None = None) -> str:
    from app.services.secretary_report_copy import format_direction_report_html

    return format_direction_report_html(directions, narrative=narrative)


def draft_direction_narrative(
    bundle: dict[str, Any],
    directions: list[dict[str, Any]],
    *,
    use_llm: bool = True,
) -> str | None:
    if not use_llm or not directions:
        return None
    try:
        from app.services.llm_completions import complete_chat_text_sync, resolve_text_llm_runtime

        runtime = resolve_text_llm_runtime()
        if not runtime.api_key:
            return None
        payload = {
            "evidence_summary": bundle.get("evidence_summary"),
            "trends": bundle.get("trends"),
            "directions": [{k: d.get(k) for k in ("rank", "title", "horizon", "category")} for d in directions],
        }
        system = (
            "You are TBCC operator advisor. Write 2-4 plain sentences explaining WHY direction #1 "
            "ranks above #2. Do NOT reorder or add new actions. No markdown. Max 400 chars."
        )
        user = json.dumps(payload, default=str)[:8000]
        text = complete_chat_text_sync(
            runtime,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=200,
            temperature=0.3,
        )
        body = (text or "").strip()
        return body[:400] if body else None
    except Exception as e:
        logger.warning("direction narrative LLM failed: %s", e)
        return None


def build_analytics_direction_report(
    db: Session,
    *,
    days: int = 30,
    use_llm: bool = False,
) -> dict[str, Any]:
    bundle = build_direction_evidence_bundle(db, days=days)
    directions = rank_directions(bundle)
    narrative = draft_direction_narrative(bundle, directions, use_llm=use_llm)
    return {
        "ok": True,
        "generated_at": bundle.get("generated_at"),
        "window_days": days,
        "directions": directions,
        "contradictions": bundle.get("contradictions") or [],
        "trends": bundle.get("trends") or {},
        "narrative": narrative,
        "evidence_summary": bundle.get("evidence_summary") or {},
        "markdown": format_direction_markdown(bundle, directions),
    }
