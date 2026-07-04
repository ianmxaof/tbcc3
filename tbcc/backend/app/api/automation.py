"""Automation hub overview — scraper, schedulers, Telegram bot runtimes, Format Engine."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.bots import _bot_runtime_status, _bot_runtime_status_secretary
from app.database.session import get_db
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.models.secretary_user_context import SecretaryUserContext
from app.services import scraper_telethon_auth
from app.services.post_scheduler import pool_auto_post_enabled
from app.services.secretary_settings_effective import get_effective_secretary_settings
from app.services.celery_queue_ops import celery_queue_snapshot
from app.services.system_health import collect_scheduling_health

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/overview")
async def automation_overview(db: Session = Depends(get_db)):
    """Single payload for dashboard Automation → Bots & workers tab."""
    scraper: dict = {"authorized": False, "error": None}
    try:
        scraper = await scraper_telethon_auth.scraper_auth_status()
    except Exception as e:
        scraper = {"authorized": False, "error": str(e)}

    sched_total = db.query(func.count(ScheduledTextPost.id)).scalar() or 0
    sched_recurring = (
        db.query(func.count(ScheduledTextPost.id))
        .filter(ScheduledTextPost.interval_minutes.isnot(None))
        .scalar()
        or 0
    )

    sec_eff = get_effective_secretary_settings(db)
    ctx_total = db.query(func.count(SecretaryUserContext.id)).scalar() or 0
    phase_rows = (
        db.query(SecretaryUserContext.current_phase, func.count(SecretaryUserContext.id))
        .group_by(SecretaryUserContext.current_phase)
        .all()
    )
    know_active = (
        db.query(func.count(SecretaryKnowledgeEntry.id))
        .filter(SecretaryKnowledgeEntry.is_active.is_(True))
        .scalar()
        or 0
    )

    pay_rt = _bot_runtime_status("payment_bot", db)
    loot_rt = _bot_runtime_status("loot_bot", db)
    sec_rt = _bot_runtime_status_secretary()

    stack: dict = {"available": False}
    try:
        from app.services.tbcc_stack_control import get_stack_status, stack_control_available

        if stack_control_available():
            stack = get_stack_status()
            stack["available"] = True
    except Exception:
        pass

    return {
        "scraper": {
            "authorized": bool(scraper.get("authorized")),
            "pending_login": bool(scraper.get("pending_login")),
            "user": scraper.get("user"),
            "session_file": scraper.get("session_file"),
            "error": scraper.get("error"),
        },
        "scheduler": {
            "total_posts": int(sched_total),
            "recurring_posts": int(sched_recurring),
            "pool_auto_post_enabled": pool_auto_post_enabled(),
            **collect_scheduling_health(),
            "queues": celery_queue_snapshot().get("queues") or {},
        },
        "bots": {
            "payment_bot": {
                "label": "Subscription / payment bot",
                "module": "bots.payment_bot",
                "username_env": "TBCC_PAYMENT_BOT_USERNAME",
                "username": (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@"),
                **pay_rt,
            },
            "loot_bot": {
                "label": "Loot overseer",
                "module": "bots.loot_bot",
                "username_env": "TBCC_LOOT_BOT_USERNAME",
                "username": (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@"),
                **loot_rt,
            },
            "secretary_bot": {
                "label": "Secretary / FAQ (Format Engine)",
                "module": "bots.secretary_bot",
                "username_env": "TBCC_SECRETARY_BOT_USERNAME",
                "username": (os.getenv("TBCC_SECRETARY_BOT_USERNAME") or "").strip().lstrip("@"),
                **sec_rt,
            },
        },
        "format_engine": {
            "settings": sec_eff,
            "user_contexts_total": int(ctx_total),
            "phases": {str(p or "unknown"): int(c) for p, c in phase_rows},
            "knowledge_chunks_active": int(know_active),
            "dashboard_path": "/bots",
            "dashboard_tab": "secretary",
        },
        "stack": stack,
    }
