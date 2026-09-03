"""AOF VIP membership ladder — mirrors Gumroad product ``ynnulc`` (1 tier × 5 recurrences).

Stars use ``TBCC_STARS_USD_PER_STAR`` (default $0.012). Gumroad option name on live
product is currently ``Tiers`` — rename in Gumroad to ``VIP · All lanes`` when convenient;
override via ``TBCC_GUMROAD_VIP_OPTION_NAME``.
"""

from __future__ import annotations

import os
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

# One-time intro price for first-time buyers (2026-08-03; extended to 90d 2026-08-17 — $10 holds for
# the first 3 months, standard $18/mo ladder applies after). `name` kept as the original "Intro Month"
# literal on purpose: it's a DB identity key (is_vip_intro_plan_name, protected_main_vip_plan_names) that
# existing rows match on — renaming it would orphan the live row. Only display copy reflects the real length.
VIP_INTRO_SKU = VipMembershipSku(
    name="AOF VIP — Intro Month",
    duration_days=90,
    price_usd=10.0,
    gumroad_recurrence="monthly",
    blurb="First 3 months at intro price · same daily roll + vault + all lanes.",
)
VIP_INTRO_PLAN_NAME = VIP_INTRO_SKU.name
VIP_INTRO_PRICE_CENTS = 1000

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
    if int(cents) == VIP_INTRO_PRICE_CENTS:
        return VIP_INTRO_SKU
    rec = VIP_PRICE_CENTS_TO_RECURRENCE.get(int(cents))
    return sku_for_recurrence(rec) if rec else None


def vip_intro_period_label() -> str:
    """Human label for the intro SKU's length, e.g. "3 months" — derived from duration_days so copy
    never drifts out of sync with the actual offer length again."""
    months = max(1, round(VIP_INTRO_SKU.duration_days / 30))
    return "1 month" if months == 1 else f"{months} months"


def is_vip_intro_plan_name(name: str | None) -> bool:
    return (name or "").strip() == VIP_INTRO_PLAN_NAME


def protected_main_vip_plan_names() -> frozenset[str]:
    """Rows that must survive legacy-main deactivation during seed."""
    return frozenset(sku.name for sku in VIP_MEMBERSHIP_SKUS) | frozenset({VIP_INTRO_PLAN_NAME})


def vip_display_name() -> str:
    """
    Customer-facing brand name for the VIP tier.

    "VIP" reads cheap; DB plan names, Gumroad recurrence, and matching logic (is_vip_intro_plan_name,
    protected_main_vip_plan_names) all stay keyed on the literal "AOF VIP …" strings above — only what
    the customer reads is renamed here. Override via TBCC_VIP_DISPLAY_NAME.
    """
    return (os.getenv("TBCC_VIP_DISPLAY_NAME") or "").strip() or "Insiders"


def display_plan_name(name: str | None) -> str:
    """Cosmetic rewrite of a DB plan name's "AOF VIP" / "VIP" prefix for user-facing copy."""
    n = (name or "").strip()
    if not n:
        return n
    disp = vip_display_name()
    if n.startswith("AOF VIP"):
        return disp + n[len("AOF VIP") :]
    if n.startswith("VIP"):
        return disp + n[len("VIP") :]
    return n


# --- Default shop table (2026-09-03) -------------------------------------------------
# The first screen sells impulse: 24h Loot Room keys, then a single recurring month.
# The multi-month terms stay in the DB and keep resolving for Gumroad Ping + grandfathered
# renewals (sku_for_price_cents / sku_for_recurrence are untouched) — they are only filtered
# out of the default catalog keyboard. Set TBCC_SHOW_FULL_VIP_LADDER=1 to list every term.

FEATURED_VIP_TERM_DAYS = 30


def featured_vip_sku() -> VipMembershipSku:
    """The one recurring term the shop leads with."""
    return sku_for_duration_days(FEATURED_VIP_TERM_DAYS) or VIP_MEMBERSHIP_SKUS[0]


def default_hidden_vip_plan_names() -> frozenset[str]:
    """Multi-month ladder terms buried on the default shop grid (never deleted)."""
    return frozenset(
        sku.name for sku in VIP_MEMBERSHIP_SKUS if sku.duration_days > FEATURED_VIP_TERM_DAYS
    )


def show_full_vip_ladder() -> bool:
    """Escape hatch — list every term again without a redeploy of the catalog logic."""
    return (os.getenv("TBCC_SHOW_FULL_VIP_LADDER") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_hidden_ladder_plan_name(name: str | None) -> bool:
    """True when a plan row is a buried multi-month term (default catalogs skip it)."""
    if show_full_vip_ladder():
        return False
    return (name or "").strip() in default_hidden_vip_plan_names()
