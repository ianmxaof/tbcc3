"""Build and seed buffer_x_queue armory for listening relay + scheduled posts."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.data.aof_x_buffer_armory import AOF_X_BUFFER_ARMORY_TEMPLATES
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_social_links import fill_armory_template, gravatar_avatar_image_url, buffer_ig_default_image_url
from app.services.buffer_x_caption import fit_plaintext_for_x, should_fit_for_x

logger = logging.getLogger(__name__)

RELAY_ROW_ID = 1
MAX_QUEUE = 16


def build_armory_queue_items() -> list[dict]:
    grav_img = gravatar_avatar_image_url()
    ig_img = buffer_ig_default_image_url()
    default_img = grav_img or ig_img
    out: list[dict] = []
    for i, tpl in enumerate(AOF_X_BUFFER_ARMORY_TEMPLATES):
        raw = fill_armory_template(
            str(tpl.get("text") or ""),
            utm_source="buffer",
            utm_medium="x",
            utm_campaign=str(tpl.get("utm_campaign") or tpl.get("id") or f"armory_{i}"),
            for_x=True,
        )
        if not raw:
            continue
        text = fit_plaintext_for_x(raw) if should_fit_for_x() else raw
        if len(text) > 280:
            text = text[:277].rstrip() + "…"
        entry: dict = {"text": text}
        if str(tpl.get("image") or "").strip() == "gravatar" and grav_img:
            entry["image_url"] = grav_img
        elif default_img and not entry.get("image_url"):
            entry["image_url"] = default_img
        out.append(entry)
        if len(out) >= MAX_QUEUE:
            break
    return out


def seed_relay_buffer_armory(db: Session, *, replace: bool = True) -> int:
    row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == RELAY_ROW_ID).first()
    if row is None:
        row = ListeningRelaySettings(id=RELAY_ROW_ID)
        db.add(row)
        db.flush()
    items = build_armory_queue_items()
    if not items:
        return 0
    if replace or not row.get_buffer_x_queue():
        row.set_buffer_x_queue(items)
    else:
        row.set_buffer_x_queue(row.get_buffer_x_queue() + items)
        row.set_buffer_x_queue(row.get_buffer_x_queue()[:MAX_QUEUE])
    db.commit()
    logger.info("seed_aof_buffer_armory: relay queue=%s", len(row.get_buffer_x_queue()))
    return len(items)


def seed_scheduled_buffer_armory(
    db: Session,
    *,
    post_id: int | None = None,
    replace: bool = True,
    only_mirror_enabled: bool = True,
) -> int:
    items = build_armory_queue_items()
    if not items:
        return 0
    q = db.query(ScheduledTextPost)
    if post_id is not None:
        q = q.filter(ScheduledTextPost.id == int(post_id))
    elif only_mirror_enabled:
        q = q.filter(ScheduledTextPost.buffer_mirror_enabled.is_(True))
    posts = q.all()
    n = 0
    for post in posts:
        if replace or not post.get_buffer_x_queue():
            post.set_buffer_x_queue(items)
        else:
            merged = post.get_buffer_x_queue() + items
            post.set_buffer_x_queue(merged[:MAX_QUEUE])
        n += 1
    if n:
        db.commit()
    logger.info("seed_aof_buffer_armory: scheduled posts armed=%s items_each=%s", n, len(items))
    return n
