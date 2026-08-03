"""Traffic Pulse — real-time operator visibility for network traffic (inbox + optional DM)."""

from __future__ import annotations

import html
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_DIGEST_COUNTS = "tbcc:traffic_pulse:digest:counts"
REDIS_DIGEST_REFS = "tbcc:traffic_pulse:digest:refs"
REDIS_INSTANT_HOUR_KEY = "tbcc:traffic_pulse:instant:hour"
REDIS_INSTANT_HOUR_BUCKET = "tbcc:traffic_pulse:instant:bucket"

_INSTANT_HOUR_COUNT: int = 0
_INSTANT_HOUR_START: float = 0.0


def traffic_pulse_enabled() -> bool:
    return (os.getenv("TBCC_TRAFFIC_PULSE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def traffic_pulse_instant_types() -> set[str]:
    raw = (os.getenv("TBCC_TRAFFIC_PULSE_INSTANT") or "beacon,start,post_fail").strip().lower()
    if raw in ("0", "false", "no", "off", "none"):
        return set()
    return {s.strip() for s in raw.split(",") if s.strip()}


def traffic_pulse_instant_hourly_cap() -> int:
    raw = (os.getenv("TBCC_TRAFFIC_PULSE_INSTANT_HOURLY_CAP") or "20").strip()
    try:
        return max(1, min(500, int(raw)))
    except ValueError:
        return 20


def traffic_pulse_digest_minutes() -> int:
    raw = (os.getenv("TBCC_TRAFFIC_PULSE_DIGEST_MIN") or "15").strip()
    try:
        return max(5, min(120, int(raw)))
    except ValueError:
        return 15


def _redis():
    from app.services.admin_inbox import _redis_client

    return _redis_client()


def _increment_digest(event_type: str, source_ref: str | None = None) -> None:
    try:
        r = _redis()
        r.hincrby(REDIS_DIGEST_COUNTS, event_type, 1)
        if source_ref:
            r.hincrby(REDIS_DIGEST_REFS, source_ref[:64], 1)
    except Exception:
        logger.debug("traffic pulse digest increment failed", exc_info=True)


def _instant_cap_allows() -> bool:
    global _INSTANT_HOUR_COUNT, _INSTANT_HOUR_START
    cap = traffic_pulse_instant_hourly_cap()
    now = time.time()
    try:
        r = _redis()
        bucket = int(r.get(REDIS_INSTANT_HOUR_BUCKET) or 0)
        if bucket and now - bucket >= 3600:
            r.set(REDIS_INSTANT_HOUR_KEY, 0)
            r.set(REDIS_INSTANT_HOUR_BUCKET, int(now))
            _INSTANT_HOUR_COUNT = 0
            _INSTANT_HOUR_START = now
        count = int(r.get(REDIS_INSTANT_HOUR_KEY) or 0)
        if count >= cap:
            return False
        r.incr(REDIS_INSTANT_HOUR_KEY)
        if not bucket:
            r.set(REDIS_INSTANT_HOUR_BUCKET, int(now))
        return True
    except Exception:
        if now - _INSTANT_HOUR_START >= 3600:
            _INSTANT_HOUR_START = now
            _INSTANT_HOUR_COUNT = 0
        if _INSTANT_HOUR_COUNT >= cap:
            return False
        _INSTANT_HOUR_COUNT += 1
        return True


def push_traffic_pulse(
    event_type: str,
    *,
    title: str,
    body: str = "",
    meta: dict[str, Any] | None = None,
    force_instant: bool = False,
) -> None:
    if not traffic_pulse_enabled():
        return
    et = (event_type or "").strip().lower()
    meta = dict(meta or {})
    meta["pulse_event_type"] = et

    want_instant = force_instant or et in traffic_pulse_instant_types()
    instant = False
    if want_instant and _instant_cap_allows():
        instant = True
    else:
        _increment_digest(et, meta.get("source_ref"))

    try:
        from app.services.admin_inbox import push_admin_inbox_event

        push_admin_inbox_event(
            category="traffic",
            severity="info",
            title=title,
            body=body,
            meta=meta,
            instant=instant,
        )
    except Exception:
        logger.debug("traffic pulse inbox push failed", exc_info=True)


def pulse_beacon_hit(link_label: str, slug: str, source_ref: str | None, hit_count: int, **extra: Any) -> None:
    from app.services.traffic_beacon_notify import format_traffic_beacon_body_html
    from app.services.traffic_inbox_copy import format_traffic_detail, format_traffic_title

    meta = {
        "slug": slug,
        "source_ref": source_ref,
        "hit_count": hit_count,
        "link_label": link_label,
        **{k: v for k, v in extra.items() if v is not None},
    }
    if not meta.get("placement"):
        from app.services.traffic_beacon_notify import parse_beacon_placement

        meta["placement"] = parse_beacon_placement(label=link_label, slug=slug)
    meta["pulse_event_type"] = "beacon"
    body = format_traffic_detail(meta) or format_traffic_beacon_body_html(meta)
    push_traffic_pulse(
        "beacon",
        title=format_traffic_title(meta, fallback=f"Click beacon · {link_label}"),
        body=body,
        meta=meta,
    )
    try:
        from app.services.undress_surge import on_beacon_hit_for_surge

        on_beacon_hit_for_surge(
            source_ref=source_ref,
            slug=slug,
            link_label=link_label,
        )
    except Exception:
        logger.debug("undress surge beacon hook failed", exc_info=True)


def pulse_bot_start(telegram_user_id: int, source_ref: str, payload: str, touch_count: int) -> None:
    from app.services.traffic_inbox_copy import format_traffic_detail, format_traffic_title

    meta = {
        "telegram_user_id": telegram_user_id,
        "source_ref": source_ref,
        "payload": payload,
        "touch_count": touch_count,
        "pulse_event_type": "start",
    }
    push_traffic_pulse(
        "start",
        title=format_traffic_title(meta, fallback=f"Bot start · {source_ref}"),
        body=format_traffic_detail(meta),
        meta=meta,
    )


def pulse_post_outbound(
    *,
    ok: bool,
    event_type: str,
    channel_id: int | None,
    scheduled_post_id: int | None,
    error_message: str | None = None,
    pool_id: int | None = None,
) -> None:
    from app.services.traffic_inbox_copy import enrich_post_pulse_meta, format_traffic_detail, format_traffic_title

    et = "post_fail" if not ok else "post_ok"
    meta = {
        "ok": ok,
        "event_type": event_type,
        "outbound_event_type": event_type,
        "channel_id": channel_id,
        "scheduled_post_id": scheduled_post_id,
        "pool_id": pool_id,
        "pulse_event_type": et,
    }
    if error_message:
        meta["error_message"] = error_message[:200]
    meta.update(
        enrich_post_pulse_meta(
            scheduled_post_id=scheduled_post_id,
            channel_id=channel_id,
            event_type=event_type,
            pool_id=pool_id,
        )
    )
    title = format_traffic_title(meta, fallback="Channel post failed" if not ok else "Channel post sent")
    body = format_traffic_detail(meta)
    push_traffic_pulse(
        et,
        title=title,
        body=body,
        meta=meta,
        force_instant=not ok,
    )


def pulse_loot_roll(
    *,
    roll_kind: str | None,
    tier: int,
    media_sent: int,
    chat_id: int,
) -> None:
    from app.services.traffic_inbox_copy import format_traffic_detail, format_traffic_title

    meta = {
        "roll_kind": roll_kind,
        "tier": tier,
        "media_sent": media_sent,
        "chat_id": chat_id,
        "pulse_event_type": "loot_roll",
    }
    push_traffic_pulse(
        "loot_roll",
        title=format_traffic_title(meta, fallback=f"Loot roll · {roll_kind or 'roll'}"),
        body=format_traffic_detail(meta),
        meta=meta,
    )


def pulse_affiliate_served(
    *,
    placement: str,
    label: str,
    url: str,
    source_ref: str | None = None,
) -> None:
    from app.services.traffic_inbox_copy import format_traffic_detail, format_traffic_title

    slug = None
    if "/r/" in url:
        slug = url.rsplit("/r/", 1)[-1].split("?")[0].strip() or None
    meta = {
        "placement": placement,
        "label": label,
        "url": url,
        "source_ref": source_ref,
        "slug": slug,
        "pulse_event_type": "affiliate_served",
    }
    push_traffic_pulse(
        "affiliate_served",
        title=format_traffic_title(meta, fallback=f"Affiliate · {label}"),
        body=format_traffic_detail(meta),
        meta=meta,
    )
    try:
        from app.services.undress_surge import on_affiliate_served_for_surge

        on_affiliate_served_for_surge(source_ref=source_ref, label=label, url=url)
    except Exception:
        logger.debug("undress surge affiliate hook failed", exc_info=True)


def build_digest_telegram_html() -> str | None:
    try:
        r = _redis()
        counts = r.hgetall(REDIS_DIGEST_COUNTS) or {}
        refs = r.hgetall(REDIS_DIGEST_REFS) or {}
    except Exception:
        return None
    if not counts:
        return None

    lines = ["📡 <b>Traffic Pulse digest</b>"]
    for key, val in sorted(counts.items(), key=lambda x: -int(x[1] or 0)):
        k = html.escape(str(key))
        lines.append(f"• {k}: {int(val or 0)}")
    if refs:
        top = sorted(refs.items(), key=lambda x: -int(x[1] or 0))[:8]
        lines.append("")
        lines.append("<b>Top source_ref</b>")
        for ref, val in top:
            lines.append(f"• <code>{html.escape(str(ref))}</code>: {int(val or 0)}")
    lines.append("")
    lines.append("<i>/inbox · tune TBCC_TRAFFIC_PULSE_INSTANT</i>")
    return "\n".join(lines)


def clear_digest_buffer() -> None:
    try:
        r = _redis()
        r.delete(REDIS_DIGEST_COUNTS, REDIS_DIGEST_REFS)
    except Exception:
        pass


def send_traffic_pulse_digest() -> dict[str, Any]:
    text = build_digest_telegram_html()
    if not text:
        return {"ok": True, "skipped": True, "reason": "empty"}
    try:
        from app.services.admin_inbox import _telegram_send_html

        _telegram_send_html(text)
        clear_digest_buffer()
        return {"ok": True, "sent": True}
    except Exception as e:
        logger.warning("traffic pulse digest send failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
