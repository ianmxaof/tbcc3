"""
Companion bot onboarding: LV gate + AOF network membership + per-user generation credits.

Membership uses Bot API getChatMember (bot must be admin in AOF channels).
Operator undress API balance is only spent when user has trial/credits remaining.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from app.data.aof_manual_gate_links import manual_gate_url
from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT, ADDLIST_RAW, MAIN_GROUP_INVITE

logger = logging.getLogger(__name__)

_ACCESS_TTL_SEC = 60 * 60 * 24 * 90  # 90 days
_MEM: dict[int, dict[str, Any]] = {}

_MEMBER_STATUSES = frozenset(
    {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    }
)


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("companion_access: redis unavailable: %s", e)
        return None


def _key(user_id: int) -> str:
    return f"tbcc:companion:access:{user_id}"


def gate_enabled() -> bool:
    raw = (os.getenv("TBCC_COMPANION_GATE_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def gate_lv_url() -> str:
    explicit = (os.getenv("TBCC_COMPANION_GATE_LV_URL") or "").strip()
    if explicit:
        return explicit
    return manual_gate_url("main_group") or manual_gate_url("addlist") or ""


def affiliate_undress_url() -> str:
    return (
        (os.getenv("TBCC_COMPANION_AFFILIATE_UNDRESS_URL") or "").strip()
        or (os.getenv("TBCC_AFFILIATE_UNDRESS_URL") or "").strip()
    )


def free_trial_photos() -> int:
    raw = (os.getenv("TBCC_COMPANION_FREE_TRIAL_PHOTOS") or "1").strip()
    try:
        return max(0, min(5, int(raw)))
    except ValueError:
        return 1


def vip_skip_gate_for_subscribers() -> bool:
    from app.services.aof_vip_perks import vip_companion_skip_gate

    return vip_companion_skip_gate()


def refresh_vip_subscriber_flag(user_id: int) -> CompanionAccess:
    """Sync Redis companion access with active AOF VIP subscription row."""
    acc = get_access(user_id)
    try:
        from app.database.session import SessionLocal
        from app.services.subscription_access import is_aof_vip_subscriber

        db = SessionLocal()
        try:
            acc.vip_subscriber = is_aof_vip_subscriber(db, int(user_id))
        finally:
            db.close()
    except Exception as e:
        logger.debug("refresh_vip_subscriber_flag uid=%s: %s", user_id, e)
    save_access(acc)
    return acc


def admin_telegram_ids() -> frozenset[int]:
    raw = (os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    extra = (os.getenv("TBCC_COMPANION_ADMIN_IDS") or "").strip()
    for part in extra.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids)


def network_channel_idents() -> list[tuple[str, str, str]]:
    """(key, chat_id, display_name) for membership checks — deduped by chat id."""
    rows: list[tuple[str, str, str]] = [("main_group", MAIN_GROUP_IDENT, "AOF Loot Room")]
    seen = {MAIN_GROUP_IDENT}
    for ch in AOF_NETWORK_CHANNELS:
        if ch.identifier in seen:
            continue
        seen.add(ch.identifier)
        rows.append((ch.key, ch.identifier, ch.display_name))
    return rows


@dataclass
class CompanionAccess:
    user_id: int
    lv_ack: bool = False
    member_verified: bool = False
    matched_channel: str = ""
    trial_used: int = 0
    credits: int = 0
    verified_at: float = 0.0
    vip_subscriber: bool = False

    @property
    def gate_complete(self) -> bool:
        if not gate_enabled():
            return True
        if self.vip_subscriber and vip_skip_gate_for_subscribers():
            return True
        return self.lv_ack and self.member_verified

    def generations_remaining(self) -> int:
        trial_left = max(0, free_trial_photos() - self.trial_used)
        return trial_left + max(0, self.credits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "lv_ack": self.lv_ack,
            "member_verified": self.member_verified,
            "matched_channel": self.matched_channel,
            "trial_used": self.trial_used,
            "credits": self.credits,
            "verified_at": self.verified_at,
            "vip_subscriber": self.vip_subscriber,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanionAccess:
        return cls(
            user_id=int(data.get("user_id") or 0),
            lv_ack=bool(data.get("lv_ack")),
            member_verified=bool(data.get("member_verified")),
            matched_channel=str(data.get("matched_channel") or ""),
            trial_used=int(data.get("trial_used") or 0),
            credits=int(data.get("credits") or 0),
            verified_at=float(data.get("verified_at") or 0.0),
            vip_subscriber=bool(data.get("vip_subscriber")),
        )


def get_access(user_id: int, *, sync_vip: bool = False) -> CompanionAccess:
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_key(user_id))
            if raw:
                acc = CompanionAccess.from_dict(json.loads(raw))
                if sync_vip:
                    return refresh_vip_subscriber_flag(user_id)
                return acc
        except Exception as e:
            logger.warning("companion_access get failed: %s", e)
    data = _MEM.get(user_id)
    if data:
        acc = CompanionAccess.from_dict(data)
        if sync_vip:
            return refresh_vip_subscriber_flag(user_id)
        return acc
    acc = CompanionAccess(user_id=user_id)
    if sync_vip:
        return refresh_vip_subscriber_flag(user_id)
    return acc


def save_access(access: CompanionAccess) -> None:
    payload = json.dumps(access.to_dict())
    r = _redis()
    if r is not None:
        try:
            r.setex(_key(access.user_id), _ACCESS_TTL_SEC, payload)
            return
        except Exception as e:
            logger.warning("companion_access save failed: %s", e)
    _MEM[access.user_id] = access.to_dict()


def mark_lv_acknowledged(user_id: int) -> CompanionAccess:
    acc = get_access(user_id)
    acc.lv_ack = True
    save_access(acc)
    _maybe_credit_referrer(int(user_id))
    return acc


async def auto_complete_gate_if_ready(bot: Bot, user_id: int) -> CompanionAccess:
    """
    Refresh VIP flag and re-check channel membership when LV is done but member flag unset.

    Users often join addlist channels after tapping verify, or retry by sending a photo —
    this avoids a dead-end loop at Member ⏳.
    """
    acc = get_access(user_id, sync_vip=True)
    if acc.gate_complete:
        return acc
    if acc.lv_ack and not acc.member_verified:
        await verify_aof_membership(bot, user_id)
        acc = get_access(user_id)
    return acc


async def verify_aof_membership(bot: Bot, user_id: int) -> tuple[bool, str]:
    """
    True if user is in any AOF network channel the bot can inspect.
    Requires @aof_spicybot_bot to be a member/admin of those channels.
    """
    if user_id in admin_telegram_ids():
        acc = get_access(user_id)
        acc.member_verified = True
        acc.matched_channel = "admin bypass"
        acc.verified_at = time.time()
        save_access(acc)
        return True, "admin bypass"

    channels = network_channel_idents()
    for _key, ident, display_name in channels:
        chat_id: int | str
        try:
            chat_id = int(ident)
        except ValueError:
            chat_id = ident
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in _MEMBER_STATUSES:
                acc = get_access(user_id)
                acc.member_verified = True
                acc.matched_channel = display_name
                acc.verified_at = time.time()
                save_access(acc)
                _maybe_credit_referrer(user_id)
                return True, display_name
        except TelegramError as e:
            logger.debug("get_chat_member %s uid=%s: %s", ident, user_id, e)
            continue
    logger.info(
        "verify_aof_membership: uid=%s not found in any of %d AOF channels",
        user_id,
        len(channels),
    )
    return False, ""


def _maybe_credit_referrer(user_id: int) -> None:
    try:
        from app.services.companion_referral import maybe_credit_referrer_on_gate_complete

        maybe_credit_referrer_on_gate_complete(user_id)
    except Exception as e:
        logger.debug("companion referral credit skipped: %s", e)


def can_spend_operator_api(user_id: int) -> tuple[bool, str]:
    """Whether we may charge YOUR undress API balance for this user."""
    if user_id in admin_telegram_ids():
        return True, "admin"
    acc = get_access(user_id, sync_vip=True)
    if gate_enabled() and not acc.gate_complete:
        return False, "complete_gate"
    if acc.generations_remaining() > 0:
        return True, "allowance"
    return False, "no_credits"


def consume_generation_allowance(user_id: int) -> bool:
    acc = get_access(user_id)
    if user_id in admin_telegram_ids():
        return True
    trial_cap = free_trial_photos()
    if acc.trial_used < trial_cap:
        acc.trial_used += 1
        save_access(acc)
        return True
    if acc.credits > 0:
        acc.credits -= 1
        save_access(acc)
        return True
    return False


def refund_generation_allowance(user_id: int) -> None:
    """Return one photo slot after a failed queue (non-admin)."""
    if user_id in admin_telegram_ids():
        return
    acc = get_access(user_id)
    if acc.trial_used > 0:
        acc.trial_used -= 1
        save_access(acc)
        return
    acc.credits += 1
    save_access(acc)


def grant_credits(user_id: int, amount: int) -> int:
    acc = get_access(user_id)
    acc.credits = max(0, acc.credits + int(amount))
    save_access(acc)
    return acc.credits


def addlist_url() -> str:
    return (os.getenv("TBCC_AOF_ADDLIST_URL") or ADDLIST_RAW).strip()


def main_group_invite_url() -> str:
    return (os.getenv("TBCC_AOF_MAIN_GROUP_INVITE") or MAIN_GROUP_INVITE).strip()
