"""Unified income ledger — internal + external monetization sources."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.external_payment_order import ExternalPaymentOrder
from app.models.income_entry import IncomeEntry
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.services.nowpayments_client import stars_to_usd

logger = logging.getLogger(__name__)

# Internal (TBCC-tracked payments)
SOURCE_SUBSCRIPTION_STARS = "subscription_stars"
SOURCE_SUBSCRIPTION_CRYPTO = "subscription_crypto"
SOURCE_SUBSCRIPTION_MANUAL = "subscription_manual"
SOURCE_COMPANION_STARS = "companion_stars"

# External (gates, affiliates, donations, products)
SOURCE_LINKVERTISE = "linkvertise"
SOURCE_ADMAVEN = "admaven"
SOURCE_WORKINK = "workink"
SOURCE_LOOTLABS = "lootlabs"
SOURCE_BMC = "bmc"
SOURCE_AFFILIATE = "affiliate"
SOURCE_DIGITAL_PRODUCT = "digital_product"
SOURCE_OTHER = "other"

SOURCE_LABELS: dict[str, str] = {
    SOURCE_SUBSCRIPTION_STARS: "Subscriptions (Telegram Stars)",
    SOURCE_SUBSCRIPTION_CRYPTO: "Subscriptions (crypto / NOWPayments)",
    SOURCE_SUBSCRIPTION_MANUAL: "Subscriptions (manual / webhook)",
    SOURCE_COMPANION_STARS: "Companion bot (Telegram Stars)",
    SOURCE_LINKVERTISE: "Linkvertise",
    SOURCE_ADMAVEN: "AdMaven",
    SOURCE_WORKINK: "Work.ink",
    SOURCE_LOOTLABS: "LootLabs",
    SOURCE_BMC: "Buy Me a Coffee",
    SOURCE_AFFILIATE: "Affiliate program",
    SOURCE_DIGITAL_PRODUCT: "Digital product",
    SOURCE_OTHER: "Other",
}

INTERNAL_SOURCES = (
    SOURCE_SUBSCRIPTION_STARS,
    SOURCE_SUBSCRIPTION_CRYPTO,
    SOURCE_SUBSCRIPTION_MANUAL,
    SOURCE_COMPANION_STARS,
)

EXTERNAL_SOURCES = (
    SOURCE_LINKVERTISE,
    SOURCE_ADMAVEN,
    SOURCE_WORKINK,
    SOURCE_LOOTLABS,
    SOURCE_BMC,
    SOURCE_AFFILIATE,
    SOURCE_DIGITAL_PRODUCT,
    SOURCE_OTHER,
)

ALL_SOURCES = INTERNAL_SOURCES + EXTERNAL_SOURCES

MANUAL_SOURCES = EXTERNAL_SOURCES

SYNC_KINDS = ("webhook", "computed", "manual", "api_poll", "playwright_scrape", "payout")

def stars_usd_rate() -> float:
    import os

    try:
        return float((os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012").strip())
    except ValueError:
        return 0.012


def _usd_cents_from_stars(stars: int) -> int:
    return max(0, round(stars_to_usd(int(stars or 0)) * 100))


def _usd_cents_from_usd(amount_usd: float) -> int:
    return max(0, round(float(amount_usd) * 100))


def _subscription_source(payment_method: str | None) -> str:
    pm = (payment_method or "stars").strip().lower()
    if pm == "stars":
        return SOURCE_SUBSCRIPTION_STARS
    if pm in ("crypto", "nowpayments"):
        return SOURCE_SUBSCRIPTION_CRYPTO
    return SOURCE_SUBSCRIPTION_MANUAL


def _subscription_idempotency_key(sub: Subscription, charge_id: str | None) -> str:
    cid = (charge_id or sub.telegram_payment_charge_id or "").strip()
    if cid:
        return f"subscription:{cid[:120]}"
    return f"subscription:id:{int(sub.id)}"


def _companion_idempotency_key(charge_id: str | None, *, user_id: int, stars: int) -> str:
    cid = (charge_id or "").strip()
    if cid:
        return f"companion_stars:{cid[:120]}"
    return f"companion_stars:user:{user_id}:{stars}:{datetime.utcnow().strftime('%Y%m%d')}"


def _subscription_earned_at(db: Session, sub: Subscription, plan: SubscriptionPlan | None) -> datetime | None:
    cid = (sub.telegram_payment_charge_id or "").strip()
    if cid and "EPO-" in cid:
        ref = cid[cid.index("EPO-") :].split("_")[0].split()[0]
        if ref.startswith("EPO-"):
            order = (
                db.query(ExternalPaymentOrder)
                .filter(ExternalPaymentOrder.reference_code == ref)
                .first()
            )
            if order and order.paid_at:
                return order.paid_at
    if sub.expires_at and plan and (plan.duration_days or 0) > 0:
        return sub.expires_at - timedelta(days=max(int(plan.duration_days), 1))
    return None


def _resolve_traffic_source_ref(
    db: Session,
    *,
    telegram_user_id: int | None,
    explicit: str | None,
) -> str | None:
    """Explicit ref wins; otherwise fall back to the buyer's funnel touch."""
    if explicit:
        return explicit.strip()[:64] or None
    if telegram_user_id is None:
        return None
    try:
        from app.services.traffic_attribution import resolve_attribution_for_user

        attr = resolve_attribution_for_user(db, int(telegram_user_id))
        ref = (attr.get("traffic_source_ref") or "").strip()
        return ref[:64] or None
    except Exception:
        logger.debug("income traffic_source_ref resolve failed", exc_info=True)
        return None


def record_income_entry(
    db: Session,
    *,
    idempotency_key: str,
    source: str,
    amount_minor: int,
    currency: str,
    amount_usd_cents: int,
    source_label: str | None = None,
    earned_at: datetime | None = None,
    sync_kind: str = "computed",
    external_ref: str | None = None,
    subscription_id: int | None = None,
    telegram_user_id: int | None = None,
    traffic_source_ref: str | None = None,
    raw: dict[str, Any] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    key = (idempotency_key or "").strip()[:128]
    if not key:
        return {"ok": False, "error": "missing_idempotency_key"}

    existing = db.query(IncomeEntry).filter(IncomeEntry.idempotency_key == key).first()
    if existing:
        return {"ok": True, "idempotent": True, "id": existing.id}

    source_ref = _resolve_traffic_source_ref(
        db,
        telegram_user_id=telegram_user_id,
        explicit=traffic_source_ref,
    )

    sk = (sync_kind or "computed")[:16]
    minor = int(amount_minor)
    usd_c = int(amount_usd_cents)
    if sk != "payout":
        minor = max(0, minor)
        usd_c = max(0, usd_c)

    row = IncomeEntry(
        idempotency_key=key,
        source=(source or "other")[:32],
        source_label=(source_label or SOURCE_LABELS.get(source, source))[:256],
        amount_minor=minor,
        currency=(currency or "USD")[:8],
        amount_usd_cents=usd_c,
        earned_at=earned_at,
        sync_kind=sk,
        external_ref=(external_ref[:128] if external_ref else None),
        subscription_id=subscription_id,
        telegram_user_id=int(telegram_user_id) if telegram_user_id is not None else None,
        traffic_source_ref=source_ref,
        raw_json=json.dumps(raw, ensure_ascii=False) if raw else None,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    try:
        if commit:
            db.commit()
        else:
            db.flush()
        return {"ok": True, "idempotent": False, "id": row.id}
    except IntegrityError:
        db.rollback()
        dup = db.query(IncomeEntry).filter(IncomeEntry.idempotency_key == key).first()
        if dup:
            return {"ok": True, "idempotent": True, "id": dup.id}
        raise


def record_subscription_income(
    db: Session,
    sub: Subscription,
    plan: SubscriptionPlan,
    *,
    payment_method: str | None = None,
    charge_id: str | None = None,
    amount_usd_override: float | None = None,
    external_ref: str | None = None,
    sync_kind: str = "webhook",
) -> dict[str, Any]:
    source = _subscription_source(payment_method or sub.payment_method)
    stars = int(sub.amount_stars if sub.amount_stars is not None else (plan.price_stars or 0))
    if amount_usd_override is not None and float(amount_usd_override) > 0:
        usd_cents = _usd_cents_from_usd(float(amount_usd_override))
        currency = "USD"
        amount_minor = usd_cents
    else:
        usd_cents = _usd_cents_from_stars(stars)
        currency = "XTR"
        amount_minor = stars

    label = (plan.name or sub.plan or "Subscription").strip()
    product_type = (plan.product_type or "").strip().lower()
    if product_type == "bundle":
        label = f"Bundle: {label}"

    return record_income_entry(
        db,
        idempotency_key=_subscription_idempotency_key(sub, charge_id),
        source=source,
        source_label=label,
        amount_minor=amount_minor,
        currency=currency,
        amount_usd_cents=usd_cents,
        earned_at=_subscription_earned_at(db, sub, plan),
        sync_kind=sync_kind,
        external_ref=external_ref,
        subscription_id=int(sub.id),
        telegram_user_id=int(sub.telegram_user_id) if sub.telegram_user_id else None,
        # Stamped at fulfillment; survives touch TTL expiry on later backfills.
        traffic_source_ref=getattr(sub, "traffic_source_ref", None),
        raw={
            "plan_id": int(plan.id),
            "payment_method": payment_method or sub.payment_method,
            "stars_equivalent": stars,
        },
    )


def record_companion_stars_income(
    db: Session,
    *,
    user_id: int,
    stars: int,
    charge_id: str | None = None,
) -> dict[str, Any]:
    stars = max(0, int(stars or 0))
    if stars <= 0:
        return {"ok": False, "error": "zero_stars"}
    return record_income_entry(
        db,
        idempotency_key=_companion_idempotency_key(charge_id, user_id=user_id, stars=stars),
        source=SOURCE_COMPANION_STARS,
        source_label=SOURCE_LABELS[SOURCE_COMPANION_STARS],
        amount_minor=stars,
        currency="XTR",
        amount_usd_cents=_usd_cents_from_stars(stars),
        earned_at=datetime.utcnow(),
        sync_kind="webhook",
        telegram_user_id=int(user_id),
        raw={"product": "companion_photo"},
    )


def backfill_subscription_income(db: Session) -> dict[str, Any]:
    """Seed ledger rows from existing subscriptions (idempotent)."""
    inserted = 0
    idempotent = 0
    skipped = 0

    rows = (
        db.query(Subscription, SubscriptionPlan)
        .outerjoin(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .filter(Subscription.status.in_(["active", "expired"]))
        .order_by(Subscription.id.asc())
        .all()
    )
    for sub, plan in rows:
        if not plan:
            skipped += 1
            continue
        result = record_subscription_income(
            db,
            sub,
            plan,
            payment_method=sub.payment_method,
            charge_id=sub.telegram_payment_charge_id,
            sync_kind="computed",
        )
        if result.get("idempotent"):
            idempotent += 1
        elif result.get("ok"):
            inserted += 1
        else:
            skipped += 1

    return {
        "ok": True,
        "inserted": inserted,
        "idempotent": idempotent,
        "skipped": skipped,
        "scanned": len(rows),
    }


def _normalize_source(source: str) -> str:
    s = (source or "").strip().lower()[:32]
    if s not in ALL_SOURCES:
        raise ValueError(f"unknown_source:{s}")
    return s


def _latest_cumulative_usd(db: Session, source: str) -> float:
    rows = (
        db.query(IncomeEntry)
        .filter(
            IncomeEntry.source == source,
            IncomeEntry.sync_kind.in_(("api_poll", "playwright_scrape")),
        )
        .order_by(IncomeEntry.id.desc())
        .limit(30)
        .all()
    )
    for row in rows:
        if not row.raw_json:
            continue
        try:
            raw = json.loads(row.raw_json)
            cum = raw.get("cumulative_usd")
            if cum is not None:
                return float(cum)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return 0.0


def record_manual_income(
    db: Session,
    *,
    source: str,
    amount_usd: float,
    source_label: str | None = None,
    earned_at: datetime | None = None,
    period_key: str | None = None,
    notes: str | None = None,
    promo_affiliate_link_id: int | None = None,
    traffic_source_ref: str | None = None,
) -> dict[str, Any]:
    src = _normalize_source(source)
    usd = max(0.0, float(amount_usd))
    if usd <= 0:
        return {"ok": False, "error": "amount_must_be_positive"}

    period = (period_key or datetime.utcnow().strftime("%Y-%m-%d")).strip()[:64]
    ext_ref = None
    if promo_affiliate_link_id is not None:
        ext_ref = f"affiliate:{int(promo_affiliate_link_id)}"
    elif period_key:
        ext_ref = f"{src}:{period[:96]}"

    idem = f"manual:{src}:{period}"[:128]
    usd_cents = _usd_cents_from_usd(usd)
    label = (source_label or SOURCE_LABELS.get(src, src))[:256]

    return record_income_entry(
        db,
        idempotency_key=idem,
        source=src,
        source_label=label,
        amount_minor=usd_cents,
        currency="USD",
        amount_usd_cents=usd_cents,
        earned_at=earned_at or datetime.utcnow(),
        sync_kind="manual",
        external_ref=ext_ref,
        traffic_source_ref=traffic_source_ref,
        raw={"notes": notes, "period_key": period, "promo_affiliate_link_id": promo_affiliate_link_id},
    )


def record_income_payout(
    db: Session,
    *,
    source: str,
    amount_usd: float,
    destination: str = "bank",
    notes: str | None = None,
    withdrawn_at: datetime | None = None,
) -> dict[str, Any]:
    """Record cash leaving an external platform (withdrawal). Stored as negative USD in the ledger."""
    src = _normalize_source(source)
    usd = max(0.0, float(amount_usd))
    if usd <= 0:
        return {"ok": False, "error": "amount_must_be_positive"}

    when = withdrawn_at or datetime.utcnow()
    stamp = when.strftime("%Y%m%d")
    idem = f"payout:{src}:{stamp}:{int(round(usd * 100))}"[:128]
    usd_cents = _usd_cents_from_usd(usd)
    label = f"{SOURCE_LABELS.get(src, src)} payout → {destination}"

    return record_income_entry(
        db,
        idempotency_key=idem,
        source=src,
        source_label=label[:256],
        amount_minor=-usd_cents,
        currency="USD",
        amount_usd_cents=-usd_cents,
        earned_at=when,
        sync_kind="payout",
        external_ref=f"payout:{destination}"[:128],
        raw={"destination": destination, "notes": notes, "gross_usd": usd},
    )


def record_cumulative_sync_delta(
    db: Session,
    source: str,
    cumulative_usd: float,
    *,
    source_label: str | None = None,
    sync_kind: str = "api_poll",
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    src = _normalize_source(source)
    cumulative = max(0.0, float(cumulative_usd))
    previous = _latest_cumulative_usd(db, src)
    delta = round(cumulative - previous, 2)
    payload = dict(raw or {})
    payload["cumulative_usd"] = cumulative
    payload["previous_cumulative_usd"] = previous

    if delta <= 0:
        return {
            "ok": True,
            "skipped": True,
            "delta_usd": 0.0,
            "cumulative_usd": cumulative,
            "previous_cumulative_usd": previous,
        }

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    usd_cents = _usd_cents_from_usd(delta)
    return record_income_entry(
        db,
        idempotency_key=f"sync:{src}:delta:{stamp}"[:128],
        source=src,
        source_label=(source_label or SOURCE_LABELS.get(src, src))[:256],
        amount_minor=usd_cents,
        currency="USD",
        amount_usd_cents=usd_cents,
        earned_at=datetime.utcnow(),
        sync_kind=(sync_kind or "api_poll")[:16],
        raw=payload,
    )


def list_income_entries(
    db: Session,
    *,
    days: int | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    q = db.query(IncomeEntry).order_by(IncomeEntry.id.desc())
    if source:
        q = q.filter(IncomeEntry.source == _normalize_source(source))
    if days is not None and days > 0:
        since = datetime.utcnow() - timedelta(days=int(days))
        q = q.filter(IncomeEntry.earned_at >= since)
    total = q.count()
    rows = q.offset(max(0, offset)).limit(max(1, min(500, limit))).all()
    items = [
        {
            "id": r.id,
            "source": r.source,
            "source_label": r.source_label,
            "amount_minor": r.amount_minor,
            "currency": r.currency,
            "amount_usd_cents": r.amount_usd_cents,
            "amount_usd": round(int(r.amount_usd_cents or 0) / 100.0, 2),
            "earned_at": r.earned_at.isoformat() + "Z" if r.earned_at else None,
            "sync_kind": r.sync_kind,
            "external_ref": r.external_ref,
            "traffic_source_ref": r.traffic_source_ref,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def income_source_catalog() -> dict[str, Any]:
    return {
        "internal": [{"source": s, "label": SOURCE_LABELS[s]} for s in INTERNAL_SOURCES],
        "external": [{"source": s, "label": SOURCE_LABELS[s]} for s in EXTERNAL_SOURCES],
        "manual_sources": [{"source": s, "label": SOURCE_LABELS[s]} for s in MANUAL_SOURCES],
    }


def _aggregate_rows(rows: list[IncomeEntry]) -> dict[str, Any]:
    total_usd_cents = 0
    gross_usd_cents = 0
    payout_usd_cents = 0
    total_stars = 0
    internal_usd_cents = 0
    external_usd_cents = 0
    by_source: dict[str, dict[str, Any]] = {}

    for row in rows:
        usd_c = int(row.amount_usd_cents or 0)
        is_payout = (row.sync_kind or "") == "payout" or usd_c < 0
        if is_payout:
            payout_usd_cents += abs(usd_c)
            continue
        total_usd_cents += usd_c
        gross_usd_cents += usd_c
        if row.source in INTERNAL_SOURCES:
            internal_usd_cents += usd_c
        else:
            external_usd_cents += usd_c
        if (row.currency or "").upper() == "XTR":
            total_stars += int(row.amount_minor or 0)
        bucket = by_source.setdefault(
            row.source,
            {
                "source": row.source,
                "label": row.source_label or SOURCE_LABELS.get(row.source, row.source),
                "usd_cents": 0,
                "stars": 0,
                "count": 0,
                "category": "internal" if row.source in INTERNAL_SOURCES else "external",
            },
        )
        bucket["usd_cents"] += usd_c
        bucket["count"] += 1
        if (row.currency or "").upper() == "XTR":
            bucket["stars"] += int(row.amount_minor or 0)

    by_source_list = sorted(by_source.values(), key=lambda x: -int(x["usd_cents"]))
    return {
        "total_usd_cents": total_usd_cents,
        "gross_usd_cents": gross_usd_cents,
        "payout_usd_cents": payout_usd_cents,
        "net_usd_cents": total_usd_cents,
        "total_stars": total_stars,
        "internal_usd_cents": internal_usd_cents,
        "external_usd_cents": external_usd_cents,
        "by_source": by_source_list,
        "entry_count": len(rows),
    }


def income_summary(db: Session, *, days: int | None = None, backfill: bool = True) -> dict[str, Any]:
    backfill_result: dict[str, Any] | None = None
    if backfill:
        try:
            backfill_result = backfill_subscription_income(db)
        except Exception as e:
            logger.warning("income backfill failed: %s", e)
            backfill_result = {"ok": False, "error": str(e)}

    q = db.query(IncomeEntry)
    if days is not None and days > 0:
        since = datetime.utcnow() - timedelta(days=int(days))
        q = q.filter(IncomeEntry.earned_at >= since)

    rows = q.all()
    agg = _aggregate_rows(rows)

    latest = db.query(func.max(IncomeEntry.earned_at), func.max(IncomeEntry.created_at)).first()
    latest_earned = latest[0].isoformat() + "Z" if latest and latest[0] else None
    latest_created = latest[1].isoformat() + "Z" if latest and latest[1] else None

    return {
        "ok": True,
        "scope": "full",
        "range_days": days,
        "totals": {
            "usd_cents": agg["total_usd_cents"],
            "usd": round(agg["total_usd_cents"] / 100.0, 2),
            "gross_usd": round(agg["gross_usd_cents"] / 100.0, 2),
            "payouts_usd": round(agg["payout_usd_cents"] / 100.0, 2),
            "stars": agg["total_stars"],
            "entry_count": agg["entry_count"],
            "internal_usd": round(agg["internal_usd_cents"] / 100.0, 2),
            "external_usd": round(agg["external_usd_cents"] / 100.0, 2),
        },
        "by_source": agg["by_source"],
        "stars_usd_rate": stars_usd_rate(),
        "latest_earned_at": latest_earned,
        "latest_entry_at": latest_created,
        "backfill": backfill_result,
        "sources": income_source_catalog(),
    }
