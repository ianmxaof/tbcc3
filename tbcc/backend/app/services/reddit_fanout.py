"""Reddit fan-out after Telegram scheduled send."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.reddit_post_service import fanout_reddit_teaser
from app.services.telegram_html_plain import telegram_html_to_plain

logger = logging.getLogger(__name__)

_EROME_RE = re.compile(r"https?://(?:www\.)?erome\.com/a/[A-Za-z0-9_-]+", re.I)


def reddit_mirror_env_enabled() -> bool:
    return (os.getenv("TBCC_REDDIT_MIRROR_ON_SCHEDULED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def extract_erome_url(text: str) -> str | None:
    m = _EROME_RE.search(text or "")
    return m.group(0) if m else None


def teaser_from_post(post: ScheduledTextPost) -> str:
    html = (getattr(post, "last_sent_caption_html", None) or post.content or "").strip()
    plain = telegram_html_to_plain(html, max_len=500)
    return plain[:280] if plain else "AOF Network drop"


def run_reddit_mirror_for_scheduled_post(db: Session, post: ScheduledTextPost) -> dict[str, Any]:
    if not reddit_mirror_env_enabled():
        return {"ok": False, "skipped": True, "reason": "TBCC_REDDIT_MIRROR_ON_SCHEDULED=0"}
    if not bool(getattr(post, "reddit_mirror_enabled", False)):
        return {"ok": False, "skipped": True, "reason": "reddit_mirror_disabled"}

    teaser = teaser_from_post(post)
    erome = extract_erome_url(post.content or "") or extract_erome_url(
        getattr(post, "last_sent_caption_html", None) or ""
    )
    if erome:
        teaser = f"New gallery — {erome}"

    limit = 1
    raw = (os.getenv("TBCC_REDDIT_FANOUT_LIMIT") or "1").strip()
    try:
        limit = max(1, min(3, int(raw)))
    except ValueError:
        pass

    results = fanout_reddit_teaser(
        db,
        teaser=teaser,
        utm_campaign=f"sched_{post.id}",
        limit=limit,
        erome_url=erome,
        image_urls=_promo_urls_from_post(post),
    )
    ok = any(r.get("ok") for r in results)
    return {"ok": ok, "results": results}


def _promo_urls_from_post(post: ScheduledTextPost) -> list[str]:
    urls: list[str] = []
    try:
        for u in post._urls_from_attachment_urls_json_column() or []:
            if str(u).startswith("https://"):
                urls.append(str(u).strip())
    except Exception:
        pass
    return urls[:4]
