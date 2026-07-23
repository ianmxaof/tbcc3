"""Celery offload for loot reveal MP4 encode (island worker CPU)."""

from __future__ import annotations

import logging
import random

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.loot_reveal_video_worker.compose_reveal_card_mp4_task")
def compose_reveal_card_mp4_task(
    card_jpeg: bytes,
    *,
    seed: int | None = None,
    background_name: str | None = None,
) -> dict:
    from app.services.loot_reveal_video import (
        backgrounds_dir,
        compose_reveal_card_mp4,
        loot_reveal_video_enabled,
    )

    if not loot_reveal_video_enabled():
        return {"ok": False, "reason": "disabled"}
    rng = random.Random(seed) if seed is not None else None
    bg_path = None
    if background_name:
        candidate = backgrounds_dir() / background_name
        if candidate.is_file():
            bg_path = candidate
    mp4, note = compose_reveal_card_mp4(card_jpeg, rng=rng, background=bg_path)
    if not mp4:
        return {"ok": False, "reason": note}
    return {"ok": True, "note": note, "mp4_b64": __import__("base64").b64encode(mp4).decode("ascii")}
