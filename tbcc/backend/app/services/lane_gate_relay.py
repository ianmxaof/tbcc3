"""
Relay lane gate traffic through the loot bot so lanes become measurable.

A Linkvertise slug pointed straight at a channel invite is unmeasurable: the
invite cannot carry a ?start= payload, so the click never becomes a funnel
touch and the lane can never be credited with revenue. Pointing the slug at
the loot bot with ?start=src_lv_<lane>_<wk> instead means the bot records the
touch and then hands over the same invite, which costs the user one extra tap
and buys full click -> touch -> revenue attribution.
"""

from __future__ import annotations

import re

from app.data.aof_network import network_channel_by_key

_LANE_PAYLOAD_RE = re.compile(r"^src_lv_(?P<rest>[a-z0-9_]+)$")


def parse_lane_gate_payload(payload: str) -> tuple[str, str] | None:
    """
    `src_lv_big_tits_wk31` -> ("big_tits", "wk31").

    Returns None unless the lane resolves to a real AOF channel with an invite,
    so a typo'd payload falls through to the normal welcome instead of
    silently dead-ending.
    """
    raw = (payload or "").strip().lower()
    m = _LANE_PAYLOAD_RE.match(raw)
    if not m:
        return None
    lane, _, week = m.group("rest").rpartition("_")
    if not lane or not week:
        return None
    if not lane_invite_url(lane):
        return None
    return lane, week


def lane_invite_url(lane_key: str) -> str | None:
    channel = network_channel_by_key((lane_key or "").strip().lower())
    if not channel:
        return None
    invite = (channel.invite or "").strip()
    return invite or None


def lane_display_name(lane_key: str) -> str:
    channel = network_channel_by_key((lane_key or "").strip().lower())
    if channel and (channel.display_name or "").strip():
        return channel.display_name.strip()
    return (lane_key or "").replace("_", " ").upper()


def is_relayable_lane(lane_key: str) -> bool:
    return lane_invite_url(lane_key) is not None
