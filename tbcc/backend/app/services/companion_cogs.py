"""
Companion bot unit economics — is 25 stars a photo actually profitable?

Every delivered photo spends operator balance on the upstream undress API, and
that cost has never been recorded anywhere, so the companion has been sold at
an unknown margin. Cost inputs are env-driven and default to *unknown* rather
than to a flattering guess: with no cost basis set, this reports
cost_basis_known=False instead of implying 100% margin.

Free-trial photos are pure cost with zero revenue, but generations live in
Redis rather than a table, so trial burn is estimated from the configured
trial size, never measured. Treat it as a floor.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.services.companion_stars import stars_per_photo


def usd_per_star() -> float:
    try:
        return max(0.0, float((os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012").strip()))
    except ValueError:
        return 0.012


def undress_usd_per_credit() -> float:
    """0.0 means unset — read it off the undress plan invoice, do not guess."""
    try:
        return max(0.0, float((os.getenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT") or "0").strip()))
    except ValueError:
        return 0.0


def undress_credits_per_photo() -> float:
    """Credits burned per *delivered* photo, including typical retries."""
    try:
        return max(0.0, float((os.getenv("TBCC_COMPANION_UNDRESS_CREDITS_PER_PHOTO") or "1").strip()))
    except ValueError:
        return 1.0


def stars_platform_fee_pct() -> float:
    """
    Store cut on Stars purchases. Defaults to 0 because it depends on whether
    the buyer topped up on iOS, Android or the web; set it from payout reality.
    """
    try:
        return max(0.0, min(100.0, float((os.getenv("TBCC_STARS_PLATFORM_FEE_PCT") or "0").strip())))
    except ValueError:
        return 0.0


def cost_basis_known() -> bool:
    return undress_usd_per_credit() > 0


def companion_unit_economics() -> dict[str, Any]:
    stars = stars_per_photo()
    gross = round(stars * usd_per_star(), 4)
    fee_pct = stars_platform_fee_pct()
    net_revenue = round(gross * (1.0 - fee_pct / 100.0), 4)
    cogs = round(undress_credits_per_photo() * undress_usd_per_credit(), 4)
    known = cost_basis_known()
    contribution = round(net_revenue - cogs, 4)
    margin_pct = round(100.0 * contribution / net_revenue, 1) if net_revenue else None

    out: dict[str, Any] = {
        "stars_per_photo": stars,
        "usd_per_star": usd_per_star(),
        "gross_usd_per_photo": gross,
        "platform_fee_pct": fee_pct,
        "net_revenue_usd_per_photo": net_revenue,
        "undress_credits_per_photo": undress_credits_per_photo(),
        "undress_usd_per_credit": undress_usd_per_credit(),
        "cogs_usd_per_photo": cogs if known else None,
        "cost_basis_known": known,
        "contribution_usd_per_photo": contribution if known else None,
        "margin_pct": margin_pct if known else None,
        "below_cost": bool(known and contribution < 0),
    }
    if not known:
        out["action"] = (
            "Set TBCC_COMPANION_UNDRESS_USD_PER_CREDIT from the undress plan invoice "
            "(plan price / credits granted). Margin is unknown until then."
        )
    elif out["below_cost"]:
        out["action"] = (
            f"Every photo loses ${abs(contribution):.4f}. Raise TBCC_COMPANION_STARS_PER_PHOTO "
            f"to at least {breakeven_stars_per_photo()} or cut credits per photo."
        )
    return out


def breakeven_stars_per_photo() -> int:
    """Smallest star price that covers upstream cost after the platform fee."""
    cogs = undress_credits_per_photo() * undress_usd_per_credit()
    per_star = usd_per_star()
    if cogs <= 0 or per_star <= 0:
        return 0
    net_per_star = per_star * (1.0 - stars_platform_fee_pct() / 100.0)
    if net_per_star <= 0:
        return 0
    import math

    # Round before ceil: 0.20*3 lands on 0.6000000000000001 and would otherwise
    # bill an extra star.
    return int(math.ceil(round(cogs / net_per_star, 6)))


def estimated_trial_burn_usd(trial_photos_delivered: int) -> float:
    return round(
        max(0, int(trial_photos_delivered)) * undress_credits_per_photo() * undress_usd_per_credit(),
        2,
    )


def companion_margin_summary(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Paid companion photos over a window with estimated contribution."""
    from app.models.income_entry import IncomeEntry
    from app.services.income_ledger import SOURCE_COMPANION_STARS

    since = datetime.utcnow() - timedelta(days=max(1, min(366, days)))
    rows = (
        db.query(IncomeEntry)
        .filter(
            IncomeEntry.source == SOURCE_COMPANION_STARS,
            IncomeEntry.created_at >= since,
        )
        .all()
    )

    unit = companion_unit_economics()
    photos = len(rows)
    gross_usd = round(sum(int(r.amount_usd_cents or 0) for r in rows) / 100.0, 2)
    stars_total = sum(int(r.amount_minor or 0) for r in rows if (r.currency or "").upper() == "XTR")
    net_revenue = round(gross_usd * (1.0 - unit["platform_fee_pct"] / 100.0), 2)

    known = unit["cost_basis_known"]
    cogs_usd = round(photos * (unit["cogs_usd_per_photo"] or 0.0), 2) if known else None
    contribution = round(net_revenue - (cogs_usd or 0.0), 2) if known else None

    return {
        "range_days": days,
        "photos_sold": photos,
        "stars_collected": stars_total,
        "gross_usd": gross_usd,
        "net_revenue_usd": net_revenue,
        "estimated_cogs_usd": cogs_usd,
        "estimated_contribution_usd": contribution,
        "margin_pct": unit["margin_pct"],
        "cost_basis_known": known,
        "below_cost": unit["below_cost"],
        "breakeven_stars_per_photo": breakeven_stars_per_photo(),
        "unit_economics": unit,
        # Trial generations are Redis-only, so this cost is real but invisible.
        "free_trial_photos_per_user": _free_trial_photos(),
        "trial_burn_measured": False,
    }


def _free_trial_photos() -> int:
    try:
        from app.services.companion_access import free_trial_photos

        return free_trial_photos()
    except Exception:
        return 0
