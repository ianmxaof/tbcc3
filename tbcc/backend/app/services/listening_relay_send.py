"""Send listening-relay copy follow-ups (media, buttons, <pre> text)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from telethon import TelegramClient

from app.models.media import Media
from app.models.subscription_plan import SubscriptionPlan
from app.services.listening_relay_format import ensure_relay_pre_block
from app.services.listening_relay_slot import normalize_slot_extra
from app.services.scheduled_post_service import (
    _apply_order_mode_to_sequence,
    _build_reply_markup,
    _checkout_deep_link_payload,
    _execute_telegram_scheduled_send,
)
from app.utils.telegram_peer import normalize_telethon_peer_identifier

logger = logging.getLogger(__name__)


@dataclass
class RelayCopyFollowup:
    html: str = ""
    buttons: list[dict] = field(default_factory=list)
    media_ids: list[int] = field(default_factory=list)
    attachment_urls: list[str] = field(default_factory=list)
    album_order_mode: str = "static"
    pin_after_send: bool = False
    checkout_stars_enabled: bool = False
    checkout_stars_plan_id: int | None = None
    checkout_button_label: str | None = None
    checkout_referral_code: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "html": self.html,
            "buttons": self.buttons,
            "media_ids": self.media_ids,
            "attachment_urls": self.attachment_urls,
            "album_order_mode": self.album_order_mode,
            "pin_after_send": self.pin_after_send,
            "checkout_stars_enabled": self.checkout_stars_enabled,
            "checkout_stars_plan_id": self.checkout_stars_plan_id,
            "checkout_button_label": self.checkout_button_label,
            "checkout_referral_code": self.checkout_referral_code,
        }

    @staticmethod
    def from_slot_extra(extra: dict[str, Any], copy_html: str) -> RelayCopyFollowup:
        ex = normalize_slot_extra(extra)
        return RelayCopyFollowup(
            html=ensure_relay_pre_block(copy_html) if copy_html else "",
            buttons=list(ex.get("copy_buttons") or []),
            media_ids=list(ex.get("copy_media_ids") or []),
            attachment_urls=list(ex.get("copy_attachment_urls") or []),
            album_order_mode=str(ex.get("copy_album_order_mode") or "static"),
            pin_after_send=bool(ex.get("copy_pin_after_send")),
            checkout_stars_enabled=bool(ex.get("copy_checkout_stars_enabled")),
            checkout_stars_plan_id=ex.get("copy_checkout_stars_plan_id"),
            checkout_button_label=ex.get("copy_checkout_button_label"),
            checkout_referral_code=ex.get("copy_checkout_referral_code"),
        )

    @staticmethod
    def from_json_dict(raw: dict[str, Any]) -> RelayCopyFollowup:
        html = str(raw.get("html") or "")
        if html and "<pre" not in html.lower():
            html = ensure_relay_pre_block(html)
        return RelayCopyFollowup(
            html=html,
            buttons=[b for x in (raw.get("buttons") or []) if (b := _valid_btn(x))],
            media_ids=_int_list(raw.get("media_ids")),
            attachment_urls=[str(u).strip() for u in (raw.get("attachment_urls") or []) if str(u).strip()][:10],
            album_order_mode=str(raw.get("album_order_mode") or "static"),
            pin_after_send=bool(raw.get("pin_after_send")),
            checkout_stars_enabled=bool(raw.get("checkout_stars_enabled")),
            checkout_stars_plan_id=_optional_int(raw.get("checkout_stars_plan_id")),
            checkout_button_label=raw.get("checkout_button_label"),
            checkout_referral_code=raw.get("checkout_referral_code"),
        )


def _valid_btn(x: Any) -> dict | None:
    if not isinstance(x, dict):
        return None
    t = str(x.get("text") or "").strip()
    u = str(x.get("url") or "").strip()
    return {"text": t, "url": u} if t and u else None


def _int_list(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out[:10]


def _optional_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def followups_to_json(followups: list[RelayCopyFollowup]) -> str | None:
    if not followups:
        return None
    return json.dumps([f.to_json_dict() for f in followups])


def followups_from_json(raw: str | None) -> list[RelayCopyFollowup]:
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(arr, list):
        return []
    return [RelayCopyFollowup.from_json_dict(x) for x in arr if isinstance(x, dict)]


def _merge_copy_checkout_buttons(followup: RelayCopyFollowup, db: Session) -> list[dict]:
    base = list(followup.buttons)
    if not followup.checkout_stars_enabled or not followup.checkout_stars_plan_id:
        return base
    bot = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
    if not bot:
        return base
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(followup.checkout_stars_plan_id)).first()
    if not plan or plan.is_active is False or int(plan.price_stars or 0) <= 0:
        return base
    payload = _checkout_deep_link_payload(int(followup.checkout_stars_plan_id), followup.checkout_referral_code)
    if not payload:
        return base
    url = f"https://t.me/{bot}?start={payload}"
    label = (followup.checkout_button_label or "").strip()
    if not label:
        stars = int(plan.price_stars or 0)
        name = (plan.name or "Subscribe").strip()[:36]
        label = f"{name} — {stars}⭐"
    if len(label) > 64:
        label = label[:63] + "…"
    return base + [{"text": label, "url": url}]


class _RelayMediaOrderPost:
    """Minimal shim for _apply_order_mode_to_sequence carousel index."""

    def __init__(self, mode: str):
        self.album_order_mode = mode
        self.album_carousel_index = 0


def _load_copy_media(db: Session, mids: list[int], order_mode: str) -> list[Media]:
    items: list[Media] = []
    for mid in mids:
        m = db.query(Media).filter(Media.id == int(mid)).first()
        if m:
            items.append(m)
    return _apply_order_mode_to_sequence(items, order_mode, _RelayMediaOrderPost(order_mode))


async def send_relay_copy_followups(
    client: TelegramClient,
    channel_identifier: str | Any,
    *,
    reply_anchor: int | None,
    followups: list[RelayCopyFollowup],
    db: Session,
    send_silent: bool = True,
) -> None:
    if not followups:
        return
    if isinstance(channel_identifier, str):
        peer = normalize_telethon_peer_identifier(channel_identifier)
    else:
        # Caller may pass a Telethon entity already resolved (e.g. poster_worker).
        peer = channel_identifier
    silent_kw = {"silent": True} if send_silent else {}
    anchor = reply_anchor
    for fu in followups:
        if not (fu.html or "").strip() and not fu.media_ids and not fu.attachment_urls:
            continue
        merged = _merge_copy_checkout_buttons(fu, db)
        reply_markup = _build_reply_markup(merged)
        media_items = _load_copy_media(db, fu.media_ids, fu.album_order_mode)
        promo_urls = list(fu.attachment_urls)
        if fu.album_order_mode == "shuffle":
            import random

            random.shuffle(promo_urls)
        caption = (fu.html or "").strip() or " "
        try:
            sent = await _execute_telegram_scheduled_send(
                client,
                peer,
                caption=caption,
                media_items=media_items,
                promo_ordered=promo_urls if not media_items else [],
                reply_markup=reply_markup,
                silent_kw=silent_kw,
                reply_to=anchor,
            )
            if fu.pin_after_send and sent:
                msg = sent[0] if isinstance(sent, list) else sent
                if msg:
                    try:
                        await client.pin_message(peer, msg, notify=False)
                    except Exception as e:
                        logger.warning("relay copy pin_after_send failed: %s", e)
            new_id = None
            if sent:
                msg = sent[0] if isinstance(sent, list) else sent
                new_id = getattr(msg, "id", None)
            if new_id:
                anchor = new_id
        except Exception:
            logger.exception("send_relay_copy_followup failed")
            raise
