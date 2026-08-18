"""Basic analytics for subscriptions, revenue, and outbound post metrics."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.channel import Channel
from app.models.post_outbound_event import PostOutboundEvent
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan

router = APIRouter()


class ManualIncomeBody(BaseModel):
    source: str = Field(..., max_length=32)
    amount_usd: float = Field(..., gt=0)
    source_label: str | None = Field(default=None, max_length=256)
    period_key: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=512)
    promo_affiliate_link_id: int | None = None


class IncomeSyncBody(BaseModel):
    sources: list[str] | None = None
    headed: bool = False


@router.get("/subscriptions")
def subscription_analytics(db: Session = Depends(get_db)):
    """Return subscription counts and revenue (Stars)."""
    total = db.query(Subscription).count()
    active = db.query(Subscription).filter(Subscription.status == "active").count()
    expired = db.query(Subscription).filter(Subscription.status == "expired").count()
    cancelled = db.query(Subscription).filter(Subscription.status == "cancelled").count()

    # Revenue: sum of amount_stars, fallback to plan.price_stars for legacy rows
    revenue_result = (
        db.query(func.coalesce(func.sum(Subscription.amount_stars), 0))
        .filter(Subscription.status.in_(["active", "expired"]))
        .scalar()
    )
    revenue_stars = int(revenue_result or 0)

    # For rows without amount_stars, add plan price (legacy data)
    legacy_subs = (
        db.query(SubscriptionPlan.price_stars)
        .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.status.in_(["active", "expired"]),
            Subscription.amount_stars.is_(None),
        )
        .all()
    )
    legacy_revenue = sum((p[0] or 0) for p in legacy_subs)
    revenue_stars += legacy_revenue

    return {
        "total_subscriptions": total,
        "active": active,
        "expired": expired,
        "cancelled": cancelled,
        "revenue_stars": revenue_stars,
    }


@router.get("/income/summary")
def income_summary_route(
    db: Session = Depends(get_db),
    days: int | None = Query(None, ge=1, le=3660),
    backfill: bool = Query(True),
):
    """Unified internal income rollup (Stars subs, crypto/manual subs, companion Stars)."""
    from app.services.income_ledger import income_summary

    return income_summary(db, days=days, backfill=backfill)


@router.post("/income/backfill")
def income_backfill_route(db: Session = Depends(get_db)):
    """Idempotently seed ledger from existing subscriptions."""
    from app.services.income_ledger import backfill_subscription_income

    return backfill_subscription_income(db)


@router.get("/income/sources")
def income_sources_route():
    from app.services.income_ledger import income_source_catalog

    return income_source_catalog()


@router.get("/income/entries")
def income_entries_route(
    db: Session = Depends(get_db),
    days: int | None = Query(None, ge=1, le=3660),
    source: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    from app.services.income_ledger import list_income_entries

    return list_income_entries(db, days=days, source=source, limit=limit, offset=offset)


@router.post("/income/manual")
def income_manual_route(body: ManualIncomeBody, db: Session = Depends(get_db)):
    from app.services.income_ledger import record_manual_income

    try:
        return record_manual_income(
            db,
            source=body.source,
            amount_usd=body.amount_usd,
            source_label=body.source_label,
            period_key=body.period_key,
            notes=body.notes,
            promo_affiliate_link_id=body.promo_affiliate_link_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/income/sync")
def income_sync_route(body: IncomeSyncBody | None = None, db: Session = Depends(get_db)):
    from app.services.income_sync import sync_external_income

    payload = body or IncomeSyncBody()
    return sync_external_income(db, sources=payload.sources, headed=payload.headed)


@router.get("/income/affiliates")
def income_affiliates_route(db: Session = Depends(get_db)):
    from app.services.income_sync import affiliate_registry_status

    return affiliate_registry_status(db)


@router.get("/income/poll-status")
def income_poll_status_route():
    from app.services.income_sync import get_income_poll_status

    return get_income_poll_status()


@router.get("/sponsor-pulse")
def sponsor_pulse_route(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Pack A/B/C click + attributed-$ pulse (wraps affiliate_sponsor_report)."""
    from app.services.affiliate_sponsor_pulse import build_sponsor_pulse

    return build_sponsor_pulse(db, days=days)


@router.post("/income/poll")
def income_poll_trigger_route(db: Session = Depends(get_db)):
    """On-demand light poll (same as Celery Beat task)."""
    from app.services.income_sync import run_income_poll

    return run_income_poll(db, light=True)


def _day_key(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.date().isoformat()


@router.get("/post-events")
def list_post_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Recent outbound post log (scheduled sends + pool album posts)."""
    q = (
        db.query(PostOutboundEvent)
        .order_by(PostOutboundEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = q.all()
    ch_ids = {r.channel_id for r in rows if r.channel_id}
    names: dict[int, str] = {}
    if ch_ids:
        for c in db.query(Channel).filter(Channel.id.in_(ch_ids)).all():
            names[c.id] = c.name or c.identifier or str(c.id)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "event_type": r.event_type,
                "channel_id": r.channel_id,
                "channel_name": names.get(r.channel_id) if r.channel_id else None,
                "scheduled_post_id": r.scheduled_post_id,
                "pool_id": r.pool_id,
                "ok": r.ok,
                "error_message": r.error_message,
            }
        )
    return {"items": out, "limit": limit, "offset": offset}


@router.get("/post-events/summary")
def post_events_summary(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Aggregates for charts: counts by day and channel over the last `days` days."""
    start = datetime.utcnow() - timedelta(days=days)
    rows = db.query(PostOutboundEvent).filter(PostOutboundEvent.created_at >= start).all()

    totals: dict[str, int] = defaultdict(int)
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_channel: dict[int, int] = defaultdict(int)

    for r in rows:
        totals[r.event_type] += 1
        totals["_all"] += 1
        if r.ok:
            totals["_ok"] += 1
        else:
            totals["_failed"] += 1
        dk = _day_key(r.created_at)
        if dk:
            by_day[dk][r.event_type] += 1
            by_day[dk]["_count"] += 1
        if r.channel_id:
            by_channel[r.channel_id] += 1

    day_list = sorted(by_day.keys())
    by_day_out = []
    for d in day_list:
        m = by_day[d]
        by_day_out.append(
            {
                "date": d,
                "scheduled_post_sent": m.get("scheduled_post_sent", 0),
                "pool_album_posted": m.get("pool_album_posted", 0),
                "count": m.get("_count", 0),
            }
        )

    ch_rows = []
    if by_channel:
        ch_ids = list(by_channel.keys())
        ch_map = {c.id: c for c in db.query(Channel).filter(Channel.id.in_(ch_ids)).all()}
        for cid, cnt in sorted(by_channel.items(), key=lambda x: -x[1]):
            ch = ch_map.get(cid)
            ch_rows.append(
                {
                    "channel_id": cid,
                    "channel_name": (ch.name or ch.identifier) if ch else str(cid),
                    "count": cnt,
                }
            )

    return {
        "range_days": days,
        "totals": {
            "scheduled_post_sent": totals.get("scheduled_post_sent", 0),
            "pool_album_posted": totals.get("pool_album_posted", 0),
            "all": totals.get("_all", 0),
            "ok": totals.get("_ok", 0),
            "failed": totals.get("_failed", 0),
        },
        "by_day": by_day_out,
        "by_channel": ch_rows,
    }


@router.get("/telegram-channel-stats")
def telegram_channel_stats(
    channel: str = Query(..., description="Telegram @username, t.me link, or numeric id"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Message views/forwards from Telegram via Telethon (not stored in TBCC DB).
    Requires API_ID, API_HASH, and an authorized TBCC_POSTER_TELEGRAM_SESSION.
    """
    from app.services.telegram_channel_stats import (
        fetch_channel_post_stats_sync,
        telethon_stats_configured,
    )

    if not telethon_stats_configured():
        raise HTTPException(
            status_code=503,
            detail="Set API_ID and API_HASH; authorize TBCC_POSTER_TELEGRAM_SESSION",
        )
    return fetch_channel_post_stats_sync(channel, limit=limit)


@router.get("/deliveries")
def list_deliveries(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    scheduled_post_id: int | None = Query(None),
    channel_id: int | None = Query(None),
):
    """Post delivery ledger with Telegram view snapshots (when refreshed)."""
    from app.services.content_performance import list_delivery_metrics

    return list_delivery_metrics(
        db,
        days=days,
        limit=limit,
        offset=offset,
        scheduled_post_id=scheduled_post_id,
        channel_id=channel_id,
    )


@router.post("/deliveries/refresh-views")
def refresh_delivery_views(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=500),
):
    """Poll Telethon for message view counts on recent deliveries."""
    from app.services.content_performance import refresh_delivery_views_sync
    from app.services.telegram_channel_stats import telethon_stats_configured

    if not telethon_stats_configured():
        raise HTTPException(
            status_code=503,
            detail="Set API_ID and API_HASH; authorize TBCC_POSTER_TELEGRAM_SESSION",
        )
    return refresh_delivery_views_sync(db, limit=limit)


@router.get("/deliveries/views-by-hour")
def delivery_views_by_hour(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Average views by local hour (TBCC_ANALYTICS_TZ) + community peak-time reference bands."""
    from app.services.content_performance import aggregate_views_by_hour

    return aggregate_views_by_hour(db, days=days)


@router.get("/deliveries/caption-slots")
def delivery_views_by_caption_slot(
    db: Session = Depends(get_db),
    scheduled_post_id: int = Query(..., ge=1),
    days: int = Query(90, ge=1, le=366),
):
    """Per-caption-slot view aggregates for one scheduler job."""
    from app.services.content_performance import aggregate_views_by_caption_slot

    result = aggregate_views_by_caption_slot(db, scheduled_post_id=scheduled_post_id, days=days)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=str(result["error"]))
    return result


@router.get("/growth-attribution/summary")
def growth_attribution_summary(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Loot/sub/referral conversions with time-of-day breakdown."""
    from app.services.growth_attribution import attribution_summary

    return attribution_summary(db, days=days)


@router.get("/companion-margin")
def companion_margin(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Companion photo unit economics — reports unknown cost basis rather than guessing."""
    from app.services.companion_cogs import companion_margin_summary

    return companion_margin_summary(db, days=days)


@router.get("/gate-funnel")
def gate_funnel(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Beacon click → funnel touch → revenue per source_ref (crawler hits excluded)."""
    from app.services.gate_funnel import gate_funnel_report

    return gate_funnel_report(db, days=days)


@router.get("/ops-picture")
def ops_picture(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
    post_import_days: int = Query(7, ge=1, le=90),
    backfill: bool = Query(False),
):
    """Point-in-time ops + money snapshot for /ops-picture (as-of request time)."""
    from app.services.ops_picture_report import build_ops_picture_report

    return build_ops_picture_report(
        db,
        days=days,
        post_import_days=post_import_days,
        backfill_income=backfill,
    )


@router.get("/direction")
def analytics_direction(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
    format: str = Query("json", pattern="^(json|markdown)$"),
    use_llm: bool = Query(False),
):
    """On-demand analytics direction — deterministic Top 5 ranked by $ impact."""
    from app.services.analytics_direction import build_analytics_direction_report

    report = build_analytics_direction_report(db, days=days, use_llm=use_llm)
    if format == "markdown":
        return Response(content=report.get("markdown") or "", media_type="text/markdown; charset=utf-8")
    return report


@router.get("/bots/funnel")
def bots_funnel_summary_route(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
):
    """Loot rolls, attribution events, and monetization deep links for dashboard Bots tab."""
    from app.services.bot_funnel_analytics import bot_funnel_summary

    return bot_funnel_summary(db, days=days)


@router.get("/growth-attribution/events")
def growth_attribution_events(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=366),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None),
):
    from app.services.growth_attribution import list_attribution_events

    return list_attribution_events(
        db,
        days=days,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )


@router.get("/signals/status")
def growth_signals_status_route():
    """Flywheel / dashboard: growth signal engine config + last tick."""
    from app.services.content_signals import growth_signals_status

    return growth_signals_status()


@router.get("/signals/eligibility")
def growth_signals_eligibility_route(db: Session = Depends(get_db)):
    """Whether a growth tick / view refresh is worth running (no side effects)."""
    from app.services.content_signals import growth_signals_eligibility

    return growth_signals_eligibility(db)


@router.get("/signals")
def growth_signals_compute(
    db: Session = Depends(get_db),
    days: int = Query(None, ge=3, le=90),
):
    """Strongest content/growth signals (read-only, no view refresh)."""
    from app.services.content_signals import compute_strong_signals

    return compute_strong_signals(db, days=days) if days else compute_strong_signals(db)


@router.post("/signals/tick")
def growth_signals_tick(
    db: Session = Depends(get_db),
    refresh_views: bool = Query(True),
    push_inbox: bool = Query(True),
):
    """
    Flywheel growth tick: refresh Telethon views → rank signals → inbox digest on change.
    Analytics lane only (no instant DM).
    """
    from app.services.content_signals import tick_growth_signals

    return tick_growth_signals(db, refresh_views=refresh_views, push_inbox_on_change=push_inbox)


@router.get("/signals/markdown")
def growth_signals_markdown(
    db: Session = Depends(get_db),
    days: int = Query(None, ge=3, le=90),
):
    from app.services.content_signals import compute_strong_signals, format_signals_markdown

    report = compute_strong_signals(db, days=days) if days else compute_strong_signals(db)
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(format_signals_markdown(report), media_type="text/markdown; charset=utf-8")


@router.get("/signals/proposals")
def growth_signal_proposals_route(
    db: Session = Depends(get_db),
    days: int = Query(None, ge=3, le=90),
):
    """Pending growth reaction proposals (observe-only drafts, operator reviews).

    No auto-execution: each proposal carries suggested MCP/API follow-up params
    for a human (or approved OpenClaw turn) to act on.
    """
    from app.services.growth_reaction import list_proposals

    return list_proposals(db, days=days)


@router.post("/signals/proposals/{proposal_id}/dismiss")
def dismiss_growth_signal_proposal_route(proposal_id: str):
    """Dismiss a proposal so it stops surfacing (survives signal recompute)."""
    from app.services.growth_reaction import dismiss_proposal

    result = dismiss_proposal(proposal_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "dismiss failed")
    return result


@router.get("/export-flywheel/status")
def export_flywheel_status_route(db: Session = Depends(get_db)):
    from app.services.export_flywheel_service import flywheel_status, list_export_proposals

    status = flywheel_status(db)
    status["proposals_summary"] = {
        "proposal_count": list_export_proposals(db).get("proposal_count"),
        "mode": status.get("mode"),
    }
    return status


@router.get("/export-flywheel/proposals")
def export_flywheel_proposals_route(db: Session = Depends(get_db)):
    from app.services.export_flywheel_service import list_export_proposals

    return list_export_proposals(db)


@router.post("/export-flywheel/proposals/{proposal_id}/dismiss")
def dismiss_export_flywheel_proposal_route(proposal_id: str):
    from app.services.export_flywheel_service import dismiss_export_proposal

    result = dismiss_export_proposal(proposal_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "dismiss failed")
    return result


@router.post("/export-flywheel/proposals/{proposal_id}/approve")
def approve_export_flywheel_proposal_route(proposal_id: str, db: Session = Depends(get_db)):
    from app.services.export_flywheel_executor import execute_proposal
    from app.services.export_flywheel_service import approve_export_proposal, build_export_proposals

    approved = approve_export_proposal(proposal_id)
    if not approved.get("ok"):
        raise HTTPException(status_code=400, detail=approved.get("error") or "approve failed")
    match = next((p for p in build_export_proposals(db) if p.get("id") == proposal_id), None)
    execution = execute_proposal(db, match) if match else None
    return {"ok": True, "approved": approved, "execution": execution}


@router.get("/industry-benchmarks")
def list_industry_benchmarks_route(
    db: Session = Depends(get_db),
    topic_type: str | None = Query(None),
):
    from app.services.industry_intelligence import list_industry_benchmarks

    return {"items": list_industry_benchmarks(db, topic_type=topic_type)}


@router.post("/industry-benchmarks/seed")
def seed_industry_benchmarks_route(db: Session = Depends(get_db)):
    from app.services.industry_intelligence import import_iui_corpus, seed_industry_benchmarks

    bench = seed_industry_benchmarks(db)
    rag = import_iui_corpus(db)
    return {"benchmarks": bench, "iui_corpus": rag}


@router.get("/ga4/hub-device-country")
def ga4_hub_device_country(days: int = Query(None, ge=1, le=30)):
    from app.services.ga4_hub_analytics import fetch_device_country_report

    return fetch_device_country_report(days=days)


@router.get("/category-demand")
def category_demand_crosswalk(
    db: Session = Depends(get_db),
    limit: int = Query(40, ge=5, le=100),
    gap_threshold: float = Query(15.0, ge=1.0, le=50.0),
):
    from app.services.category_demand_crosswalk import compute_category_demand_crosswalk

    return compute_category_demand_crosswalk(db, limit=limit, gap_threshold=gap_threshold)


@router.post("/openclaw/tick")
def openclaw_unified_tick_deprecated(
    db: Session = Depends(get_db),
    ops_limit: int = Query(1, ge=0, le=5),
    growth: bool = Query(True),
):
    """Deprecated alias — internal TBCC flywheel tick, not the OpenClaw gateway. Use POST /analytics/tbcc-flywheel/tick."""
    return tbcc_flywheel_unified_tick(db=db, ops_limit=ops_limit, growth=growth)


@router.post("/tbcc-flywheel/tick")
def tbcc_flywheel_unified_tick(
    db: Session = Depends(get_db),
    ops_limit: int = Query(1, ge=0, le=5),
    growth: bool = Query(True),
):
    """
    TBCC internal flywheel tick: ops routing + growth signals.
    External OpenClaw (github.com/openclaw/openclaw) should use TBCC MCP instead.
    """
    from app.services.content_signals import flywheel_growth_tick_enabled, tick_growth_signals
    from app.services.ops_flywheel import tick_flywheel

    out: dict[str, Any] = {"ok": True, "ops": None, "growth": None}
    if ops_limit > 0:
        out["ops"] = tick_flywheel(limit=ops_limit)
    if growth and flywheel_growth_tick_enabled():
        out["growth"] = tick_growth_signals(db)
    elif growth:
        out["growth"] = {
            "ok": True,
            "skipped": True,
            "reason": "TBCC_FLYWHEEL_GROWTH_TICK=0",
        }
    try:
        from app.services.export_flywheel_service import flywheel_enabled, tick_observe

        if flywheel_enabled():
            out["export_flywheel"] = tick_observe(db, push_inbox=False)
    except Exception as e:
        out["export_flywheel"] = {"ok": False, "error": str(e)[:200]}
    return out


class EromeBrowseIntelIngestBody(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)


@router.post("/erome-browse-intel")
def ingest_erome_browse_intel_route(body: EromeBrowseIntelIngestBody = Body(...)):
    """Ingest Tampermonkey browse-intel JSONL rows (append + dedupe by album/day)."""
    from app.services.erome_browse_intel import ingest_rows

    if not body.rows:
        raise HTTPException(status_code=400, detail="rows required")
    return ingest_rows(body.rows)


@router.post("/erome-browse-intel/sync-file")
def sync_erome_browse_intel_file_route():
    """Ingest ``browse-intel-drop.jsonl`` from erome-analytics dir if present."""
    from app.services.erome_browse_intel import sync_from_drop_file

    return sync_from_drop_file()


@router.get("/erome-browse-intel/summary")
def erome_browse_intel_summary_route(days: int = Query(None, ge=1, le=180)):
    from app.services.erome_browse_intel import intel_summary

    return intel_summary(days=days)


@router.post("/market-intel/probe")
def market_intel_probe_route(limit_per_sub: int = Query(25, ge=1, le=100)):
    """Run Reddit JSON market probe (public subs, no OAuth)."""
    from app.services.market_intel_probe import run_market_probes

    return run_market_probes(limit_per_sub=limit_per_sub)


@router.post("/market-intel/probe/scrolller")
def market_intel_scrolller_probe_route(limit_per_sub: int = Query(20, ge=1, le=50)):
    """Run Scrolller agent-route probe (metadata + watermarked embed refs only)."""
    from app.services.market_intel_scrolller_probe import run_scrolller_probes

    return run_scrolller_probes(limit_per_sub=limit_per_sub)


@router.get("/market-intel/scrolller/registry-suggestions")
def scrolller_registry_suggestions_route(
    db: Session = Depends(get_db),
    apply: bool = Query(False, description="Insert suggestions when TBCC_SCROLLLER_REGISTRY_AUTO_APPLY=1"),
    max_new: int = Query(None, ge=1, le=25),
):
    """Rank Scrolller seed subs and suggest probation registry rows for unknown names."""
    from app.services.scrolller_reddit_registry import suggest_reddit_registry_from_scrolller

    return suggest_reddit_registry_from_scrolller(db, apply=apply, max_new=max_new)


@router.post("/market-intel")
def market_intel_ingest_route(body: EromeBrowseIntelIngestBody = Body(...)):
    """Ingest multi-platform market-intel rows (platform field per row)."""
    from app.services.erome_browse_intel import ingest_rows

    if not body.rows:
        raise HTTPException(status_code=400, detail="rows required")
    return ingest_rows(body.rows)


@router.get("/market-intel/upload-hints")
def market_intel_upload_hints_route(top_n: int = Query(8, ge=1, le=30)):
    from app.services.erome_upload_policy import intel_upload_hints

    return intel_upload_hints(top_n=top_n)


@router.get("/erome-upload/governance")
def erome_upload_governance_summary_route():
    """Pending private uploads awaiting human title/tag/public pass."""
    from app.services.erome_upload_governance import governance_summary

    return governance_summary()


class EromeGovernanceMarkBody(BaseModel):
    album_url: str = Field(..., min_length=8, max_length=400)
    status: str = Field(..., description="needs_review | approved_public | rejected | staged_private")
    notes: str | None = Field(None, max_length=500)
    title: str | None = Field(None, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=30)


@router.post("/erome-upload/governance/mark")
def erome_upload_governance_mark_route(body: EromeGovernanceMarkBody = Body(...)):
    from app.services.erome_upload_governance import mark_governance

    out = mark_governance(
        album_url=body.album_url,
        status=body.status,
        notes=body.notes,
        title=body.title,
        tags=body.tags or None,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "mark_failed")
    return out


@router.post("/erome-upload/intel-week/seed")
def erome_intel_week_seed_route(
    week: str | None = Query(None),
    title: str | None = Query(None),
):
    """Create intel-week staging folder + sidecar with suggested tags (private)."""
    from app.services.erome_upload_governance import intel_week_staging_dir, seed_intel_week_sidecar

    folder = intel_week_staging_dir(week=week)
    return seed_intel_week_sidecar(folder, title=title)


@router.get("/market-intel/cycle")
def market_intel_cycle_status_route():
    """Latest weekly cycle evaluation (current ISO week if present)."""
    from app.services.market_intel_cycle import (
        cycle_enabled,
        get_cycle_record_for_week,
        get_last_cycle_record,
        week_id,
    )

    rec = get_cycle_record_for_week() or get_last_cycle_record()
    return {
        "ok": True,
        "enabled": cycle_enabled(),
        "week_id": week_id(),
        "record": rec,
    }


@router.post("/market-intel/cycle/evaluate")
def market_intel_cycle_evaluate_route(force: bool = Query(False)):
    """Evaluate weekly intel cycle (append ledger when complete or forced)."""
    from app.services.market_intel_cycle import evaluate_weekly_cycle

    return evaluate_weekly_cycle(force=force)


@router.post("/market-intel/cycle/run")
def market_intel_cycle_run_route(
    db: Session = Depends(get_db),
    force: bool = Query(False),
):
    """Probe + evaluate weekly cycle + optional gated post actions."""
    from app.services.erome_browse_intel import sync_from_drop_file
    from app.services.market_intel_cycle import evaluate_weekly_cycle
    from app.services.market_intel_cycle_executor import execute_cycle_actions
    from app.services.market_intel_probe import run_market_probes
    from app.services.market_intel_scrolller_probe import run_scrolller_probes

    drop = sync_from_drop_file()
    probe = run_market_probes()
    scrolller = run_scrolller_probes()
    cycle = evaluate_weekly_cycle(force=force)
    actions = execute_cycle_actions(db, cycle) if cycle.get("complete") else {"skipped": True}
    return {"ok": True, "drop_sync": drop, "probe": probe, "scrolller_probe": scrolller, "cycle": cycle, "actions": actions}
