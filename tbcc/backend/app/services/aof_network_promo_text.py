"""Plain-text promo copy for Mega pack READMEs and zip inserts."""

from __future__ import annotations

import os

from app.data.aof_network import (
    ADDLIST_RAW,
    AOF_NETWORK_CHANNELS,
    MAINHUB_RAW,
)
from app.services.aof_social_links import aof_gate_url, aof_hub_invite_url, allmylinks_url
from app.services.utm_links import allmylinks_tracked_url


def build_mega_pack_readme_text(*, extra_lines: list[str] | None = None) -> str:
    """
    Network channel link list for README inside Mega folders.
    Uses aof_network.py invites + gate/allmylinks from .env.
    """
    gate = (os.getenv("TBCC_WORKINK_BASE_LINK") or aof_gate_url() or "").strip()
    hub = aof_hub_invite_url()
    custom = (os.getenv("TBCC_ZIP_PROMO_TEXT") or "").strip()

    lines: list[str] = [
        "AOF — Telegram Network",
        "========================",
        "",
        f"Main hub (public): {MAINHUB_RAW}",
        f"Loot Room entry (public): {hub}",
        f"Add all channels: {ADDLIST_RAW}",
        "",
        "Network channels:",
        "-----------------",
    ]
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key == "main":
            continue
        lines.append(f"{ch.display_name}: {ch.invite}")

    lines.extend(
        [
            "",
            "Monetization & bots",
            "-------------------",
        ]
    )
    if gate:
        lines.append(f"Public gate (complete ad step): {gate}")
    aml = allmylinks_tracked_url(source="mega", medium="readme", campaign="pack_readme")
    if aml:
        lines.append(f"Link hub: {aml}")
    lines.append("Shop / subscribe: @aofsubscriptions_bot")
    lines.append("Loot room: @aof_lootgod_bot")
    lines.append("")
    lines.append("Gate clicks fund the pipeline — do not strip links for clearnet reposts.")

    if custom:
        lines.extend(["", "—", custom])

    if extra_lines:
        lines.extend([""] + [ln.strip() for ln in extra_lines if ln.strip()])

    return "\n".join(lines).strip() + "\n"
