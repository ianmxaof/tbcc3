"""Per-platform plain captions for Buffer (IG) and Discord webhook fan-out."""

from __future__ import annotations

import os
import re

from app.data.aof_network import MAINHUB_RAW
from app.services.utm_links import allmylinks_tracked_url

_URL_RE = re.compile(r"https?://\S+")


def _display_url(url: str) -> str:
    """Strip scheme for IG-style plain text (not clickable in caption anyway)."""
    u = (url or "").strip()
    return u.replace("https://", "").replace("http://", "").rstrip("/")


def aof_discord_invite_url() -> str:
    return (os.getenv("TBCC_AOF_DISCORD_INVITE_URL") or "").strip()


def aof_mainhub_display() -> str:
    raw = (os.getenv("TBCC_AOF_MAINHUB_DISPLAY") or MAINHUB_RAW).strip()
    return _display_url(raw) if raw.startswith("http") else raw.lstrip("@")


def teaser_without_urls(text: str | None, *, max_len: int = 280) -> str:
    """One-line promo hook with URLs removed — safe for IG captions."""
    t = _URL_RE.sub("", (text or "").strip())
    t = re.sub(r"\s*[·|—–-]\s*", " · ", t)
    t = re.sub(r"\s+", " ", t).strip(" ·-|")
    return t[:max_len] if t else ""


def build_instagram_caption(
    *,
    teaser: str | None = None,
    utm_campaign: str = "instagram",
    include_gate: bool = False,
) -> str:
    """
    Instagram caption: plain text only (no HTML). Links are not tappable in IG captions —
    use hub / allmylinks as readable text + 'link in bio' pattern.
    """
    aml = allmylinks_tracked_url(
        source="buffer",
        medium="instagram",
        campaign=utm_campaign,
    )
    hub = aof_mainhub_display()
    lines = [
        "Archive of Filth — AOF Network",
        "",
        f"Hub → {hub}",
        f"Full map (link in bio) → {_display_url(aml) if aml else 'allmylinks.com/aof69'}",
    ]
    hook = teaser_without_urls(teaser)
    if hook:
        lines.extend(["", hook])
    if include_gate:
        from app.services.aof_social_links import aof_gate_url

        gate = aof_gate_url()
        if gate:
            lines.append(f"Gate → {_display_url(gate)}")
    lines.append("")
    lines.append("Tap link in bio for the full stack.")
    return "\n".join(lines).strip()[:2200]


def build_discord_caption(
    *,
    teaser: str | None = None,
    utm_campaign: str = "discord",
    include_gate: bool = True,
) -> str:
    """Discord webhook body — URLs auto-linkify; include community invite when set."""
    aml = allmylinks_tracked_url(
        source="discord",
        medium="relay",
        campaign=utm_campaign,
    )
    lines = [
        "**AOF Network**",
        "",
        f"Main hub: {MAINHUB_RAW}",
    ]
    if aml:
        lines.append(f"Full map: {aml}")
    invite = aof_discord_invite_url()
    if invite:
        lines.append(f"Discord: {invite}")
    if include_gate:
        from app.services.aof_social_links import aof_gate_url

        gate = aof_gate_url()
        if gate:
            lines.append(f"Gate: {gate}")
    hook = (teaser or "").strip()
    if hook:
        if len(hook) > 600:
            hook = hook[:597] + "…"
        lines.extend(["", hook])
    return "\n".join(lines).strip()[:2000]
