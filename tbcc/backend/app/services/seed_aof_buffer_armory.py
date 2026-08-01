"""Build and seed buffer_x_queue armory for listening relay + scheduled posts."""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.data.aof_x_buffer_armory import AOF_X_BUFFER_ARMORY_TEMPLATES
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_social_links import fill_armory_template, gravatar_avatar_image_url, buffer_ig_default_image_url
from app.services.buffer_x_hashtags import append_x_hashtags
from app.services.buffer_x_caption import finalize_buffer_x_caption, should_fit_for_x
from app.services.buffer_x_promo_image import direct_url_for_buffer, pick_promo_image
from app.services.template_expand import expand_template_tokens

logger = logging.getLogger(__name__)

RELAY_ROW_ID = 1
LEGACY_MAIN_SCHEDULER_NAME = "AOF MAIN GROUP + X SCHEDULER"


def armory_max_queue() -> int:
    raw = (os.getenv("TBCC_BUFFER_ARMORY_MAX_DEPTH") or "50").strip()
    try:
        return max(1, min(200, int(raw)))
    except ValueError:
        return 50


def _static_armory_templates() -> list[dict[str, str]]:
    return list(AOF_X_BUFFER_ARMORY_TEMPLATES)


def _armory_template_source(db: Session | None) -> list[dict[str, str]]:
    if db is not None:
        try:
            from app.services.social_copy_rotation import build_pool_entries_from_db, rotation_categories

            entries: list[dict[str, str]] = []
            for cat in rotation_categories():
                entries.extend(build_pool_entries_from_db(db, category=cat, limit=armory_max_queue()))
            if entries:
                return entries
        except Exception:
            logger.debug("armory social_copy fallback", exc_info=True)
    return _static_armory_templates()


def _banned_main_channel_id(db: Session) -> int | None:
    from app.data.aof_network import BANNED_MAIN_GROUP_IDENT

    row = db.query(Channel).filter(Channel.identifier == BANNED_MAIN_GROUP_IDENT).first()
    return int(row.id) if row else None


def _eligible_buffer_mirror_posts(db: Session, posts: list[ScheduledTextPost]) -> list[ScheduledTextPost]:
    banned_id = _banned_main_channel_id(db)
    if banned_id is None:
        return posts
    return [p for p in posts if int(p.channel_id or 0) != banned_id]


def build_armory_queue_items(*, db=None) -> list[dict]:
    grav_img = gravatar_avatar_image_url()
    ig_img = buffer_ig_default_image_url()
    default_img = grav_img or ig_img
    used_promo_urls: set[str] = set()
    out: list[dict] = []
    max_q = armory_max_queue()
    templates: list[dict[str, str]] = []
    if db is not None:
        try:
            from app.services.social_copy_rotation import pick_pool_entry

            for _ in range(max_q):
                picked = pick_pool_entry(db)
                if not picked:
                    break
                templates.append(picked)
        except Exception:
            logger.debug("armory pick_pool_entry fallback", exc_info=True)
    if not templates:
        templates = _armory_template_source(db)
    for i, tpl in enumerate(templates):
        raw_text = expand_template_tokens(str(tpl.get("text") or ""), db=db, for_x=True)
        raw = fill_armory_template(
            raw_text,
            utm_source="buffer",
            utm_medium="x",
            utm_campaign=str(tpl.get("utm_campaign") or tpl.get("id") or tpl.get("category") or f"armory_{i}"),
            for_x=True,
            db=db,
            advance_affiliate=True,
        )
        if not raw:
            continue
        text = finalize_buffer_x_caption(raw, db=db, advance_link_cycle=True) if should_fit_for_x() else raw
        text = append_x_hashtags(text, max_chars=280)
        if len(text) > 280:
            text = text[:277].rstrip() + "…"
        entry: dict = {"text": text}
        promo_direct = direct_url_for_buffer(pick_promo_image(exclude=used_promo_urls))
        if promo_direct:
            entry["image_url"] = promo_direct
            used_promo_urls.add(promo_direct)
        elif str(tpl.get("image") or "").strip() == "gravatar" and grav_img:
            entry["image_url"] = grav_img
        elif default_img and not entry.get("image_url"):
            entry["image_url"] = default_img
        out.append(entry)
        if len(out) >= max_q:
            break
    return out


def seed_relay_buffer_armory(db: Session, *, replace: bool = True) -> int:
    row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == RELAY_ROW_ID).first()
    if row is None:
        row = ListeningRelaySettings(id=RELAY_ROW_ID)
        db.add(row)
        db.flush()
    items = build_armory_queue_items(db=db)
    if not items:
        return 0
    if replace or not row.get_buffer_x_queue():
        row.set_buffer_x_queue(items)
    else:
        row.set_buffer_x_queue(row.get_buffer_x_queue() + items)
        row.set_buffer_x_queue(row.get_buffer_x_queue()[: armory_max_queue()])
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
    items = build_armory_queue_items(db=db)
    if not items:
        return 0
    q = db.query(ScheduledTextPost)
    if post_id is not None:
        q = q.filter(ScheduledTextPost.id == int(post_id))
    elif only_mirror_enabled:
        q = q.filter(ScheduledTextPost.buffer_mirror_enabled.is_(True))
    posts = q.all()
    posts = _eligible_buffer_mirror_posts(db, posts)
    n = 0
    for post in posts:
        if replace or not post.get_buffer_x_queue():
            post.set_buffer_x_queue(items)
        else:
            merged = post.get_buffer_x_queue() + items
            post.set_buffer_x_queue(merged[: armory_max_queue()])
        n += 1
    if n:
        db.commit()
    logger.info("seed_aof_buffer_armory: scheduled posts armed=%s items_each=%s", n, len(items))
    return n
