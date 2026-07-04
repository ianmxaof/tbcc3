"""Unified multi-surface campaign deploy: Telegram → Buffer → Discord + ledger."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign_deploy_event import CampaignDeployEvent
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.campaign_surface_copy import resolve_surface_texts
from app.services.outbound_webhook import notify_discord_webhook_text

logger = logging.getLogger(__name__)


@dataclass
class DeployOptions:
    telegram: bool = True
    buffer: bool | None = None  # None = use post.buffer_mirror_enabled
    discord: bool | None = None  # None = use post.discord_mirror_enabled
    sync: bool = False
    reshuffle_album: bool = False
    trigger: str = "api"


@dataclass
class DeploySurfaceResult:
    status: str = "skipped"
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeployResult:
    scheduled_post_id: int
    campaign_group_id: str | None
    telegram: DeploySurfaceResult = field(default_factory=DeploySurfaceResult)
    buffer: DeploySurfaceResult = field(default_factory=DeploySurfaceResult)
    discord: DeploySurfaceResult = field(default_factory=DeploySurfaceResult)
    ledger_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled_post_id": self.scheduled_post_id,
            "campaign_group_id": self.campaign_group_id,
            "ledger_id": self.ledger_id,
            "telegram": {"status": self.telegram.status, "error": self.telegram.error, **self.telegram.detail},
            "buffer": {"status": self.buffer.status, "error": self.buffer.error, **self.buffer.detail},
            "discord": {"status": self.discord.status, "error": self.discord.error, **self.discord.detail},
        }


def _resolve_leader(post: ScheduledTextPost, db: Session) -> tuple[ScheduledTextPost, str | None]:
    cg = getattr(post, "campaign_group_id", None)
    if not cg:
        return post, None
    siblings = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.campaign_group_id == cg)
        .order_by(ScheduledTextPost.id)
        .all()
    )
    return (siblings[0] if siblings else post), cg


def _should_buffer(post: ScheduledTextPost, opt: DeployOptions) -> bool:
    if opt.buffer is False:
        return False
    if opt.buffer is True:
        return True
    return bool(getattr(post, "buffer_mirror_enabled", False))


def _should_discord(post: ScheduledTextPost, opt: DeployOptions) -> bool:
    if opt.discord is False:
        return False
    if opt.discord is True:
        return True
    return bool(getattr(post, "discord_mirror_enabled", False))


def _run_telegram(post_id: int, *, reshuffle: bool) -> DeploySurfaceResult:
    from app.workers.poster_worker import post_scheduled_text

    out = DeploySurfaceResult(status="pending")
    try:
        post_scheduled_text(int(post_id), reshuffle_album=reshuffle, manual_trigger=True)
        out.status = "ok"
    except Exception as e:
        out.status = "failed"
        out.error = str(e)[:2000]
        logger.exception("campaign deploy telegram failed post_id=%s", post_id)
    return out


def _enqueue_telegram(post_id: int, *, reshuffle: bool) -> DeploySurfaceResult:
    from app.workers.poster_worker import post_scheduled_text

    try:
        post_scheduled_text.delay(int(post_id), reshuffle_album=reshuffle, manual_trigger=True)
        return DeploySurfaceResult(status="queued")
    except Exception as e:
        return DeploySurfaceResult(status="failed", error=str(e)[:2000])


def _run_buffer_mirror(post_id: int) -> DeploySurfaceResult:
    from app.services.scheduled_buffer_mirror import mirror_scheduled_post_to_buffer_with_surfaces

    out = DeploySurfaceResult(status="pending")
    try:
        detail = mirror_scheduled_post_to_buffer_with_surfaces(int(post_id), require_mirror_enabled=False)
        out.detail = detail or {}
        out.status = "ok" if detail.get("ok") else "failed"
        if not detail.get("ok"):
            out.error = str(detail.get("error") or "buffer mirror returned not ok")[:2000]
    except Exception as e:
        out.status = "failed"
        out.error = str(e)[:2000]
        logger.exception("campaign deploy buffer failed post_id=%s", post_id)
    return out


def _run_discord(post: ScheduledTextPost, db: Session) -> DeploySurfaceResult:
    hook = (os.environ.get("TBCC_DISCORD_LISTENING_RELAY_WEBHOOK_URL") or "").strip()
    if not hook:
        return DeploySurfaceResult(status="skipped", error="TBCC_DISCORD_LISTENING_RELAY_WEBHOOK_URL unset")
    try:
        texts = resolve_surface_texts(post, db)
        plain = texts.get("discord") or texts.get("ig_threads") or texts.get("x") or ""
        if not plain.strip():
            return DeploySurfaceResult(status="failed", error="empty discord body")
        notify_discord_webhook_text(hook, plain)
        return DeploySurfaceResult(status="ok", detail={"chars": len(plain)})
    except Exception as e:
        return DeploySurfaceResult(status="failed", error=str(e)[:2000])


def _persist_ledger(db: Session, result: DeployResult, trigger: str) -> int:
    row = CampaignDeployEvent(
        scheduled_post_id=result.scheduled_post_id,
        campaign_group_id=result.campaign_group_id,
        trigger=trigger,
        telegram_status=result.telegram.status,
        telegram_error=result.telegram.error,
        buffer_status=result.buffer.status,
        buffer_error=result.buffer.error,
        discord_status=result.discord.status,
        discord_error=result.discord.error,
        surfaces_json=json.dumps(result.to_dict()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return int(row.id)


def deploy_scheduled_post(
    db: Session,
    post_id: int,
    options: DeployOptions | None = None,
) -> DeployResult:
    opt = options or DeployOptions()
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
    if not post:
        raise ValueError(f"scheduled post {post_id} not found")

    leader, cg = _resolve_leader(post, db)
    leader_id = int(leader.id)
    result = DeployResult(scheduled_post_id=leader_id, campaign_group_id=cg)

    if opt.telegram:
        if opt.sync:
            result.telegram = _run_telegram(leader_id, reshuffle=opt.reshuffle_album)
            db.refresh(leader)
            # poster_worker runs buffer + discord mirrors after successful Telegram send.
            if result.telegram.status == "ok":
                if _should_buffer(leader, opt):
                    result.buffer = _run_buffer_mirror(leader_id)
                else:
                    result.buffer = DeploySurfaceResult(
                        status="delegated",
                        detail={"note": "handled by poster_worker if buffer_mirror_enabled"},
                    )
                if _should_discord(leader, opt):
                    result.discord = _run_discord(leader, db)
                else:
                    result.discord = DeploySurfaceResult(
                        status="delegated",
                        detail={"note": "handled by poster_worker if discord_mirror_enabled"},
                    )
            else:
                result.buffer = DeploySurfaceResult(status="skipped", error="telegram failed")
                result.discord = DeploySurfaceResult(status="skipped", error="telegram failed")
            result.ledger_id = _persist_ledger(db, result, opt.trigger)
            return result
        result.telegram = _enqueue_telegram(leader_id, reshuffle=opt.reshuffle_album)
        result.ledger_id = _persist_ledger(db, result, opt.trigger)
        return result

    db.refresh(leader)

    if _should_buffer(leader, opt):
        result.buffer = _run_buffer_mirror(leader_id)
    else:
        result.buffer = DeploySurfaceResult(status="skipped")

    if _should_discord(leader, opt):
        result.discord = _run_discord(leader, db)
    else:
        result.discord = DeploySurfaceResult(status="skipped")

    result.ledger_id = _persist_ledger(db, result, opt.trigger)
    return result


def list_recent_deploys(db: Session, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(CampaignDeployEvent)
        .order_by(CampaignDeployEvent.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    out: list[dict] = []
    for r in rows:
        surfaces = {}
        if r.surfaces_json:
            try:
                surfaces = json.loads(r.surfaces_json)
            except (json.JSONDecodeError, TypeError):
                surfaces = {}
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "scheduled_post_id": r.scheduled_post_id,
                "campaign_group_id": r.campaign_group_id,
                "trigger": r.trigger,
                "telegram_status": r.telegram_status,
                "buffer_status": r.buffer_status,
                "discord_status": r.discord_status,
                "surfaces": surfaces,
            }
        )
    return out


def audit_scheduled_posts(db: Session) -> list[dict]:
    rows = db.query(ScheduledTextPost).order_by(ScheduledTextPost.id).all()
    out: list[dict] = []
    for p in rows:
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "channel_id": p.channel_id,
                "campaign_group_id": getattr(p, "campaign_group_id", None),
                "interval_minutes": p.interval_minutes,
                "last_posted_at": p.last_posted_at.isoformat() if p.last_posted_at else None,
                "sent_at": p.sent_at.isoformat() if p.sent_at else None,
                "buffer_mirror_enabled": bool(getattr(p, "buffer_mirror_enabled", False)),
                "discord_mirror_enabled": bool(getattr(p, "discord_mirror_enabled", False)),
                "send_failure_streak": getattr(p, "send_failure_streak", None),
                "posting_auto_paused_at": (
                    p.posting_auto_paused_at.isoformat() if getattr(p, "posting_auto_paused_at", None) else None
                ),
            }
        )
    return out
