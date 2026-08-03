"""Human-readable, compact copy for Traffic Pulse inbox + instant DMs."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from app.services.traffic_beacon_notify import parse_beacon_placement

_PLACEMENT_HUMAN: dict[str, str] = {
    "x_buffer": "Buffer X queue",
    "telegram_footer": "TG channel caption footer",
    "links_hub": "@aofmainhub link hub",
    "links_hub_ai": "link hub · AI tools row",
    "loot_roll": "Loot God DM roll footer",
    "manual_only": "dashboard insert only",
}

_PULSE_KIND: dict[str, str] = {
    "post_ok": "Scheduler post delivered",
    "post_fail": "Scheduler post failed",
    "affiliate_served": "Affiliate link rotated in",
    "beacon": "Click beacon hit",
    "start": "Bot /start deep link",
    "loot_roll": "Loot roll completed",
}


def placement_human(placement: str | None) -> str:
    key = (placement or "").strip().lower()
    if not key:
        return "unknown surface"
    return _PLACEMENT_HUMAN.get(key, key.replace("_", " "))


def pulse_kind_human(pulse_type: str | None) -> str:
    key = (pulse_type or "").strip().lower()
    return _PULSE_KIND.get(key, key.replace("_", " ") or "traffic")


def _short_slug(slug: str | None, *, max_len: int = 28) -> str:
    s = (slug or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _host_from_url(url: str | None) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host or ""
    except Exception:
        return ""


def enrich_post_pulse_meta(
    *,
    scheduled_post_id: int | None,
    channel_id: int | None,
    event_type: str | None = None,
    pool_id: int | None = None,
) -> dict[str, Any]:
    """Resolve scheduler/channel names for inbox copy (best-effort, no raise)."""
    out: dict[str, Any] = {}
    et = (event_type or "").strip()
    if et:
        out["outbound_event_type"] = et
    try:
        from app.database.session import SessionLocal
        from app.models.channel import Channel
        from app.models.content_pool import ContentPool
        from app.models.scheduled_text_post import ScheduledTextPost

        db = SessionLocal()
        try:
            if scheduled_post_id:
                post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(scheduled_post_id)).first()
                if post:
                    out["scheduled_post_name"] = (post.name or "").strip() or None
                    out["interval_minutes"] = post.interval_minutes
                    if post.pool_id and not pool_id:
                        pool_id = int(post.pool_id)
            if channel_id:
                ch = db.query(Channel).filter(Channel.id == int(channel_id)).first()
                if ch:
                    out["channel_name"] = (ch.name or ch.identifier or "").strip() or None
            if pool_id:
                pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
                if pool:
                    out["pool_name"] = (pool.name or "").strip() or None
        finally:
            db.close()
    except Exception:
        pass
    return out


def format_traffic_title(meta: dict[str, Any], *, fallback: str = "") -> str:
    """Short title for instant push."""
    pt = str(meta.get("pulse_event_type") or "")
    if pt == "post_ok":
        ch = meta.get("channel_name") or f"ch#{meta.get('channel_id') or '?'}"
        sched = meta.get("scheduled_post_name") or f"job #{meta.get('scheduled_post_id') or '?'}"
        return f"TG post · {ch} · {sched}"
    if pt == "post_fail":
        ch = meta.get("channel_name") or f"ch#{meta.get('channel_id') or '?'}"
        return f"TG post FAILED · {ch}"
    if pt == "affiliate_served":
        label = str(meta.get("label") or "sponsor").strip()
        surf = placement_human(str(meta.get("placement") or ""))
        return f"Affiliate slot · {label} · {surf}"
    if pt == "beacon":
        label = str(meta.get("link_label") or meta.get("slug") or "beacon").strip()
        label = re.sub(r"\s*·\s*[a-z0-9_]+\s*$", "", label, flags=re.IGNORECASE)
        hits = int(meta.get("hit_count") or 0)
        return f"Beacon click · {label} · hit #{hits}"
    if pt == "start":
        ref = str(meta.get("source_ref") or "bot").strip()
        return f"Bot entry · {ref}"
    if pt == "loot_roll":
        kind = str(meta.get("roll_kind") or "roll")
        tier = meta.get("tier")
        return f"Loot roll · {kind} · tier {tier}"
    return fallback or pulse_kind_human(pt)


def format_traffic_detail(meta: dict[str, Any], *, raw_body: str = "") -> str:
    """One compact detail line (HTML)."""
    pt = str(meta.get("pulse_event_type") or "")
    if pt == "post_ok":
        parts: list[str] = []
        et = str(meta.get("outbound_event_type") or meta.get("event_type") or "")
        if et == "pool_album_posted":
            parts.append("pool album export")
        elif et:
            parts.append(html.escape(et.replace("_", " ")))
        interval = meta.get("interval_minutes")
        if interval:
            parts.append(f"every {int(interval)}m")
        sid = meta.get("scheduled_post_id")
        if sid:
            parts.append(f"job <code>#{html.escape(str(sid))}</code>")
        pool = meta.get("pool_name")
        if pool:
            parts.append(html.escape(str(pool)[:40]))
        return " · ".join(parts) if parts else "Celery beat fired; message reached Telegram"

    if pt == "post_fail":
        err = html.escape(str(meta.get("error_message") or raw_body or "unknown")[:120])
        return f"Error: {err}"

    if pt == "affiliate_served":
        slug = _short_slug(str(meta.get("slug") or ""))
        host = _host_from_url(str(meta.get("url") or ""))
        bits = []
        if slug:
            bits.append(f"<code>{html.escape(slug)}</code>")
        if host:
            bits.append(html.escape(host))
        return " · ".join(bits) if bits else "Sponsor URL now in rotation"

    if pt == "beacon":
        placement = placement_human(
            str(meta.get("placement") or parse_beacon_placement(
                label=str(meta.get("link_label") or ""),
                slug=str(meta.get("slug") or ""),
            ) or "")
        )
        bits = [html.escape(placement)]
        slug = _short_slug(str(meta.get("slug") or ""))
        if slug:
            bits.append(f"<code>{html.escape(slug)}</code>")
        ref = (meta.get("referer") or "").strip()
        if ref:
            bits.append(f"from {html.escape(_host_from_url(ref) or ref[:40])}")
        cc = (meta.get("country") or "").strip()
        if cc:
            bits.append(html.escape(cc))
        return " · ".join(bits)

    if pt == "start":
        payload = html.escape(str(meta.get("payload") or "")[:60])
        uid = meta.get("telegram_user_id")
        return f"uid <code>{html.escape(str(uid))}</code> · payload <code>{payload}</code>"

    if pt == "loot_roll":
        media = meta.get("media_sent")
        return f"delivered {html.escape(str(media))} item(s) to DM"

    if raw_body:
        return html.escape(raw_body[:160])
    return ""


def format_traffic_compact_line(event: dict[str, Any], *, ago: str) -> str:
    """Single-line digest entry for a traffic event."""
    meta = event.get("meta") or {}
    icon = "📡"
    title = format_traffic_title(meta, fallback=str(event.get("title") or "Traffic"))
    detail = format_traffic_detail(meta, raw_body=str(event.get("body") or ""))
    line = f"{icon} <b>{html.escape(title)}</b> · <code>{html.escape(ago)}</code>"
    if detail:
        line += f"\n  <i>{detail}</i>"
    return line


def format_traffic_rollup(events: list[dict[str, Any]], *, ago_fn) -> str | None:
    """Collapse many traffic events into a short rollup block."""
    if len(events) < 4:
        return None

    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        meta = ev.get("meta") or {}
        kind = str(meta.get("pulse_event_type") or "other")
        by_kind[kind].append(ev)

    times = [float(e.get("ts_unix") or 0) for e in events if float(e.get("ts_unix") or 0) > 0]
    span = ""
    if times:
        span = f"{ago_fn(max(times))}–{ago_fn(min(times))}"

    lines = [f"📡 <b>Traffic pulse</b> · <b>{len(events)}</b> events" + (f" · <code>{html.escape(span)}</code>" if span else "")]

    def _top_labels(kind_events: list[dict[str, Any]], key: str, limit: int = 4) -> str:
        counts: dict[str, int] = defaultdict(int)
        for ev in kind_events:
            meta = ev.get("meta") or {}
            label = str(meta.get(key) or meta.get("scheduled_post_name") or meta.get("label") or "?").strip()
            label = re.sub(r"\s*·\s*[a-z0-9_]+\s*$", "", label, flags=re.IGNORECASE)
            counts[label[:48]] += 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:limit]
        return ", ".join(f"{html.escape(l)}×{n}" if n > 1 else html.escape(l) for l, n in top)

    if by_kind.get("post_ok"):
        n = len(by_kind["post_ok"])
        jobs = _top_labels(by_kind["post_ok"], "scheduled_post_name")
        lines.append(f"• <b>Scheduler posts</b> {n}× — {jobs}")
    if by_kind.get("affiliate_served"):
        n = len(by_kind["affiliate_served"])
        sponsors = _top_labels(by_kind["affiliate_served"], "label")
        lines.append(f"• <b>Affiliate rotations</b> {n}× — {sponsors}")
    if by_kind.get("beacon"):
        n = len(by_kind["beacon"])
        beacons = _top_labels(by_kind["beacon"], "link_label")
        lines.append(f"• <b>Click beacons</b> {n}× — {beacons}")
    for kind in ("post_fail", "start", "loot_roll", "other"):
        if by_kind.get(kind):
            lines.append(f"• <b>{html.escape(pulse_kind_human(kind))}</b> {len(by_kind[kind])}×")

    lines.append("<i>Details: /inbox traffic · instant: TBCC_TRAFFIC_PULSE_INSTANT</i>")
    return "\n".join(lines)


def format_system_compact_line(event: dict[str, Any], *, ago: str) -> str:
    title = str(event.get("title") or "").strip()
    if title.lower() == "secretary bot online":
        return f"⚙️ <b>Secretary restarted</b> · inbox ready · <code>{html.escape(ago)}</code>"
    icon = "⚙️"
    body = html.escape(str(event.get("body") or "")[:100])
    line = f"{icon} <b>{html.escape(title)}</b> · <code>{html.escape(ago)}</code>"
    if body:
        line += f" — <i>{body}</i>"
    return line
