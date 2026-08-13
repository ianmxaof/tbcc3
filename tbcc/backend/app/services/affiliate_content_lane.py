"""Classify affiliate URLs into SFW (Checkout List) vs NSFW (AOF) lanes."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

AffiliateLane = Literal["sfw", "nsfw", "grey"]

_NSFW_HOST_RE = re.compile(
    r"(^|\.)("
    r"nudify|nodress|nakedly|pornmaker|playbun|fapify|botynude|heatme|vixal|"
    r"pornhub|xvideos|xhamster|erome|motherless|thisvid|nutaku|spicevids|"
    r"bangbros|brazzers|realitykings|musebox|motionmuse|drawai|venersbot|hotdreams"
    r")(\.|/|$)",
    re.I,
)

_NSFW_PATH_RE = re.compile(
    r"nodress|nudify|pornmaker|/ref/.*bot|t\.me/\w+bot|telegram\.me/\w+bot|"
    r"gumroad\.com/l/|allmylinks\.com",
    re.I,
)

_NSFW_LABEL_RE = re.compile(
    r"nudify|undress|porn|xxx|nsfw|blowjob|milf|taboo|goon|loot god|aof vip|"
    r"cherry affair|nakedly|playbun|fapify|spicevids|nutaku",
    re.I,
)

_SFW_HOST_RE = re.compile(
    r"(^|\.)("
    r"rakuten\.com|chime\.com|pr\.tn|revolut\.com|cursor\.com|claude\.ai|anthropic\.com|"
    r"proton\.me|protonmail\.com|pulsedmedia\.com|rewards\.bing\.com|"
    r"amazon\.|flipkart\.com|dealscrown\.com|microsoft\.com|"
    r"cometapi\.com|kit\.com|buffer\.com|cloudflare\.com|hetzner\.com|"
    r"namecheap\.com|digitalocean\.com|linode\.com|vultr\.com|"
    r"nordvpn\.com|mullvad\.net|protonvpn\.com"
    r")",
    re.I,
)

# SFW Telegram mini-apps / wallets — must beat the generic t.me/*bot NSFW path.
_SFW_TG_BOT_RE = re.compile(
    r"(?:t\.me|telegram\.me)/(?:CloudFarmWalletBot)(?:/|$|\?)",
    re.I,
)

_SFW_LABEL_RE = re.compile(
    r"rakuten|chime|revolut|cursor|claude|proton|seedbox|pulsed|bing rewards|microsoft rewards|"
    r"comet api|vpn|hosting|cloudflare|digitalocean|cloud farm|cloudfarm",
    re.I,
)


def _hostname(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_affiliate_lane(url: str, label: str = "") -> AffiliateLane:
    """
    Route affiliate intake to Checkout List (sfw) or AOF surfaces (nsfw).

    Grey = unknown — intake keeps out of Checkout List unless forced sfw.
    """
    u = (url or "").strip()
    blob = f"{label} {u}".strip()
    host = _hostname(u)

    if _SFW_TG_BOT_RE.search(u) or _SFW_HOST_RE.search(host) or _SFW_LABEL_RE.search(blob):
        return "sfw"
    if _NSFW_HOST_RE.search(host) or _NSFW_PATH_RE.search(u) or _NSFW_LABEL_RE.search(blob):
        return "nsfw"
    return "grey"


def placements_for_lane(lane: AffiliateLane, *, force_sfw: bool = False) -> list[str]:
    from app.services.promo_affiliate_rotation import AFFILIATE_PLACEMENTS, DEFAULT_PLACEMENT

    if force_sfw or lane == "sfw":
        return ["links_hub_sfw"]
    nsfw = sorted(
        p
        for p in AFFILIATE_PLACEMENTS
        if p not in (DEFAULT_PLACEMENT, "links_hub_sfw")
    )
    if lane == "grey":
        # Keep grey out of Checkout List until operator forces sfw.
        return nsfw
    return nsfw


def lane_display(lane: AffiliateLane) -> str:
    return {
        "sfw": "Checkout List (SFW)",
        "nsfw": "AOF affiliate rotation",
        "grey": "AOF rotation (unclassified — use <code>sfw</code> prefix for Checkout List)",
    }.get(lane, lane)
