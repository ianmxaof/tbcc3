"""Public anonymous sale announcements (Telegram network + Buffer X).

No buyer PII — only sale_kind + optional plan label. Triggered after every real
fulfillment via notify_sale_fulfilled → Celery task.
"""

from __future__ import annotations

import html
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import queue_post_scheduler
from app.services.payment_admin_notify import classify_sale_kind

logger = logging.getLogger(__name__)

SALE_ANNOUNCE_SCHED_NAME = "AOF — sale announce (auto)"
_COOLDOWN_FILE = "sale-announce-cooldown.json"


def sale_announce_enabled() -> bool:
    raw = (os.getenv("TBCC_SALE_ANNOUNCE_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def sale_announce_targets() -> set[str]:
    """network | buffer | main (main = main group only; network = all free network channels)."""
    raw = (os.getenv("TBCC_SALE_ANNOUNCE_TARGETS") or "network,buffer").strip().lower()
    parts = {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}
    return parts or {"network", "buffer"}


def sale_announce_min_interval_s() -> int:
    raw = (os.getenv("TBCC_SALE_ANNOUNCE_MIN_INTERVAL_S") or "45").strip()
    try:
        return max(0, min(3600, int(raw)))
    except ValueError:
        return 45


def sale_announce_buffer_mode() -> str:
    raw = (os.getenv("TBCC_SALE_ANNOUNCE_BUFFER_MODE") or "addToQueue").strip()
    if raw in ("shareNow", "now", "share"):
        return "shareNow"
    return "addToQueue"


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cooldown_path() -> Path:
    return _tbcc_root() / ".tbcc-run" / _COOLDOWN_FILE


def _throttle_ok(sale_kind: str) -> bool:
    interval = sale_announce_min_interval_s()
    if interval <= 0:
        return True
    path = _cooldown_path()
    now = time.time()
    data: dict[str, float] = {}
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
    except Exception:
        data = {}
    last = float(data.get(sale_kind) or data.get("_any") or 0)
    if now - last < interval:
        return False
    data[sale_kind] = now
    data["_any"] = now
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.debug("sale announce cooldown write failed: %s", e)
    return True


def _loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def _payment_bot_username() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def build_sale_announce_html(
    *,
    sale_kind: str,
    plan_name: str | None = None,
    payment_method: str | None = None,
) -> str:
    """Anonymous FOMO copy — never include telegram_user_id."""
    loot = _loot_bot_username()
    pay = _payment_bot_username()
    kind = (sale_kind or "subscription").strip().lower()
    pm = (payment_method or "").strip().lower()
    via = ""
    if pm in ("stars", "telegram_stars"):
        via = " via ⭐"
    elif pm in ("nowpayments", "crypto", "webhook"):
        via = " via crypto"

    if kind == "loot_key":
        return (
            f"🔑 <b>Loot Room key sold{html.escape(via)}.</b>\n\n"
            "Someone just unlocked 24h access — real purchase, not a tease.\n"
            f"Grab yours: <a href=\"https://t.me/{html.escape(pay)}?start=loot\">@{html.escape(pay)}</a> · "
            f"play <a href=\"https://t.me/{html.escape(loot)}?start=loot_free\">@{html.escape(loot)}</a>"
        )
    if kind == "pack":
        label = html.escape((plan_name or "Pack").strip()[:80])
        return (
            f"📦 <b>Pack sold{html.escape(via)}.</b>\n\n"
            f"{label} just moved — real checkout.\n"
            f"Shop: <a href=\"https://t.me/{html.escape(pay)}\">@{html.escape(pay)}</a>"
        )
    # subscription / VIP
    return (
        f"⭐ <b>Subscription sold{html.escape(via)}.</b>\n\n"
        "Someone just paid for access — real money, real seat.\n"
        f"Join: <a href=\"https://t.me/{html.escape(pay)}\">@{html.escape(pay)}</a>"
    )


def build_sale_announce_plain(
    *,
    sale_kind: str,
    plan_name: str | None = None,
    payment_method: str | None = None,
) -> str:
    from app.services.telegram_html_plain import telegram_html_to_plain

    return telegram_html_to_plain(
        build_sale_announce_html(
            sale_kind=sale_kind, plan_name=plan_name, payment_method=payment_method
        ),
        max_len=400,
    )


def _upsert_one_shot(
    db: Session,
    *,
    channel_id: int,
    content: str,
    name: str = SALE_ANNOUNCE_SCHED_NAME,
) -> ScheduledTextPost:
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == channel_id, ScheduledTextPost.name == name)
        .first()
    )
    now = datetime.now(timezone.utc)
    if not sched:
        sched = ScheduledTextPost(
            name=name,
            channel_id=channel_id,
            content=content,
            send_silent=False,
            pin_after_send=False,
            created_at=now,
            scheduler_category="promo_bulletin",
        )
        db.add(sched)
        db.flush()
    else:
        sched.content = content
        sched.sent_at = None
        sched.interval_minutes = None
        sched.posting_auto_paused_at = None
        sched.posting_auto_pause_reason = None
        sched.send_failure_streak = 0
    return sched


def announce_sale_to_telegram_network(
    db: Session,
    *,
    html_body: str,
    main_only: bool = False,
) -> dict[str, Any]:
    """Queue one-shot sale posts across network channels (or main group only)."""
    queued: list[dict[str, Any]] = []
    stagger_raw = (os.getenv("TBCC_SALE_ANNOUNCE_STAGGER_S") or "8").strip()
    try:
        stagger = max(0, min(120, int(stagger_raw)))
    except ValueError:
        stagger = 8

    channels: list[tuple[str, Channel]] = []
    if main_only:
        ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
        if ch:
            channels.append(("main", ch))
    else:
        for net_ch in AOF_NETWORK_CHANNELS:
            if net_ch.key == "packs":
                continue
            ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
            if ch:
                channels.append((net_ch.key, ch))

    for i, (key, ch) in enumerate(channels):
        sched = _upsert_one_shot(db, channel_id=int(ch.id), content=html_body)
        db.flush()
        queued.append(
            {
                **queue_post_scheduler(int(sched.id), countdown=i * stagger),
                "key": key,
                "channel_id": ch.id,
                "post_id": sched.id,
            }
        )
    db.commit()
    return {"ok": True, "queued": queued, "count": len(queued)}


def announce_sale_to_buffer(*, plain: str) -> dict[str, Any]:
    from app.services.buffer_graphql import (
        buffer_api_key,
        buffer_target_channel_ids,
        create_posts_multi_channel,
    )
    from app.services.buffer_post_result import buffer_create_post_succeeded
    from app.services.buffer_x_caption import finalize_buffer_x_caption, should_fit_for_x

    if not buffer_api_key():
        return {"ok": False, "skipped": True, "reason": "no_buffer_api_key"}
    # Sale FOMO is X-first; skip IG/etc. that require media for text-only posts.
    chans = buffer_target_channel_ids(x_primary_only=True)
    if not chans:
        chans = buffer_target_channel_ids()
    if not chans:
        return {"ok": False, "skipped": True, "reason": "no_buffer_channels"}

    text = plain
    if should_fit_for_x():
        try:
            text = finalize_buffer_x_caption(plain, db=None, overflow_url=None, advance_link_cycle=False)
        except Exception:
            text = plain[:280]

    mode = sale_announce_buffer_mode()
    results = create_posts_multi_channel(text, channel_ids=chans, mode=mode)  # type: ignore[arg-type]
    ok_any = any(buffer_create_post_succeeded(r) for r in (results or []))
    return {"ok": ok_any, "mode": mode, "channels": len(chans), "results": results}


def run_public_sale_announce(
    db: Session,
    *,
    sale_kind: str,
    plan_name: str | None = None,
    payment_method: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not sale_announce_enabled() and not force:
        return {"ok": False, "skipped": True, "reason": "disabled"}
    kind = (sale_kind or "subscription").strip().lower()
    if not force and not _throttle_ok(kind):
        return {"ok": False, "skipped": True, "reason": "throttled", "sale_kind": kind}

    targets = sale_announce_targets()
    html_body = build_sale_announce_html(
        sale_kind=kind, plan_name=plan_name, payment_method=payment_method
    )
    plain = build_sale_announce_plain(
        sale_kind=kind, plan_name=plan_name, payment_method=payment_method
    )
    out: dict[str, Any] = {"ok": True, "sale_kind": kind, "targets": sorted(targets)}

    if "network" in targets:
        out["telegram_network"] = announce_sale_to_telegram_network(db, html_body=html_body, main_only=False)
    elif "main" in targets:
        out["telegram_network"] = announce_sale_to_telegram_network(db, html_body=html_body, main_only=True)

    if "buffer" in targets:
        try:
            out["buffer"] = announce_sale_to_buffer(plain=plain)
        except Exception as e:
            logger.exception("sale announce buffer failed")
            out["buffer"] = {"ok": False, "error": str(e)[:300]}

    return out


def queue_public_sale_announce(
    *,
    product_type: str | None,
    bot_section: str | None,
    plan_name: str | None,
    payment_method: str | None,
) -> dict[str, Any]:
    """Fire-and-forget from payment path (does not block fulfillment)."""
    if not sale_announce_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled"}
    sale_kind = classify_sale_kind(
        product_type=product_type,
        bot_section=bot_section,
        plan_name=plan_name,
    )
    try:
        from app.workers.sale_announce_worker import announce_public_sale

        announce_public_sale.delay(
            sale_kind,
            (plan_name or "")[:120],
            (payment_method or "")[:40],
        )
        return {"ok": True, "queued": True, "sale_kind": sale_kind}
    except Exception as e:
        logger.warning("queue_public_sale_announce failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
