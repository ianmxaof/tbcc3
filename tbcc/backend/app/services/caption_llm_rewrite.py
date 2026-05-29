"""When to LLM-rewrite a scheduled caption and apply rewrite."""

from __future__ import annotations

import logging
import os
import random

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.post_rewrite_llm import caption_rewrite_llm_globally_enabled, rewrite_caption_llm_sync

logger = logging.getLogger(__name__)


def _default_random_probability() -> float:
    raw = (os.environ.get("TBCC_CAPTION_LLM_REWRITE_RANDOM_PROB") or "0.25").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.25


def post_llm_rewrite_configured(post: ScheduledTextPost) -> bool:
    if not caption_rewrite_llm_globally_enabled():
        return False
    if not getattr(post, "caption_llm_rewrite_enabled", False):
        return False
    mode = (getattr(post, "caption_llm_rewrite_mode", None) or "").strip().lower()
    return mode in ("random", "interval")


def should_llm_rewrite_this_send(post: ScheduledTextPost) -> bool:
    if not post_llm_rewrite_configured(post):
        return False
    mode = (post.caption_llm_rewrite_mode or "").strip().lower()
    if mode == "random":
        prob = post.caption_llm_rewrite_probability
        if prob is None:
            prob = _default_random_probability()
        return random.random() < float(prob)
    if mode == "interval":
        interval = max(1, int(post.caption_llm_rewrite_interval or 1))
        # Next send is send_count + 1; rewrite every Nth send (N, 2N, 3N…)
        return ((int(post.caption_llm_send_count or 0) + 1) % interval) == 0
    return False


def note_llm_send_completed(post: ScheduledTextPost) -> None:
    """Call after a successful Telegram send (in-memory; caller commits)."""
    if post_llm_rewrite_configured(post):
        post.caption_llm_send_count = int(post.caption_llm_send_count or 0) + 1


def apply_llm_rewrite_if_scheduled(
    post: ScheduledTextPost,
    caption_html: str,
    db: Session,
) -> str:
    """Return caption to send (possibly LLM-rewritten)."""
    if not should_llm_rewrite_this_send(post):
        return caption_html
    try:
        out = rewrite_caption_llm_sync(caption_html)
        logger.info(
            "caption LLM rewrite post_id=%s mode=%s len %s→%s",
            post.id,
            post.caption_llm_rewrite_mode,
            len(caption_html or ""),
            len(out or ""),
        )
        return out
    except Exception as e:
        logger.warning("caption LLM rewrite failed post_id=%s: %s", post.id, e)
        return caption_html


def resolve_scheduled_caption_for_send(post: ScheduledTextPost, db: Session) -> str:
    """Rotate variations, optionally LLM-rewrite, store snapshot for Buffer mirror."""
    from app.services.scheduled_post_service import resolve_scheduled_caption

    caption = resolve_scheduled_caption(post)
    final = apply_llm_rewrite_if_scheduled(post, caption, db)
    post.last_sent_caption_html = final
    return final
