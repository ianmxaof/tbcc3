"""
Canonical beacon slug + source_ref for every Linkvertise gate destination.

Naming (locked in MODULE A attribution plan):
    beacon slug   {week}-lv-{key}        e.g. wk31-lv-ass
    source ref    src_lv_{key}_{week}    e.g. src_lv_ass_wk31

Only bot destinations can carry a `?start=` payload. Lanes that resolve to a
real AOF channel are therefore relayed through the loot bot, which records the
touch and then hands over the same invite. Keys with no resolvable channel
(`mainhub`, `addlist`) stay beacon-only: clicks and geography, no conversion
join.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.data.aof_manual_gate_links import AOF_MANUAL_LV_GATES
from app.data.aof_network import network_channel_by_key
from app.services.lane_gate_relay import is_relayable_lane

ATTRIBUTION_FULL = "full"
ATTRIBUTION_CLICK_ONLY = "click_only"

_WEEK_RE = re.compile(r"^[a-z0-9]{2,12}$")

LOOT_BOT_URL = "https://telegram.me/aof_lootgod_bot"

# Gate keys whose destination is a bot, so `?start=` attribution works end to end.
BOT_ROUTE_DESTINATIONS: dict[str, str] = {
    "loot": LOOT_BOT_URL,
    "main": LOOT_BOT_URL,
    "main_group": LOOT_BOT_URL,
    "lootgod": LOOT_BOT_URL,
}

# Keys that are aliases or not real gate destinations to beacon separately.
SKIP_KEYS = frozenset({"main"})


@dataclass(frozen=True)
class GateBeacon:
    key: str
    slug: str
    source_ref: str
    destination_url: str
    label: str
    attribution: str
    gate_url: str

    @property
    def is_full_attribution(self) -> bool:
        return self.attribution == ATTRIBUTION_FULL


def normalize_week_tag(week: str) -> str:
    w = (week or "").strip().lower()
    if not _WEEK_RE.match(w):
        raise ValueError("week tag must be 2-12 chars [a-z0-9], e.g. wk31")
    return w


def beacon_slug(key: str, week: str) -> str:
    return f"{normalize_week_tag(week)}-lv-{key.strip().lower()}"


def beacon_source_ref(key: str, week: str) -> str:
    return f"src_lv_{key.strip().lower()}_{normalize_week_tag(week)}"


def _destination_for(key: str, week: str) -> tuple[str, str, str]:
    """Return (destination_url, label, attribution) for a gate key."""
    bot_url = BOT_ROUTE_DESTINATIONS.get(key)
    if bot_url:
        return (
            f"{bot_url}?start={beacon_source_ref(key, week)}",
            f"LV {key} → loot bot",
            ATTRIBUTION_FULL,
        )

    channel = network_channel_by_key(key)
    if channel and (channel.invite or "").strip():
        if is_relayable_lane(key):
            # Bot relay first, then the same invite — one extra tap buys the
            # touch that a bare channel invite can never produce.
            return (
                f"{LOOT_BOT_URL}?start={beacon_source_ref(key, week)}",
                f"LV {key} → loot bot → {channel.display_name}",
                ATTRIBUTION_FULL,
            )
        return (channel.invite.strip(), f"LV {key} → {channel.display_name}", ATTRIBUTION_CLICK_ONLY)

    # No known Telegram destination (mainhub, addlist): beacon the gate's own
    # current target so the click still lands in click_link_hits.
    return (
        AOF_MANUAL_LV_GATES.get(key) or LOOT_BOT_URL,
        f"LV {key}",
        ATTRIBUTION_CLICK_ONLY,
    )


def build_gate_beacon_plan(week: str) -> list[GateBeacon]:
    """One beacon per manual Linkvertise gate, deterministic and idempotent by slug."""
    wk = normalize_week_tag(week)
    out: list[GateBeacon] = []
    for key, gate_url in AOF_MANUAL_LV_GATES.items():
        if key in SKIP_KEYS:
            continue
        dest, label, attribution = _destination_for(key, wk)
        out.append(
            GateBeacon(
                key=key,
                slug=beacon_slug(key, wk),
                source_ref=beacon_source_ref(key, wk),
                destination_url=dest,
                label=label,
                attribution=attribution,
                gate_url=gate_url,
            )
        )
    return sorted(out, key=lambda b: b.key)


def plan_as_dicts(week: str) -> list[dict[str, str]]:
    return [
        {
            "key": b.key,
            "slug": b.slug,
            "source_ref": b.source_ref,
            "destination_url": b.destination_url,
            "label": b.label,
            "attribution": b.attribution,
            "gate_url": b.gate_url,
        }
        for b in build_gate_beacon_plan(week)
    ]
