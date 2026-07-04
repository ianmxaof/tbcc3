"""Loot-game referrals: bonus free pulls on @aof_lootgod_bot (separate from payment-bot subscription referrals)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.loot import LootPlayerStats
from app.models.referral_code import ReferralCode

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_code(length: int = 8) -> str:
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(length))


def referral_bonus_pulls_setting(db: Session | None = None) -> int:
    raw = (os.getenv("TBCC_LOOT_REFERRAL_BONUS_PULLS") or "1").strip()
    try:
        default = max(0, min(20, int(raw)))
    except ValueError:
        default = 1
    if db is None:
        return default
    from app.models.loot_bot_settings import LootBotSettings

    row = db.query(LootBotSettings).filter(LootBotSettings.id == 1).first()
    if row and row.referral_bonus_pulls is not None:
        return max(0, min(20, int(row.referral_bonus_pulls)))
    return default


def loot_referrals_enabled(db: Session | None = None) -> bool:
    env = (os.getenv("TBCC_LOOT_REFERRAL_ENABLED") or "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if db is None:
        return True
    from app.models.loot_bot_settings import LootBotSettings

    row = db.query(LootBotSettings).filter(LootBotSettings.id == 1).first()
    if row is not None:
        return bool(row.loot_referral_enabled)
    return True


def ensure_loot_referral_code(db: Session, telegram_user_id: int) -> dict:
    uid = int(telegram_user_id)
    existing = db.query(ReferralCode).filter(ReferralCode.telegram_user_id == uid).first()
    if existing:
        code = existing.code
        return {"code": code, "start_param": f"lootref_{code}"}
    for _ in range(64):
        code = _generate_code()
        if db.query(ReferralCode).filter(ReferralCode.code == code).first():
            continue
        row = ReferralCode(telegram_user_id=uid, code=code, created_at=datetime.utcnow())
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return {"code": code, "start_param": f"lootref_{code}"}
        except Exception:
            db.rollback()
    raise RuntimeError("Could not allocate referral code")


def resolve_loot_referral_code(db: Session, code: str) -> int | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    row = db.query(ReferralCode).filter(ReferralCode.code == normalized).first()
    return int(row.telegram_user_id) if row else None


def record_loot_referral(db: Session, *, referred_user_id: int, referrer_user_id: int) -> bool:
    from app.models.loot import LootReferralTracking

    if not loot_referrals_enabled(db):
        return False
    ref_uid = int(referrer_user_id)
    new_uid = int(referred_user_id)
    if ref_uid == new_uid:
        return False
    existing = (
        db.query(LootReferralTracking)
        .filter(LootReferralTracking.referred_user_id == new_uid)
        .first()
    )
    if existing:
        if existing.referrer_user_id != ref_uid:
            existing.referrer_user_id = ref_uid
            existing.created_at = datetime.utcnow()
            db.commit()
        return True
    db.add(
        LootReferralTracking(
            referred_user_id=new_uid,
            referrer_user_id=ref_uid,
            credited=False,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    _notify_loot_referral_signup(referrer_user_id=ref_uid, referred_user_id=new_uid)
    return True


def _notify_loot_referral_signup(*, referrer_user_id: int, referred_user_id: int) -> None:
    """Inbox-only — not an instant sale; feeds analytics / /inbox review."""
    try:
        from app.services.admin_inbox import push_admin_inbox_event

        push_admin_inbox_event(
            category="loot",
            severity="info",
            title="New loot referral signup",
            body=(
                f"Referrer {referrer_user_id} → new user {referred_user_id}"
            ),
            meta={"referrer_user_id": referrer_user_id, "referred_user_id": referred_user_id},
            instant=False,
        )
    except Exception:
        pass


def bonus_free_pulls_for(db: Session, telegram_user_id: int) -> int:
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    return int(row.bonus_free_pulls or 0) if row else 0


def try_credit_referrer_for_pull(db: Session, referred_user_id: int) -> dict | None:
    """When referred user uses a free pull, grant referrer bonus pulls once."""
    from app.models.loot import LootReferralTracking

    if not loot_referrals_enabled(db):
        return None
    tr = (
        db.query(LootReferralTracking)
        .filter(
            LootReferralTracking.referred_user_id == int(referred_user_id),
            LootReferralTracking.credited.is_(False),
        )
        .first()
    )
    if not tr:
        return None
    bonus = referral_bonus_pulls_setting(db)
    if bonus <= 0:
        tr.credited = True
        db.commit()
        return None
    referrer_uid = int(tr.referrer_user_id)
    ref_row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == referrer_uid).first()
    if not ref_row:
        ref_row = LootPlayerStats(telegram_user_id=referrer_uid, roll_count=0, free_pulls_used=0, bonus_free_pulls=0)
        db.add(ref_row)
    ref_row.bonus_free_pulls = int(ref_row.bonus_free_pulls or 0) + bonus
    tr.credited = True
    db.commit()
    result = {"referrer_user_id": referrer_uid, "bonus_granted": bonus, "referred_user_id": int(referred_user_id)}
    _notify_loot_referral_credit(result)
    return result


def _notify_loot_referral_credit(result: dict) -> None:
    """Inbox-only — secondary loot signal, not a sale."""
    try:
        from app.services.admin_inbox import push_admin_inbox_event

        ref_uid = int(result.get("referrer_user_id") or 0)
        new_uid = int(result.get("referred_user_id") or 0)
        bonus = int(result.get("bonus_granted") or 0)
        push_admin_inbox_event(
            category="loot",
            severity="info",
            title="Loot referral bonus credited",
            body=(
                f"Referrer {ref_uid} earned +{bonus} bonus pull(s) (referred {new_uid} used free pull)"
            ),
            meta=result,
            instant=False,
        )
    except Exception:
        pass
