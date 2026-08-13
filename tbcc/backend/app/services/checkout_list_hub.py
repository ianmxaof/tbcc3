"""The Checkout List (@thecheckoutlist) — SFW affiliate bulletin + scheduler sync."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.affiliate_content_lane import _hostname
from app.services.promo_affiliate_rotation import build_sponsor_link_html, list_candidates

logger = logging.getLogger(__name__)

CHECKOUT_LIST_CHANNEL_IDENT_DEFAULT = "-1004361597444"
CHECKOUT_LIST_INVITE_DEFAULT = "https://t.me/thecheckoutlist"
CHECKOUT_LIST_DISPLAY_NAME = "The Checkout List"
CHECKOUT_LIST_BULLETIN_SCHED_NAME = "CHECKOUT LIST — deals board (pinned)"

_CATEGORY_ORDER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("💳", "FINANCE", ("cloudfarm", "cloud farm", "chime.com", "revolut.com")),
    ("🛠", "DEV & PRODUCTIVITY", ("cursor.com", "claude.ai", "anthropic.com", "proton.", "pr.tn", "cometapi.com")),
    ("🛍", "SHOPPING", ("rakuten.com", "amazon.", "flipkart.com", "dealscrown.com")),
    ("📦", "INFRA & MISC", ("pulsedmedia.com", "rewards.bing.com", "cloudflare.com", "hetzner.com")),
)


def checkout_list_channel_ident() -> str:
    raw = (os.getenv("TBCC_CHECKOUT_LIST_CHANNEL_IDENT") or CHECKOUT_LIST_CHANNEL_IDENT_DEFAULT).strip()
    return raw or CHECKOUT_LIST_CHANNEL_IDENT_DEFAULT


def checkout_list_invite() -> str:
    return (os.getenv("TBCC_CHECKOUT_LIST_INVITE") or CHECKOUT_LIST_INVITE_DEFAULT).strip()


def checkout_list_enabled() -> bool:
    raw = (os.getenv("TBCC_CHECKOUT_LIST_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _category_for_row(row) -> tuple[str, str]:
    host = _hostname(getattr(row, "url", "") or "")
    label = (getattr(row, "label", "") or "").lower()
    for emoji, title, hints in _CATEGORY_ORDER:
        for hint in hints:
            if hint in host or hint in label:
                return emoji, title
    return "🔗", "MORE DEALS"


def build_checkout_list_bulletin(db: Session) -> str:
    """Pinned SFW deals board for @thecheckoutlist."""
    rows = list_candidates(db, "links_hub_sfw")
    invite = checkout_list_invite()
    lines = [
        "🛒 <b>THE CHECKOUT LIST</b> — live board",
        "Curated referral links · SFW only",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if not rows:
        lines.extend(
            [
                "",
                "Links appear here as they are added via admin intake.",
                f"Channel: <a href=\"{invite}\">@thecheckoutlist</a>",
                "",
                "Suggest a deal: @aof_secretary_bot",
            ]
        )
        return "\n".join(lines)

    buckets: dict[str, list] = {}
    order: list[str] = []
    for row in rows:
        emoji, title = _category_for_row(row)
        key = f"{emoji} {title}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)

    for key in order:
        emoji, title = key.split(" ", 1)
        lines.append("")
        lines.append(f"{emoji} <b>{title}</b>")
        for row in buckets[key]:
            lines.append(f"→ {build_sponsor_link_html(row, placement='links_hub_sfw')}")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "Affiliate disclosure: we may earn a commission on some links.",
            f"<a href=\"{invite}\">@thecheckoutlist</a> · tips: @aof_secretary_bot",
        ]
    )
    return "\n".join(lines)


def _ensure_channel_row(db: Session) -> Channel | None:
    ident = checkout_list_channel_ident()
    row = db.query(Channel).filter(Channel.identifier == ident).first()
    invite = checkout_list_invite()
    if row:
        if row.name != CHECKOUT_LIST_DISPLAY_NAME:
            row.name = CHECKOUT_LIST_DISPLAY_NAME
        if (row.invite_link or "").strip() != invite:
            row.invite_link = invite
        return row
    row = Channel(name=CHECKOUT_LIST_DISPLAY_NAME, identifier=ident, invite_link=invite)
    db.add(row)
    db.flush()
    return row


def sync_checkout_list_hub(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Ensure Checkout List channel row + pinned bulletin scheduler content."""
    if not checkout_list_enabled():
        return {"ok": True, "status": "disabled"}

    bulletin = build_checkout_list_bulletin(db)
    entry: dict[str, Any] = {
        "channel_ident": checkout_list_channel_ident(),
        "bulletin_chars": len(bulletin),
        "links_sfw": len(list_candidates(db, "links_hub_sfw")),
    }

    if not execute:
        entry["status"] = "would_update"
        entry["bulletin_preview"] = bulletin[:800]
        return entry

    ch = _ensure_channel_row(db)
    if not ch:
        entry["status"] = "channel_missing"
        return entry
    entry["channel_id"] = ch.id

    sched = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == ch.id,
            ScheduledTextPost.name == CHECKOUT_LIST_BULLETIN_SCHED_NAME,
        )
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=CHECKOUT_LIST_BULLETIN_SCHED_NAME,
            channel_id=ch.id,
            content=bulletin,
            interval_minutes=1440,
            send_silent=True,
            pin_after_send=True,
            created_at=datetime.now(timezone.utc),
            last_posted_at=datetime.now(timezone.utc),
        )
        from app.services.scheduler_category import apply_scheduler_category

        apply_scheduler_category(sched, "promo_bulletin")
        db.add(sched)
        db.flush()
        entry["status"] = "created"
    else:
        sched.content = bulletin
        sched.pin_after_send = True
        sched.interval_minutes = sched.interval_minutes or 1440
        if sched.last_posted_at is None:
            sched.last_posted_at = datetime.now(timezone.utc)
        entry["status"] = "updated"

    entry["scheduler_id"] = sched.id
    entry["ok"] = True
    return entry


def queue_checkout_list_bulletin_post(db: Session) -> dict[str, Any]:
    """Queue immediate Telegram send for the deals board (requires Celery post lane)."""
    sync = sync_checkout_list_hub(db, execute=True)
    sched_id = sync.get("scheduler_id")
    if not sched_id:
        return {"ok": False, "reason": sync.get("status", "no_scheduler")}
    from app.services.aof_growth_hub import queue_post_scheduler

    queued = queue_post_scheduler(int(sched_id), countdown=0)
    return {"ok": bool(queued.get("ok")), "sync": sync, "queue": queued}
