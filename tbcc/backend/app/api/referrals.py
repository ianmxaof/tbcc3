"""Referral tracking and rewards."""
import secrets
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.referral_code import ReferralCode
from app.models.referral_tracking import ReferralTracking
from app.models.subscription import Subscription

router = APIRouter()

# Short, unambiguous chars for shareable codes (Telegram /start payload max 64 bytes).
_REF_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_referral_code(length: int = 8) -> str:
    return "".join(secrets.choice(_REF_CODE_ALPHABET) for _ in range(length))


@router.post("/")
def record_referral(
    data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Record that user was referred (called when they click ref link)."""
    referred_user_id = data.get("referred_user_id")
    referrer_user_id = data.get("referrer_user_id")
    if not referred_user_id or not referrer_user_id:
        return {"error": "referred_user_id and referrer_user_id required"}
    # Upsert: if already exists, update created_at
    existing = (
        db.query(ReferralTracking)
        .filter(ReferralTracking.referred_user_id == int(referred_user_id))
        .first()
    )
    if existing:
        existing.referrer_user_id = int(referrer_user_id)
        existing.created_at = datetime.utcnow()
    else:
        rt = ReferralTracking(
            referred_user_id=int(referred_user_id),
            referrer_user_id=int(referrer_user_id),
            created_at=datetime.utcnow(),
        )
        db.add(rt)
    db.commit()
    return {"ok": True}


@router.post("/ensure-code")
def ensure_referral_code(
    data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Assign a persistent short referral code the first time a user opens the referral flow.
    Deep link: https://t.me/BotUsername?start=ref_<code> (also supports legacy ref_<telegram_user_id>).
    """
    uid = data.get("telegram_user_id")
    if uid is None:
        return {"error": "telegram_user_id required"}
    try:
        telegram_user_id = int(uid)
    except (TypeError, ValueError):
        return {"error": "telegram_user_id must be an integer"}

    existing = (
        db.query(ReferralCode).filter(ReferralCode.telegram_user_id == telegram_user_id).first()
    )
    if existing:
        c = existing.code
        return {"code": c, "start_param": f"ref_{c}"}

    for _ in range(64):
        code = _generate_referral_code()
        clash = db.query(ReferralCode).filter(ReferralCode.code == code).first()
        if clash:
            continue
        row = ReferralCode(
            telegram_user_id=telegram_user_id,
            code=code,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return {"code": code, "start_param": f"ref_{code}"}
        except Exception:
            db.rollback()
            continue

    return {"error": "Could not allocate referral code"}


@router.get("/by-code/{code}")
def get_referrer_by_code(code: str, db: Session = Depends(get_db)):
    """Resolve referral code → Telegram user id (for /start ref_<code> handling)."""
    normalized = (code or "").strip().upper()
    if not normalized or len(normalized) > 16:
        raise HTTPException(status_code=404, detail="not found")
    row = db.query(ReferralCode).filter(ReferralCode.code == normalized).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return {"telegram_user_id": row.telegram_user_id}


@router.get("/referrer-for/{user_id}")
def get_referrer_for_user(user_id: int, db: Session = Depends(get_db)):
    """Get referrer_id for a user (from tracking). Returns null if none."""
    rt = (
        db.query(ReferralTracking)
        .filter(ReferralTracking.referred_user_id == user_id)
        .first()
    )
    if not rt:
        return {"referrer_id": None}
    return {"referrer_id": rt.referrer_user_id}


@router.get("/stats")
def referral_stats(
    db: Session = Depends(get_db),
    referrer_id: int | None = None,
):
    """Get referral stats. If referrer_id given, stats for that user."""
    q = db.query(Subscription).filter(Subscription.referrer_id.isnot(None))
    if referrer_id is not None:
        q = q.filter(Subscription.referrer_id == referrer_id)
    subs = q.all()
    by_ref = Counter(s.referrer_id for s in subs)
    return {
        "total_referred_subscriptions": len(subs),
        "by_referrer": dict(by_ref),
    }
