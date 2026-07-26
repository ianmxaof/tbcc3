"""Loot goblin drop lifecycle — create, announce, claim, revoke."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.request import HTTPXRequest

from app.models.goblin_claim import GoblinClaim
from app.models.goblin_drop import GoblinDrop
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.goblin_announce import delete_goblin_announce, send_goblin_announce
from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings, resolve_bot_token_raw
from app.services.loot_free_pull import build_free_pull_preview
from app.services.loot_preview_delivery import send_loot_free_pull_to_chat

logger = logging.getLogger(__name__)


def _settings_row(db: Session) -> ListeningRelaySettings | None:
    return db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()


def create_goblin_drop(
    db: Session,
    *,
    channel_id: int,
    message_thread_id: int | None,
    relay_log_id: int | None,
    settings: ListeningRelaySettings | None = None,
) -> GoblinDrop | None:
    settings = settings or _settings_row(db)
    cap = max(1, int(getattr(settings, "goblin_claims_cap", None) or 5)) if settings else 5
    token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:20]
    drop = GoblinDrop(
        created_at=datetime.utcnow(),
        token=token,
        status="active",
        claims_used=0,
        claims_cap=cap,
        relay_log_id=int(relay_log_id) if relay_log_id else None,
        channel_id=int(channel_id),
        message_thread_id=int(message_thread_id) if message_thread_id else None,
    )
    db.add(drop)
    db.flush()
    return drop


def schedule_goblin_drop(
    db: Session,
    *,
    channel_id: int,
    message_thread_id: int | None,
    relay_log_id: int | None,
) -> dict[str, Any]:
    """Persist drop row and queue Bot API announce + TTL delete."""
    settings = _settings_row(db)
    drop = create_goblin_drop(
        db,
        channel_id=channel_id,
        message_thread_id=message_thread_id,
        relay_log_id=relay_log_id,
        settings=settings,
    )
    if not drop:
        return {"ok": False, "error": "create_failed"}
    db.commit()
    from app.workers.goblin_worker import goblin_announce_drop

    goblin_announce_drop.delay(int(drop.id))
    return {"ok": True, "drop_id": int(drop.id), "token": drop.token}


def revoke_goblin_drop(db: Session, *, token: str) -> dict[str, Any]:
    drop = db.query(GoblinDrop).filter(GoblinDrop.token == token.strip()).first()
    if not drop:
        return {"ok": False, "error": "not_found"}
    if drop.status == "revoked":
        return {"ok": True, "already_revoked": True}
    drop.status = "revoked"
    drop.revoked_at = datetime.utcnow()
    delete_goblin_announce(db, drop)
    db.commit()
    return {"ok": True, "drop_id": int(drop.id)}


def _run_loot_async(coro):
    """Run PTB/Telethon delivery off the uvicorn loop (matches app.api.loot._run_loot_async)."""
    import concurrent.futures

    async def _inner():
        from app.services.telegram_admin import reset_admin_client

        await reset_admin_client()
        return await coro

    def _worker():
        import asyncio

        return asyncio.run(_inner())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_worker).result(timeout=300)


def _deliver_goblin_pull(db: Session, telegram_user_id: int) -> dict[str, Any]:
    token = resolve_bot_token_raw(db)
    if not token:
        return {"ok": False, "reason": "loot_bot_token_unset"}
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )
    preview = build_free_pull_preview(db, telegram_user_id=telegram_user_id, goblin_bonus=True)
    if not preview.get("ok"):
        return {"ok": False, "reason": preview.get("reason") or "preview_failed", "preview": preview}

    rem_before = int(preview.get("free_pulls_remaining_before") or 0)

    async def _run():
        from app.database.session import SessionLocal

        worker_db = SessionLocal()
        try:
            from app.services.aof_social_links import payment_bot_username

            return await send_loot_free_pull_to_chat(
                worker_db,
                bot=bot,
                chat_id=int(telegram_user_id),
                preview=preview,
                spoiler_default=spoiler,
                payment_bot_username=payment_bot_username(),
                free_pulls_remaining=max(0, rem_before),
            )
        finally:
            worker_db.close()

    delivery = _run_loot_async(_run())
    if int(delivery.get("media_sent") or 0) <= 0:
        return {"ok": False, "reason": "delivery_failed", "delivery": delivery}
    return {"ok": True, "preview": preview, "delivery": delivery}


def claim_goblin_drop(
    db: Session,
    *,
    token: str,
    telegram_user_id: int,
    announced_at: datetime | None = None,
) -> dict[str, Any]:
    """Atomic cap claim + optional reward delivery."""
    tok = (token or "").strip()
    if not tok:
        return {"ok": False, "reason": "invalid_token"}

    drop = db.query(GoblinDrop).filter(GoblinDrop.token == tok).first()
    if not drop:
        return {"ok": False, "reason": "not_found"}
    if drop.status == "revoked":
        return {"ok": False, "reason": "revoked"}
    if drop.status == "exhausted":
        return {"ok": False, "reason": "exhausted"}

    existing = (
        db.query(GoblinClaim)
        .filter(GoblinClaim.drop_id == int(drop.id), GoblinClaim.telegram_user_id == int(telegram_user_id))
        .first()
    )
    if existing:
        return {"ok": False, "reason": "already_claimed"}

    now = datetime.utcnow()
    latency_ms: int | None = None
    ref = announced_at or drop.announced_at
    if ref:
        latency_ms = max(0, int((now - ref).total_seconds() * 1000))

    stmt = (
        update(GoblinDrop)
        .where(
            GoblinDrop.id == int(drop.id),
            GoblinDrop.status == "active",
            GoblinDrop.claims_used < GoblinDrop.claims_cap,
        )
        .values(claims_used=GoblinDrop.claims_used + 1)
        .returning(GoblinDrop.claims_used, GoblinDrop.claims_cap)
    )
    row = db.execute(stmt).first()
    if not row:
        db.refresh(drop)
        if drop.status != "active":
            reason = drop.status
        elif int(drop.claims_used or 0) >= int(drop.claims_cap or 0):
            reason = "exhausted"
        else:
            reason = "claim_failed"
        return {"ok": False, "reason": reason}

    claims_used, claims_cap = int(row[0]), int(row[1])
    if claims_used >= claims_cap:
        drop.status = "exhausted"
        db.flush()

    claim = GoblinClaim(
        drop_id=int(drop.id),
        telegram_user_id=int(telegram_user_id),
        claimed_at=now,
        latency_ms=latency_ms,
    )
    db.add(claim)
    db.flush()

    reward = _deliver_goblin_pull(db, int(telegram_user_id))
    if not reward.get("ok"):
        db.rollback()
        return {"ok": False, "reason": reward.get("reason") or "delivery_failed", "delivery": reward}

    db.commit()
    return {
        "ok": True,
        "drop_id": int(drop.id),
        "claims_used": claims_used,
        "claims_cap": claims_cap,
        "latency_ms": latency_ms,
        "preview": reward.get("preview"),
        "delivery": reward.get("delivery"),
    }
