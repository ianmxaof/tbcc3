"""Companion reveal credit packs — payment-bot catalog (Stars + crypto).

Single-reveal impulse buys stay native in @aof_spicybot_bot (TBCC_COMPANION_STARS_PER_PHOTO).
These packs are the tiered top-up ladder sold via payment bot (bot_section=companion).

Pricing locked 2026-08-08 — keep per-reveal above VIP intro effective rate (~$10 + 3 bonus credits).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanionCreditPack:
    sku: str
    plan_name: str
    credit_units: int
    price_stars: int
    price_usd: float
    blurb: str


COMPANION_CREDIT_PACKS: tuple[CompanionCreditPack, ...] = (
    CompanionCreditPack(
        sku="companion_5",
        plan_name="Spicy Reveal — 5 Pack",
        credit_units=5,
        price_stars=110,
        price_usd=4.99,
        blurb="5 photo reveals on @aof_spicybot_bot · ~12% off vs single Stars.",
    ),
    CompanionCreditPack(
        sku="companion_15",
        plan_name="Spicy Reveal — 15 Pack",
        credit_units=15,
        price_stars=300,
        price_usd=11.99,
        blurb="15 reveals · best value for regulars · ~20% off singles.",
    ),
    CompanionCreditPack(
        sku="companion_50",
        plan_name="Spicy Reveal — 50 Pack",
        credit_units=50,
        price_stars=900,
        price_usd=34.99,
        blurb="50 reveals · power user · ~28% off singles.",
    ),
)

COMPANION_CREDIT_PLAN_NAMES: frozenset[str] = frozenset(p.plan_name for p in COMPANION_CREDIT_PACKS)


def pack_for_sku(sku: str | None) -> CompanionCreditPack | None:
    key = (sku or "").strip().lower()
    if not key:
        return None
    if not key.startswith("companion_"):
        key = f"companion_{key}"
    for pack in COMPANION_CREDIT_PACKS:
        if pack.sku == key:
            return pack
    return None


def pack_for_plan_name(name: str | None) -> CompanionCreditPack | None:
    raw = (name or "").strip()
    for pack in COMPANION_CREDIT_PACKS:
        if pack.plan_name == raw:
            return pack
    return None


def credit_units_for_plan_name(name: str | None) -> int | None:
    pack = pack_for_plan_name(name)
    return pack.credit_units if pack else None
