"""Sequenced sponsor packs — overlay on PromoAffiliateLink rotation (v1).

Doctrine locked 2026-08-13:
- One CTA per rotation send; Zeus wrap stays in promo_affiliate_rotation.
- Packs overlay catalog rows by exact label; no new DB table.
- Pack A = SFW finance; B = AI→owned; C = lane PPS→loot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackSlot:
    index: int
    label: str
    role: str  # hero | trust | tool | owned
    required: bool = False


@dataclass(frozen=True)
class SponsorPack:
    id: str
    title: str
    lane: str  # sfw | nsfw | mixed
    surfaces: tuple[str, ...]
    network_keys: tuple[str, ...] | None
    max_ctas_per_message: int
    slots: tuple[PackSlot, ...]


PACK_WALLET_EARN = SponsorPack(
    id="wallet_earn",
    title="Wallet → Earn",
    lane="sfw",
    surfaces=("links_hub_sfw", "links_hub", "x_buffer", "bot_network_menu"),
    network_keys=None,
    max_ctas_per_message=1,
    slots=(
        PackSlot(0, "Cloud Farm Wallet", "hero"),
        PackSlot(1, "Chime", "trust"),
        PackSlot(2, "Proton — $20 credits", "trust"),
        PackSlot(3, "Rakuten", "trust"),
    ),
)

PACK_LEARN_AI_PAY = SponsorPack(
    id="learn_ai_pay",
    title="Learn AI → Try → Pay",
    lane="nsfw",
    surfaces=("x_buffer", "links_hub_ai", "loot_roll"),
    network_keys=None,
    max_ctas_per_message=1,
    slots=(
        PackSlot(0, "Musebox AI", "tool"),
        PackSlot(1, "Lucid Dreams Bot", "tool"),
        PackSlot(2, "Cherry Affair (nudify.systems)", "tool"),
        PackSlot(3, "AOF Spicy Companion", "owned"),
    ),
)

# Lane PPS sequences — owned close is always Loot God free roll.
_LANE_PPS: dict[str, tuple[str, ...]] = {
    "milf": ("BangBros PPS", "Brazzers PPS"),
    "taboo": ("BangBros PPS", "Brazzers PPS"),
    "big_tits": ("BangBros PPS", "Brazzers PPS"),
    "voyeur": ("Reality Kings PPS", "BangBros PPS"),
    "goon": ("Spicevids PPS", "Bromo Network PPS"),
    "bop": ("Spicevids PPS", "Bromo Network PPS"),
    "abg": ("Erito Network PPS", "Nutaku — Lust Goddess"),
    "ai": ("Erito Network PPS", "Nutaku — Lust Goddess"),
}
_DEFAULT_PPS: tuple[str, ...] = ("BangBros PPS", "Spicevids PPS")
_OWNED_LOOT = "Loot God free roll"

PACK_LANE_PPS = SponsorPack(
    id="lane_pps",
    title="Lane PPS → Loot",
    lane="nsfw",
    surfaces=("telegram_footer", "loot_roll"),
    network_keys=tuple(sorted(_LANE_PPS.keys())),
    max_ctas_per_message=1,
    slots=(),  # resolved per network_key
)

SPONSOR_PACKS: tuple[SponsorPack, ...] = (
    PACK_WALLET_EARN,
    PACK_LEARN_AI_PAY,
    PACK_LANE_PPS,
)

# Contested surface → which packs may rotate (order = meta-cursor sequence).
PLACEMENT_PACK_ROTATION: dict[str, tuple[str, ...]] = {
    "links_hub_sfw": ("wallet_earn",),
    "links_hub": ("wallet_earn",),
    "links_hub_ai": ("learn_ai_pay",),
    "telegram_footer": ("lane_pps",),
    "x_buffer": ("wallet_earn", "learn_ai_pay"),
    "loot_roll": ("learn_ai_pay", "lane_pps"),
    "bot_network_menu": ("wallet_earn",),
}

META_CURSOR_KEYS: dict[str, str] = {
    "x_buffer": "pack:x_buffer_meta",
    "loot_roll": "pack:loot_roll_meta",
}


def pack_by_id(pack_id: str) -> SponsorPack | None:
    key = (pack_id or "").strip().lower()
    for pack in SPONSOR_PACKS:
        if pack.id == key:
            return pack
    return None


def slots_for_pack(pack: SponsorPack, *, network_key: str | None = None) -> tuple[PackSlot, ...]:
    if pack.id != "lane_pps":
        return pack.slots
    nk = (network_key or "").strip().lower()
    pps = _LANE_PPS.get(nk) or _DEFAULT_PPS
    out: list[PackSlot] = []
    for i, label in enumerate(pps):
        out.append(PackSlot(i, label, "hero" if i == 0 else "tool"))
    out.append(PackSlot(len(pps), _OWNED_LOOT, "owned"))
    return tuple(out)


def pack_a_finance_label_order() -> tuple[str, ...]:
    """Checkout List FINANCE section sort: Pack A slots first."""
    return tuple(s.label for s in PACK_WALLET_EARN.slots)


def label_to_pack_ids() -> dict[str, list[str]]:
    """Exact label → pack ids that reference it (for analytics rollup)."""
    out: dict[str, list[str]] = {}
    for pack in SPONSOR_PACKS:
        if pack.id == "lane_pps":
            labels = set(_DEFAULT_PPS) | {_OWNED_LOOT}
            for seq in _LANE_PPS.values():
                labels.update(seq)
        else:
            labels = {s.label for s in pack.slots}
        for lab in labels:
            out.setdefault(lab, []).append(pack.id)
    return out
