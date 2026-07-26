"""Entitlement ledger ops — grant, list, expire, ban-recovery reissue stubs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.buyer_entitlement import BuyerEntitlement


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def grant_entitlement(
    db: Session,
    *,
    telegram_user_id: int,
    kind: str,
    network_key: str | None = None,
    plan_id: int | None = None,
    duration_hours: int | None = None,
    duration_days: int | None = None,
    primary_channel_ident: str | None = None,
    backup_channel_ident: str | None = None,
    invite_url: str | None = None,
    source_note: str | None = None,
) -> BuyerEntitlement:
    now = _utcnow()
    ends: datetime | None = None
    if duration_hours is not None:
        ends = now + timedelta(hours=int(duration_hours))
    elif duration_days is not None:
        ends = now + timedelta(days=int(duration_days))
    row = BuyerEntitlement(
        telegram_user_id=int(telegram_user_id),
        kind=(kind or "other").strip().lower()[:32],
        network_key=(network_key or "").strip().lower() or None,
        plan_id=plan_id,
        status="active",
        starts_at=now,
        ends_at=ends,
        primary_channel_ident=primary_channel_ident,
        backup_channel_ident=backup_channel_ident,
        last_invite_url=invite_url,
        source_note=(source_note or "").strip() or None,
    )
    db.add(row)
    db.flush()
    return row


def list_active_entitlements(
    db: Session,
    *,
    telegram_user_id: int | None = None,
    network_key: str | None = None,
    kind: str | None = None,
) -> list[BuyerEntitlement]:
    now = _utcnow()
    q = db.query(BuyerEntitlement).filter(BuyerEntitlement.status == "active")
    if telegram_user_id is not None:
        q = q.filter(BuyerEntitlement.telegram_user_id == int(telegram_user_id))
    if network_key:
        q = q.filter(BuyerEntitlement.network_key == network_key.strip().lower())
    if kind:
        q = q.filter(BuyerEntitlement.kind == kind.strip().lower())
    rows = q.all()
    out: list[BuyerEntitlement] = []
    dirty = False
    for r in rows:
        if r.ends_at is not None and r.ends_at < now:
            r.status = "expired"
            dirty = True
            continue
        out.append(r)
    if dirty:
        db.flush()
    return out


def mark_expired(db: Session) -> int:
    now = _utcnow()
    n = (
        db.query(BuyerEntitlement)
        .filter(
            BuyerEntitlement.status == "active",
            BuyerEntitlement.ends_at.isnot(None),
            BuyerEntitlement.ends_at < now,
        )
        .update({"status": "expired"}, synchronize_session=False)
    )
    return int(n or 0)


def reissue_invites_for_lane(
    db: Session,
    *,
    network_key: str,
    new_invite_url: str,
    backup_channel_ident: str | None = None,
) -> dict[str, Any]:
    """
    Ban recovery: stamp active lane_pass holders with a new invite URL.

    Does not send Telegram DMs yet — returns user ids for a worker to notify.
    """
    nk = (network_key or "").strip().lower()
    invite = (new_invite_url or "").strip()
    if not nk or not invite.startswith(("http://", "https://")):
        raise ValueError("network_key and https invite_url required")
    now = _utcnow()
    active = list_active_entitlements(db, network_key=nk, kind="lane_pass")
    user_ids: list[int] = []
    for r in active:
        r.last_invite_url = invite
        r.last_reissued_at = now
        if backup_channel_ident:
            r.backup_channel_ident = backup_channel_ident
        user_ids.append(int(r.telegram_user_id))
    db.flush()
    return {
        "ok": True,
        "network_key": nk,
        "reissued": len(user_ids),
        "telegram_user_ids": user_ids,
        "invite_url": invite,
        "dm_pending": True,
    }
