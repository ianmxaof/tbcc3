"""AOF VIP membership ladder — mirrors Gumroad product ``ynnulc`` (1 tier × 5 recurrences).

Stars use ``TBCC_STARS_USD_PER_STAR`` (default $0.012). Gumroad option name on live
product is currently ``Tiers`` — rename in Gumroad to ``VIP · All lanes`` when convenient;
override via ``TBCC_GUMROAD_VIP_OPTION_NAME``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VipMembershipSku:
    """One VIP term (Stars + crypto + Gumroad recurrence)."""

    name: str
    duration_days: int
    price_usd: float
    gumroad_recurrence: str  # monthly|quarterly|biannually|yearly|every_two_years
    blurb: str


# Locked 2026-07-27 — match https://aof69.gumroad.com/l/ynnulc tier prices ($18 floor).
# Operator: update Gumroad product tiers + TBCC_GUMROAD_PRODUCT_MAP price:* keys (see handoff).
GUMROAD_VIP_PRODUCT_URL = "https://aof69.gumroad.com/l/ynnulc"

VIP_MEMBERSHIP_SKUS: tuple[VipMembershipSku, ...] = (
    VipMembershipSku(
        name="AOF VIP — 1 Month",
        duration_days=30,
        price_usd=18.0,
        gumroad_recurrence="monthly",
        blurb="VIP · 30 days · daily god roll · clean vault · all lanes.",
    ),
    VipMembershipSku(
        name="AOF VIP — 3 Months",
        duration_days=90,
        price_usd=48.0,
        gumroad_recurrence="quarterly",
        blurb="~11% off vs 3× monthly · 90 days VIP.",
    ),
    VipMembershipSku(
        name="AOF VIP — 6 Months",
        duration_days=180,
        price_usd=90.0,
        gumroad_recurrence="biannually",
        blurb="~17% off vs 6× monthly · 180 days VIP.",
    ),
    VipMembershipSku(
        name="AOF VIP — 1 Year",
        duration_days=365,
        price_usd=168.0,
        gumroad_recurrence="yearly",
        blurb="~22% off vs 12× monthly · full year VIP.",
    ),
    VipMembershipSku(
        name="AOF VIP — 2 Years",
        duration_days=730,
        price_usd=300.0,
        gumroad_recurrence="every_two_years",
        blurb="~31% off vs 24× monthly · 2 years VIP.",
    ),
)

# Gumroad price field is cents; used for Ping recurrence fallback when no EPO.
# Legacy keys kept for grandfathered renewals — add new price:* keys in PRODUCT_MAP on deploy.
VIP_PRICE_CENTS_TO_RECURRENCE: dict[int, str] = {
    # Legacy (pre-2026-07-27)
    600: "monthly",
    1500: "quarterly",
    3000: "biannually",
    5400: "yearly",
    10000: "every_two_years",
    # Current ladder
    1800: "monthly",
    4800: "quarterly",
    9000: "biannually",
    16800: "yearly",
    30000: "every_two_years",
}


def sku_for_recurrence(recurrence: str) -> VipMembershipSku | None:
    key = (recurrence or "").strip().lower()
    for sku in VIP_MEMBERSHIP_SKUS:
        if sku.gumroad_recurrence == key:
            return sku
    return None


def sku_for_duration_days(days: int) -> VipMembershipSku | None:
    d = int(days)
    for sku in VIP_MEMBERSHIP_SKUS:
        if sku.duration_days == d:
            return sku
    return None


def sku_for_price_cents(cents: int) -> VipMembershipSku | None:
    rec = VIP_PRICE_CENTS_TO_RECURRENCE.get(int(cents))
    return sku_for_recurrence(rec) if rec else None
