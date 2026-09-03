"""Repost Storage Hub control panels at the bottom after operator activity."""

from __future__ import annotations

import logging
from typing import Any

from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID, STORAGE_HUB_IDENT
from app.services.storage_topic_deposit import storage_hub_chat_id_int

logger = logging.getLogger(__name__)


def is_qa_intake_thread(message_thread_id: int | None) -> bool:
    qa = int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
    if message_thread_id is None:
        # Bot API omits thread id only for General (topic 1 / renamed Q&A).
        return qa <= 1
    return int(message_thread_id) == qa


async def repost_panels_after_deposit(
    bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_title: str,
    network_key: str | None = None,
) -> dict[str, Any]:
    """
    Keep lane + Q&A master panels at the bottom of the active subtopic after a deposit.
    Deletes stale singleton copies and posts fresh messages (no pin by default).
    """
    if int(chat_id) != storage_hub_chat_id_int():
        return {"ok": True, "skipped": True, "reason": "not_storage_hub"}

    out: dict[str, Any] = {"ok": True, "panels": []}
    tid = int(message_thread_id) if message_thread_id is not None else None

    try:
        from app.services.storage_deposit_panel_pins import ensure_storage_deposit_panel

        if tid and not is_qa_intake_thread(tid):
            lane = await ensure_storage_deposit_panel(
                bot,
                chat_id=int(chat_id),
                message_thread_id=tid,
                topic_title=topic_title or "",
                force_new=False,
            )
            out["panels"].append({"kind": "lane", **lane})
    except Exception as e:
        logger.warning("lane panel repost failed thread=%s: %s", tid, e, exc_info=True)
        out["panels"].append({"kind": "lane", "ok": False, "error": str(e)[:200]})

    try:
        from app.services.qa_master_panel import ensure_qa_master_panel_at_thread

        master_tid = tid if tid is not None else int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
        master = await ensure_qa_master_panel_at_thread(
            bot,
            chat_id=int(chat_id),
            message_thread_id=master_tid,
            force_new=False,
        )
        out["panels"].append({"kind": "qa_master", **master})
    except Exception as e:
        logger.warning("qa master repost failed thread=%s: %s", tid, e, exc_info=True)
        out["panels"].append({"kind": "qa_master", "ok": False, "error": str(e)[:200]})

    return out
