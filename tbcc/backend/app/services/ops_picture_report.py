"""Build a point-in-time TBCC ops picture — analytics, cash flow, ops health, blockers."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.goblin_claim import GoblinClaim
from app.models.goblin_drop import GoblinDrop
from app.models.import_job import ImportJob
from app.models.income_entry import IncomeEntry
from app.models.listening_relay_post_log import ListeningRelayPostLog
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.media import Media
from app.models.post_outbound_event import PostOutboundEvent
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.services.bot_funnel_analytics import bot_funnel_summary
from app.services.companion_cogs import companion_margin_summary
from app.services.gate_funnel import gate_funnel_report
from app.services.income_ledger import (
    SOURCE_LINKVERTISE,
    income_summary,
    list_income_entries,
    stars_usd_rate,
)
from app.services.income_sync import get_income_poll_status
from app.services.post_scheduler import schedulers_stall_summary
from app.services.system_health import scheduling_fast_snapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat() + "Z"


def stars_cashflow_summary(db: Session, *, hold_days: int | None = None) -> dict[str, Any]:
    """Reconcile TBCC ledger Stars vs Telegram Fragment hold rules."""
    hold = hold_days if hold_days is not None else int(
        (os.getenv("TBCC_STARS_WITHDRAW_HOLD_DAYS") or "21").strip() or "21"
    )
    now = _utcnow()
    cutoff = now - timedelta(days=max(0, hold))

    xtr_rows = db.query(IncomeEntry).filter(IncomeEntry.currency == "XTR").all()
    ledger_stars = sum(int(r.amount_minor or 0) for r in xtr_rows)
    available_stars = sum(
        int(r.amount_minor or 0)
        for r in xtr_rows
        if r.earned_at and r.earned_at <= cutoff
    )
    held_stars = max(0, ledger_stars - available_stars)

    sub_stars = (
        db.query(func.coalesce(func.sum(Subscription.amount_stars), 0))
        .filter(Subscription.status.in_(["active", "expired"]))
        .scalar()
    )
    legacy = (
        db.query(func.coalesce(func.sum(SubscriptionPlan.price_stars), 0))
        .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.status.in_(["active", "expired"]),
            Subscription.amount_stars.is_(None),
        )
        .scalar()
    )
    subscription_stars_total = int(sub_stars or 0) + int(legacy or 0)

    rate = stars_usd_rate()
    telegram_live: dict[str, Any] = {}
    try:
        from app.services.telegram_stars_balance import telegram_stars_reconcile_snapshot

        telegram_live = telegram_stars_reconcile_snapshot()
    except Exception as e:
        telegram_live = {"error": str(e)[:240]}

    tg_amount = None
    bal = telegram_live.get("balance") if isinstance(telegram_live, dict) else None
    if isinstance(bal, dict) and bal.get("ok"):
        tg_amount = bal.get("amount_stars")

    delta = None
    if tg_amount is not None:
        delta = int(tg_amount) - int(ledger_stars)

    return {
        "hold_days": hold,
        "as_of": _iso(now),
        "ledger_stars_total": ledger_stars,
        "ledger_stars_available_estimate": available_stars,
        "ledger_stars_held_estimate": held_stars,
        "ledger_stars_usd_estimate": round(ledger_stars * rate, 2),
        "available_stars_usd_estimate": round(available_stars * rate, 2),
        "subscription_table_stars_total": subscription_stars_total,
        "telegram_bot_stars": tg_amount,
        "ledger_vs_telegram_delta": delta,
        "telegram_live": telegram_live,
        "reconcile_note": (
            "Fragment 'total balance' can exceed TBCC ledger (Fragment refunds, companion Stars, "
            "or subs not backfilled). 'Available to withdraw' uses Telegram's 21-day hold — "
            "TBCC estimate uses earned_at on income_entries when present. "
            "telegram_bot_stars comes from Bot API getMyStarBalance when the payment token is set."
        ),
        "fragment_hints": {
            "compare_to": "Telegram → Bot Settings → Stars / Fragment dashboard",
            "typical_gap": "6770 Fragment total vs ~4270–5920 in TBCC = missing backfill or non-sub Stars",
            "kyc": (
                "US driver's license is a government-issued ID for Sumsub/Fragment — use it. "
                "Also need selfie + TON wallet + 2FA. Passport only if Sumsub rejects the DL."
            ),
        },
    }


def external_cashflow_summary(db: Session, *, days: int | None = 30) -> dict[str, Any]:
    """External platforms: earned, payouts, net, sync status."""
    q = db.query(IncomeEntry).filter(
        IncomeEntry.source.in_(
            ("linkvertise", "admaven", "workink", "bmc", "affiliate", "digital_product", "other")
        )
    )
    if days:
        since = _utcnow() - timedelta(days=int(days))
        q = q.filter(IncomeEntry.earned_at >= since)
    rows = q.order_by(IncomeEntry.id.desc()).all()

    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        src = row.source
        bucket = by_source.setdefault(
            src,
            {"source": src, "earned_usd": 0.0, "payouts_usd": 0.0, "entries": 0},
        )
        usd = int(row.amount_usd_cents or 0) / 100.0
        if (row.sync_kind or "") == "payout" or usd < 0:
            bucket["payouts_usd"] += abs(usd)
        else:
            bucket["earned_usd"] += usd
        bucket["entries"] += 1

    for bucket in by_source.values():
        bucket["earned_usd"] = round(bucket["earned_usd"], 2)
        bucket["payouts_usd"] = round(bucket["payouts_usd"], 2)
        bucket["net_usd"] = round(bucket["earned_usd"] - bucket["payouts_usd"], 2)

    recent_payouts = list_income_entries(db, limit=10, offset=0)
    payouts = [
        e
        for e in recent_payouts.get("items") or []
        if e.get("sync_kind") == "payout" or float(e.get("amount_usd") or 0) < 0
    ]

    lv = by_source.get(SOURCE_LINKVERTISE) or {
        "source": SOURCE_LINKVERTISE,
        "earned_usd": 0.0,
        "payouts_usd": 0.0,
        "net_usd": 0.0,
        "entries": 0,
    }

    return {
        "range_days": days,
        "by_source": sorted(by_source.values(), key=lambda x: -x["earned_usd"]),
        "linkvertise": {
            **lv,
            "accounting_note": (
                "Linkvertise earnings are NOT auto-known until income sync or manual entry. "
                "Record withdrawals with scripts/record_income_payout.py so ops picture stays honest."
            ),
        },
        "recent_payouts": payouts[:8],
        "income_poll": get_income_poll_status(),
    }


def _post_failure_themes(db: Session, *, days: int = 7, sample: int = 500) -> dict[str, Any]:
    since = _utcnow() - timedelta(days=days)
    total = db.query(PostOutboundEvent).filter(PostOutboundEvent.created_at >= since).count()
    failed = (
        db.query(PostOutboundEvent)
        .filter(PostOutboundEvent.created_at >= since, PostOutboundEvent.ok.is_(False))
        .count()
    )
    err_counts: Counter[str] = Counter()
    for (msg,) in (
        db.query(PostOutboundEvent.error_message)
        .filter(
            PostOutboundEvent.created_at >= since,
            PostOutboundEvent.ok.is_(False),
            PostOutboundEvent.error_message.isnot(None),
        )
        .limit(sample)
        .all()
    ):
        err_counts[(msg or "")[:120]] += 1
    return {
        "range_days": days,
        "outbound_total": total,
        "outbound_failed": failed,
        "failure_pct": round(100.0 * failed / total, 1) if total else 0.0,
        "top_themes": err_counts.most_common(6),
    }


def _import_failure_themes(db: Session, *, days: int = 7, sample: int = 500) -> dict[str, Any]:
    since = _utcnow() - timedelta(days=days)
    by_status = {
        str(s): int(c)
        for s, c in db.query(ImportJob.status, func.count(ImportJob.id))
        .filter(ImportJob.created_at >= since)
        .group_by(ImportJob.status)
        .all()
    }
    imp_counts: Counter[str] = Counter()
    for (msg,) in (
        db.query(ImportJob.error_message)
        .filter(
            ImportJob.status.in_(("failed", "error")),
            ImportJob.updated_at >= since,
            ImportJob.error_message.isnot(None),
        )
        .limit(sample)
        .all()
    ):
        imp_counts[(msg or "")[:120]] += 1
    done = int(by_status.get("done", 0))
    failed = sum(int(by_status.get(k, 0)) for k in ("failed", "error"))
    total = done + failed + sum(v for k, v in by_status.items() if k not in ("done", "failed", "error"))
    return {
        "range_days": days,
        "by_status": by_status,
        "failure_pct": round(100.0 * failed / total, 1) if total else 0.0,
        "top_themes": imp_counts.most_common(6),
    }


def _goblin_summary(db: Session, *, days: int = 14) -> dict[str, Any]:
    since = _utcnow() - timedelta(days=days)
    settings = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
    drops = db.query(GoblinDrop).filter(GoblinDrop.created_at >= since).count()
    claims = db.query(GoblinClaim).filter(GoblinClaim.claimed_at >= since).count()
    last_relay = (
        db.query(ListeningRelayPostLog)
        .order_by(ListeningRelayPostLog.id.desc())
        .first()
    )
    return {
        "goblin_mode_enabled": bool(getattr(settings, "goblin_mode_enabled", False)) if settings else False,
        "last_spawn_at": _iso(getattr(settings, "goblin_last_spawn_at", None)) if settings else None,
        "lastfm_username": getattr(settings, "lastfm_username", None) if settings else None,
        "last_relay_post_at": _iso(last_relay.created_at) if last_relay else None,
        "drops_in_range": drops,
        "claims_in_range": claims,
        "note": "Goblin spawns on new Last.fm scrobbles only; affiliate_served in Traffic Pulse ≠ spawn.",
    }


def derive_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Plain-language blockers ranked by financial impact."""
    blockers: list[dict[str, Any]] = []

    income = report.get("income") or {}
    latest = income.get("latest_earned_at")
    if latest:
        try:
            earned = datetime.fromisoformat(latest.replace("Z", ""))
            if (_utcnow() - earned).days >= 7:
                blockers.append(
                    {
                        "id": "revenue_stall",
                        "severity": "high",
                        "what": f"No new ledger income since {latest[:10]}",
                        "why": "Ops cost continues without fresh Stars/VIP conversion.",
                        "evidence": f"latest_earned_at={latest}",
                    }
                )
        except ValueError:
            pass

    companion = report.get("companion") or {}
    if int(companion.get("photos_sold") or 0) == 0:
        blockers.append(
            {
                "id": "companion_zero",
                "severity": "high",
                "what": "Companion bot sold 0 paid photos (30d)",
                "why": "Undress trial may burn COGS with no upsell.",
                "evidence": "photos_sold=0",
            }
        )

    attr = (report.get("bot_funnel") or {}).get("attribution") or {}
    if float(attr.get("attributed_revenue_pct") or 0) <= 0 and float(attr.get("total_usd") or 0) > 0:
        blockers.append(
            {
                "id": "attribution_blind",
                "severity": "medium",
                "what": "0% revenue attributed to source_ref",
                "why": "Cannot scale Jul-burst channels or kill dead gates.",
                "evidence": f"unattributed_usd={attr.get('unattributed_usd')}",
            }
        )

    posts = report.get("posts") or {}
    if float(posts.get("failure_pct") or 0) >= 20:
        blockers.append(
            {
                "id": "post_failures",
                "severity": "high",
                "what": f"~{posts.get('failure_pct')}% channel posts failed (7d)",
                "why": "FOMO and checkout CTAs starve when schedulers fail.",
                "evidence": f"{posts.get('outbound_failed')}/{posts.get('outbound_total')} failed; themes={posts.get('top_themes', [])[:2]}",
            }
        )

    imports = report.get("imports") or {}
    if float(imports.get("failure_pct") or 0) >= 25:
        blockers.append(
            {
                "id": "import_failures",
                "severity": "medium",
                "what": f"~{imports.get('failure_pct')}% pool imports failed (7d)",
                "why": "Loot lanes cannot refill reliably.",
                "evidence": f"by_status={imports.get('by_status')}; top={imports.get('top_themes', [])[:1]}",
            }
        )

    ext = report.get("external_cashflow") or {}
    lv = ext.get("linkvertise") or {}
    if (
        float(lv.get("earned_usd") or 0) == 0
        and float(lv.get("payouts_usd") or 0) == 0
    ):
        blockers.append(
            {
                "id": "external_untracked",
                "severity": "medium",
                "what": "No Linkvertise earnings or payouts in ledger",
                "why": "Ops picture under-reports real cash (withdrawals invisible).",
                "evidence": "record_income_payout.py + optional manual earned entry",
            }
        )

    gf = report.get("gate_funnel") or {}
    totals = gf.get("totals") or {}
    clicks = int(totals.get("clicks") or 0)
    touches = int(totals.get("touches") or 0)
    if clicks > 0 and touches == 0:
        blockers.append(
            {
                "id": "gate_no_touches",
                "severity": "medium",
                "what": "Beacon clicks with zero funnel touches",
                "why": "Paid traffic may hit dead destinations or click-only gates.",
                "evidence": f"clicks={clicks} touches={touches}",
            }
        )

    return blockers


def build_ops_picture_report(
    db: Session,
    *,
    days: int = 30,
    post_import_days: int = 7,
    backfill_income: bool = False,
) -> dict[str, Any]:
    """Single JSON blob as-of query time (UTC)."""
    generated = datetime.now(timezone.utc)

    def _gate_compact() -> dict[str, Any]:
        gf = gate_funnel_report(db, days=days)
        rows = gf.get("gate_funnel") or []
        ranked = sorted(rows, key=lambda r: int((r or {}).get("clicks") or 0), reverse=True)
        return {"top": ranked[:8], "totals": gf.get("totals") or {}, "unbeaconed_earning_refs": gf.get("unbeaconed_earning_refs")}

    sections: dict[str, Any] = {
        "generated_at": generated.isoformat(),
        "window_days": days,
        "post_import_window_days": post_import_days,
    }

    loaders: list[tuple[str, Callable[[], Any]]] = [
        ("income", lambda: income_summary(db, days=days, backfill=backfill_income)),
        ("income_all_time", lambda: income_summary(db, days=None, backfill=False)),
        ("stars_cashflow", lambda: stars_cashflow_summary(db)),
        ("external_cashflow", lambda: external_cashflow_summary(db, days=None)),
        ("gate_funnel", _gate_compact),
        ("companion", lambda: companion_margin_summary(db, days=days)),
        ("bot_funnel", lambda: bot_funnel_summary(db, days=days)),
        ("scheduling", lambda: {"stall": schedulers_stall_summary(), "fast": scheduling_fast_snapshot()}),
        ("imports", lambda: _import_failure_themes(db, days=post_import_days)),
        ("posts", lambda: _post_failure_themes(db, days=post_import_days)),
        ("goblin", lambda: _goblin_summary(db)),
        (
            "pools",
            lambda: {
                "approved_total": db.query(func.count(Media.id)).filter(Media.status == "approved").scalar(),
            },
        ),
    ]

    for name, fn in loaders:
        try:
            sections[name] = fn()
        except Exception as e:
            sections[name] = {"error": str(e)[:400]}

    sections["blockers"] = derive_blockers(sections)
    return sections
