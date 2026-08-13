"""Companion bot referrals — bonus photo credits when invitee completes the gate."""

from __future__ import annotations

import json
import logging
import os
import secrets
from typing import Any

from app.services.companion_access import gate_enabled, get_access, grant_credits

logger = logging.getLogger(__name__)

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REF_TTL_SEC = 60 * 60 * 24 * 365
_MEM_CODES: dict[str, int] = {}
_MEM_USER_CODE: dict[int, str] = {}
_MEM_PENDING: dict[int, int] = {}
_MEM_CREDITED: set[int] = set()


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("companion_referral: redis unavailable: %s", e)
        return None


def referrals_enabled() -> bool:
    raw = (os.getenv("TBCC_COMPANION_REFERRAL_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def referral_bonus_photos() -> int:
    raw = (os.getenv("TBCC_COMPANION_REFERRAL_BONUS_PHOTOS") or "1").strip()
    try:
        return max(0, min(10, int(raw)))
    except ValueError:
        return 1


def referral_require_invitee_reveal() -> bool:
    """When true, referrer earns only after invitee completes gate AND uses one reveal."""
    raw = (os.getenv("TBCC_COMPANION_REFERRAL_REQUIRE_INVITEE_REVEAL") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def referral_reward_description() -> str:
    bonus = referral_bonus_photos()
    if referral_require_invitee_reveal():
        return (
            f"When a friend completes the AOF gate and sends their first reveal, "
            f"you earn <b>+{bonus}</b> photo credit(s)."
        )
    return (
        f"When a friend completes the AOF gate (LV + channel verify), "
        f"you earn <b>+{bonus}</b> photo credit(s)."
    )


def _code_key(code: str) -> str:
    return f"tbcc:companion:refcode:{code.upper()}"


def _user_code_key(user_id: int) -> str:
    return f"tbcc:companion:refuser:{user_id}"


def _pending_key(referred_id: int) -> str:
    return f"tbcc:companion:refpending:{referred_id}"


def _credited_key(referred_id: int) -> str:
    return f"tbcc:companion:refcredited:{referred_id}"


def _generate_code(length: int = 8) -> str:
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(length))


def ensure_referral_code(user_id: int) -> str:
    uid = int(user_id)
    r = _redis()
    if r is not None:
        try:
            existing = r.get(_user_code_key(uid))
            if existing:
                return str(existing)
        except Exception as e:
            logger.warning("companion_referral ensure read failed: %s", e)

    if uid in _MEM_USER_CODE:
        return _MEM_USER_CODE[uid]

    for _ in range(64):
        code = _generate_code()
        if r is not None:
            try:
                if r.set(_code_key(code), str(uid), nx=True, ex=_REF_TTL_SEC):
                    r.setex(_user_code_key(uid), _REF_TTL_SEC, code)
                    return code
            except Exception as e:
                logger.warning("companion_referral ensure write failed: %s", e)
                break
        if code not in _MEM_CODES:
            _MEM_CODES[code] = uid
            _MEM_USER_CODE[uid] = code
            return code
    raise RuntimeError("Could not allocate companion referral code")


def resolve_referral_code(code: str) -> int | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_code_key(normalized))
            if raw:
                return int(raw)
        except Exception as e:
            logger.warning("companion_referral resolve failed: %s", e)
    return _MEM_CODES.get(normalized)


def record_referral(*, referred_user_id: int, referrer_user_id: int) -> bool:
    if not referrals_enabled():
        return False
    referred = int(referred_user_id)
    referrer = int(referrer_user_id)
    if referred == referrer:
        return False
    r = _redis()
    if r is not None:
        try:
            r.setex(_pending_key(referred), _REF_TTL_SEC, str(referrer))
            return True
        except Exception as e:
            logger.warning("companion_referral record failed: %s", e)
    _MEM_PENDING[referred] = referrer
    return True


def record_referral_by_code(*, referred_user_id: int, code: str) -> bool:
    referrer = resolve_referral_code(code)
    if referrer is None:
        return False
    return record_referral(referred_user_id=referred_user_id, referrer_user_id=referrer)


def _referrer_for(referred_user_id: int) -> int | None:
    uid = int(referred_user_id)
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_pending_key(uid))
            if raw:
                return int(raw)
            if r.get(_credited_key(uid)):
                return None
        except Exception as e:
            logger.warning("companion_referral pending read failed: %s", e)
    if uid in _MEM_CREDITED:
        return None
    return _MEM_PENDING.get(uid)


def _mark_credited(referred_user_id: int) -> None:
    uid = int(referred_user_id)
    r = _redis()
    if r is not None:
        try:
            r.setex(_credited_key(uid), _REF_TTL_SEC, "1")
            r.delete(_pending_key(uid))
            return
        except Exception as e:
            logger.warning("companion_referral credited write failed: %s", e)
    _MEM_CREDITED.add(uid)
    _MEM_PENDING.pop(uid, None)


def _grant_referrer_credit(
    referrer_id: int,
    referred_user_id: int,
    *,
    credit_reason: str = "gate",
) -> dict:
    bonus = referral_bonus_photos()
    _mark_credited(int(referred_user_id))
    if bonus <= 0:
        return {
            "referrer_user_id": referrer_id,
            "bonus_granted": 0,
            "referred_user_id": int(referred_user_id),
            "credit_reason": credit_reason,
        }
    new_balance = grant_credits(referrer_id, bonus)
    return {
        "referrer_user_id": referrer_id,
        "bonus_granted": bonus,
        "referred_user_id": int(referred_user_id),
        "referrer_credits": new_balance,
        "credit_reason": credit_reason,
    }


def maybe_credit_referrer_on_gate_complete(referred_user_id: int) -> dict | None:
    """Grant referrer bonus when referred user finishes LV + membership gate."""
    if not referrals_enabled() or not gate_enabled():
        return None
    acc = get_access(int(referred_user_id))
    if not acc.gate_complete:
        return None
    referrer_id = _referrer_for(referred_user_id)
    if referrer_id is None:
        return None
    if referral_require_invitee_reveal():
        return {
            "referrer_user_id": referrer_id,
            "bonus_granted": 0,
            "referred_user_id": int(referred_user_id),
            "deferred_until_reveal": True,
        }
    return _grant_referrer_credit(referrer_id, int(referred_user_id))


def maybe_credit_referrer_on_first_reveal(referred_user_id: int) -> dict | None:
    """Grant referrer bonus after invitee's first reveal when stricter mode is on."""
    if not referrals_enabled() or not referral_require_invitee_reveal():
        return None
    acc = get_access(int(referred_user_id))
    if not acc.gate_complete:
        return None
    referrer_id = _referrer_for(referred_user_id)
    if referrer_id is None:
        return None
    return _grant_referrer_credit(referrer_id, int(referred_user_id), credit_reason="first_reveal")


def referral_link(bot_username: str, user_id: int) -> str:
    code = ensure_referral_code(user_id)
    uname = (bot_username or "aof_spicybot_bot").lstrip("@")
    return f"https://t.me/{uname}?start=compref_{code}"
