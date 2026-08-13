"""Format Traffic Pulse / secretary messages for affiliate click beacons."""

from __future__ import annotations

import html
import re
from typing import Any

from app.data.aof_network import MAINHUB_RAW, MAIN_GROUP_INVITE

_PLACEMENT_FROM_LABEL_RE = re.compile(r"·\s*([a-z0-9_]+)\s*$", re.IGNORECASE)

# Operator shortcuts — where each placement usually surfaces.
PLACEMENT_HUB_URLS: dict[str, str] = {
    "x_buffer": "https://publish.buffer.com/",
    "telegram_footer": MAIN_GROUP_INVITE,
    "loot_roll": "https://t.me/aof_lootgod_bot",
    "links_hub": MAINHUB_RAW,
    "links_hub_ai": MAINHUB_RAW,
}


def _parse_beacon_placement_from_slug(slug: str | None) -> str | None:
    s = (slug or "").strip().lower()
    if not s.startswith("aff-"):
        return None
    for key in sorted(PLACEMENT_HUB_URLS.keys(), key=len, reverse=True):
        suffix = key.replace("_", "-")
        if s.endswith("-" + suffix):
            return key
    return None


def parse_beacon_placement(*, label: str | None, slug: str | None) -> str | None:
    """Infer placement key from beacon label (DrawAI · x_buffer) or slug (aff-drawai-x-buffer)."""
    lab = (label or "").strip()
    m = _PLACEMENT_FROM_LABEL_RE.search(lab)
    if m:
        return m.group(1).strip().lower()
    return _parse_beacon_placement_from_slug(slug)


def placement_hub_url(placement: str | None) -> str | None:
    key = (placement or "").strip().lower()
    if not key:
        return None
    return PLACEMENT_HUB_URLS.get(key)


def _short_url(url: str, *, max_len: int = 72) -> str:
    u = (url or "").strip()
    if len(u) <= max_len:
        return u
    return u[: max_len - 1] + "…"


def _link_line(label: str, url: str | None) -> str | None:
    u = (url or "").strip()
    if not u or not u.startswith(("http://", "https://", "tg://")):
        return None
    safe_url = html.escape(u, quote=True)
    safe_label = html.escape(label)
    return f'{safe_label} <a href="{safe_url}">{html.escape(_short_url(u))}</a>'


def format_traffic_beacon_body_html(meta: dict[str, Any]) -> str:
    """Telegram HTML body for click-beacon traffic pulse events."""
    slug = html.escape(str(meta.get("slug") or ""))
    hits = int(meta.get("hit_count") or 0)
    placement = str(meta.get("placement") or parse_beacon_placement(
        label=str(meta.get("link_label") or ""),
        slug=str(meta.get("slug") or ""),
    ) or "")
    lines = [f"slug <code>{slug}</code> · hits <b>{hits}</b>"]

    ref = (meta.get("source_ref") or "").strip()
    if ref:
        lines.append(f"ref <code>{html.escape(ref[:56])}</code>")

    dest_line = _link_line("dest", str(meta.get("destination_url") or ""))
    if dest_line:
        lines.append(dest_line)

    beacon_line = _link_line("beacon", str(meta.get("beacon_url") or ""))
    if beacon_line:
        lines.append(beacon_line)

    hub = placement_hub_url(placement)
    if placement and hub:
        pl = html.escape(placement)
        hub_line = _link_line(f"lane · {pl}", hub)
        if hub_line:
            lines.append(hub_line)
    elif placement:
        lines.append(f"lane <code>{html.escape(placement)}</code>")

    referer = (meta.get("referer") or "").strip()
    if referer:
        ref_line = _link_line("from", referer)
        if ref_line:
            lines.append(ref_line)

    ip = (meta.get("ip") or "").strip()
    country = (meta.get("country") or "").strip()
    if ip or country:
        ip_s = html.escape(ip or "?")
        cc = html.escape(country or "??")
        lines.append(f"ip {ip_s} · {cc}")

    campaign = (meta.get("campaign_id") or "").strip()
    if campaign:
        lines.append(f"post <code>{html.escape(campaign[:64])}</code>")

    return "\n".join(lines)


def beacon_pulse_meta(
    link: Any,
    hit: Any,
    *,
    link_label: str | None = None,
) -> dict[str, Any]:
    """Build inbox meta for a click-beacon hit (link + hit ORM rows)."""
    from app.services.click_beacon import link_public_url

    label = (link_label or getattr(link, "label", None) or getattr(link, "slug", None) or "").strip()
    slug = str(getattr(link, "slug", "") or "")
    placement = parse_beacon_placement(label=label, slug=slug)
    return {
        "slug": slug,
        "source_ref": (getattr(link, "source_ref", None) or "").strip() or None,
        "hit_count": int(getattr(link, "hit_count", 0) or 0),
        "link_label": label,
        "placement": placement,
        "destination_url": getattr(link, "destination_url", None),
        "beacon_url": link_public_url(link),
        "referer": getattr(hit, "referer", None),
        "ip": getattr(hit, "ip", None),
        "country": getattr(hit, "country", None),
        "campaign_id": getattr(hit, "campaign_id", None),
        "user_agent": (getattr(hit, "user_agent", None) or "")[:120] or None,
    }
