"""Daily /model creator recruitment — Loot Room + random AOF lane."""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone

import httpx

from app.data.aof_network import AOF_NETWORK_CHANNELS, MAIN_GROUP_IDENT
from app.services.loot_creator_recruitment_posts import (
    ALL_VARIANTS,
    build_creator_recruitment_html,
    creator_recruitment_keyboard,
    pick_variant_for_day,
)
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

# Content lanes eligible for random daily blast (not main loot room, not packs-only).
_RANDOM_LANE_KEYS: tuple[str, ...] = (
    "ai",
    "blowjob",
    "big_tits",
    "taboo",
    "voyeur",
    "ass",
    "milf",
    "abg",
    "goon",
    "bop",
)


def _target_hour(env_key: str, default: int) -> int:
    raw = (os.getenv(env_key) or str(default)).strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return default


def _resolve_loot_token() -> str | None:
    from app.database.session import SessionLocal
    from app.services.loot_bot_settings_effective import resolve_bot_token_raw

    db = SessionLocal()
    try:
        return resolve_bot_token_raw(db)
    finally:
        db.close()


def _send_photo_or_message(
    *,
    token: str,
    chat_id: int,
    text: str,
    image_path: str | None = None,
) -> bool:
    import json

    keyboard = {"inline_keyboard": creator_recruitment_keyboard()}
    if image_path and os.path.isfile(image_path):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with httpx.Client(timeout=60) as client:
            with open(image_path, "rb") as fh:
                r = client.post(
                    url,
                    data={
                        "chat_id": str(chat_id),
                        "caption": text,
                        "parse_mode": "HTML",
                        "reply_markup": json.dumps(keyboard),
                    },
                    files={"photo": fh},
                )
        if r.status_code != 200:
            logger.warning("Creator recruitment photo send failed: %s %s", r.status_code, r.text)
            return False
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "reply_markup": keyboard,
    }
    with httpx.Client(timeout=30) as client:
        r = client.post(url, json=payload)
    if r.status_code != 200:
        logger.warning("Creator recruitment send failed: %s %s", r.status_code, r.text)
        return False
    return True


def _creator_image_path() -> str | None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for name in (
        "docs/samples/loot_creator_recruitment/images/creator_v4_orange.png",
        "docs/samples/loot_creator_recruitment/images/creator_reveal_board.png",
    ):
        p = root / name
        if p.is_file():
            return str(p)
    return None


def _mirror_x_if_enabled(*, variant: str) -> None:
    if (os.getenv("TBCC_CREATOR_RECRUITMENT_BUFFER_MIRROR") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    try:
        from app.database.session import SessionLocal
        from app.services.loot_buffer_mirror import mirror_creator_recruitment_to_buffer

        db = SessionLocal()
        try:
            mirror_creator_recruitment_to_buffer(db, variant=variant)
        finally:
            db.close()
    except Exception:
        logger.exception("Creator recruitment Buffer/X mirror failed")


def _post_loot_room(*, force: bool = False) -> None:
    hour = _target_hour("TBCC_CREATOR_RECRUITMENT_LOOT_HOUR_UTC", 14)
    now_h = datetime.now(timezone.utc).hour
    if not force and now_h != hour:
        return

    token = _resolve_loot_token()
    if not token:
        logger.warning("Creator recruitment: loot bot token missing")
        return

    variant = pick_variant_for_day()
    text = build_creator_recruitment_html(variant=variant)
    chat_id = int(MAIN_GROUP_IDENT)
    ok = _send_photo_or_message(
        token=token,
        chat_id=chat_id,
        text=text,
        image_path=_creator_image_path(),
    )
    if ok:
        logger.info("Creator recruitment sent to loot room variant=%s", variant)
        _mirror_x_if_enabled(variant=variant)


def _post_random_lane(*, force: bool = False) -> None:
    hour = _target_hour("TBCC_CREATOR_RECRUITMENT_LANE_HOUR_UTC", 20)
    now_h = datetime.now(timezone.utc).hour
    if not force and now_h != hour:
        return

    token = _resolve_loot_token()
    if not token:
        return

    # Stable pseudo-random lane per UTC day (same lane all day, rotates daily).
    day_seed = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
    rng = random.Random(day_seed)
    key = rng.choice(_RANDOM_LANE_KEYS)
    ch = next((c for c in AOF_NETWORK_CHANNELS if c.key == key), None)
    if ch is None:
        logger.warning("Creator recruitment random lane: unknown key %s", key)
        return

    # Offset variant from loot-room pick so lanes see different copy same day.
    idx = (int(datetime.now(timezone.utc).strftime("%j")) + 3) % len(ALL_VARIANTS)
    variant = ALL_VARIANTS[idx]
    text = build_creator_recruitment_html(variant=variant)
    text = f"<i>Cross-post · {html_escape(ch.display_name)}</i>\n\n{text}"

    ok = _send_photo_or_message(
        token=token,
        chat_id=int(ch.identifier),
        text=text,
        image_path=_creator_image_path(),
    )
    if ok:
        logger.info("Creator recruitment sent to lane=%s variant=%s", key, variant)


def html_escape(s: str) -> str:
    import html

    return html.escape(s)


@celery.task(name="app.workers.loot_creator_recruitment_worker.send_loot_room_creator_recruitment")
def send_loot_room_creator_recruitment(force: bool = False):
    """Daily /model intake post in AOF LOOT ROOM (default 14:00 UTC)."""
    _post_loot_room(force=force)


@celery.task(name="app.workers.loot_creator_recruitment_worker.send_random_lane_creator_recruitment")
def send_random_lane_creator_recruitment(force: bool = False):
    """Daily /model intake on one random content lane (default 20:00 UTC)."""
    _post_random_lane(force=force)
