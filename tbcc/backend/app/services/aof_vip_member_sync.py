"""Sync native AOF VIP Stars subscription joins into TBCC subscriptions."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from telegram import ChatMemberUpdated, Update

from app.services.aof_vip_checkout import vip_channel_ident, vip_subscription_invite_url

logger = logging.getLogger(__name__)


def _chat_id_matches_vip(chat_id: int) -> bool:
    ident = vip_channel_ident()
    if not ident:
        return False
    try:
        want = int(ident)
    except ValueError:
        return False
    # Telegram Bot API uses -100… for channels; accept either form.
    cid = int(chat_id)
    if cid == want:
        return True
    if want < 0 and cid > 0:
        return str(want).endswith(str(cid))
    return False


def _member_joined(member_update: ChatMemberUpdated) -> bool:
    old = member_update.old_chat_member
    new = member_update.new_chat_member
    if not old or not new:
        return False
    return old.status in ("left", "kicked", "restricted") and new.status == "member"


def _subscription_charge_id(member_update: ChatMemberUpdated, user_id: int) -> str:
    invite = member_update.invite_link
    until = getattr(member_update.new_chat_member, "until_date", None)
    if until:
        return f"vip_native_{user_id}_{int(until)}"
    if invite and getattr(invite, "invite_link", None):
        digest = hashlib.sha1(str(invite.invite_link).encode()).hexdigest()[:16]
        return f"vip_native_{user_id}_{digest}"
    return f"vip_native_{user_id}_{int(datetime.now(timezone.utc).timestamp()) // 86400}"


def _is_stars_subscription_join(member_update: ChatMemberUpdated) -> bool:
    invite = member_update.invite_link
    if not invite:
        return False
    price = getattr(invite, "subscription_price", None)
    if price and int(price) > 0:
        return True
    sub_url = vip_subscription_invite_url()
    link = (getattr(invite, "invite_link", None) or "").strip()
    return bool(sub_url and link and link == sub_url)


async def handle_vip_chat_member_update(update: Update, context) -> None:
    """Record paid VIP channel joins (Stars subscription invite links)."""
    cm = update.chat_member
    if not cm or not cm.new_chat_member or not cm.new_chat_member.user:
        return
    if not _chat_id_matches_vip(cm.chat.id):
        return
    if not _member_joined(cm):
        return
    if not _is_stars_subscription_join(cm):
        logger.debug("vip chat_member: join without Stars subscription invite — skip sync")
        return

    user_id = int(cm.new_chat_member.user.id)
    charge_id = _subscription_charge_id(cm, user_id)

    import httpx
    import os

    from app.database.session import SessionLocal
    from app.services.aof_growth_hub import resolve_group_access_plan_id

    db = SessionLocal()
    try:
        plan_id = resolve_group_access_plan_id(db)
    finally:
        db.close()

    api_base = (os.getenv("TBCC_API_URL") or "http://localhost:8000").rstrip("/")
    payload = {
        "telegram_user_id": user_id,
        "plan_id": plan_id,
        "payment_method": "vip_star_subscription",
        "telegram_payment_charge_id": charge_id,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            internal_key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
            if internal_key:
                headers["X-TBCC-Internal-Key"] = internal_key
            r = await client.post(f"{api_base}/subscriptions/", json=payload, headers=headers)
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        logger.warning("vip chat_member: subscription sync failed user=%s err=%s", user_id, e)
        return

    if result and not result.get("error"):
        logger.info(
            "vip chat_member: synced subscription user=%s plan=%s charge=%s replay=%s",
            user_id,
            plan_id,
            charge_id,
            result.get("fulfillment_replay"),
        )
        try:
            from app.services.aof_vip_fulfillment import vip_primary_invite_url, vip_welcome_message_html

            await context.bot.send_message(
                chat_id=user_id,
                text=vip_welcome_message_html(invite_link=vip_primary_invite_url()),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
        except Exception:
            pass
    else:
        logger.warning("vip chat_member: subscription sync failed user=%s err=%s", user_id, result)
