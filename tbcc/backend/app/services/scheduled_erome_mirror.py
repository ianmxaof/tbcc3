"""Mirror a successfully sent scheduled Telegram post to Erome (watermarked album)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.erome_telegram_ingest import (
    erome_max_files_per_album,
    filter_valid_staged_files,
    upload_staged_folder,
)
from app.services.local_media_storage import read_local_media_bytes
from app.services.media_sniff import sniff_media_kind
from app.services.mega_erome_staging import erome_staging_dir
from app.services.scheduled_buffer_mirror import _sent_slot_index
from app.services.promo_storage import promo_path_from_public_url
from app.services.scheduled_post_service import (
    _album_order_mode_for_send,
    _gather_media_items_for_send,
    _resolve_variant_sources,
)
from app.services.telegram_html_plain import telegram_html_to_plain

logger = logging.getLogger(__name__)


def erome_mirror_env_enabled() -> bool:
    return (os.getenv("TBCC_EROME_MIRROR_ON_SCHEDULED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _album_title_from_post(post: ScheduledTextPost) -> str:
    html = (getattr(post, "last_sent_caption_html", None) or post.content or "").strip()
    plain = telegram_html_to_plain(html, max_len=500)
    if plain:
        first = plain.split("\n", 1)[0].strip()
        if first:
            return first[:120]
    name = (post.name or "").strip()
    return name[:120] if name else "AOF Network"


def stage_scheduled_post_for_erome(post: ScheduledTextPost, db: Session) -> tuple[Path, list[Path]]:
    slot = _sent_slot_index(post)
    album_order_mode = _album_order_mode_for_send(post, reshuffle_album=False)
    mids, promo_urls, use_pool = _resolve_variant_sources(post, slot)
    media_items = _gather_media_items_for_send(post, db, mids, use_pool, album_order_mode)

    folder = erome_staging_dir() / "scheduled" / f"post_{int(post.id)}_{slot}"
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    lim = erome_max_files_per_album()

    for idx, media in enumerate(media_items):
        if len(paths) >= lim:
            break
        data = read_local_media_bytes(media)
        if not data or len(data) < 200:
            continue
        _kind, ext = sniff_media_kind(data)
        hint = str(getattr(media, "media_type", "") or "photo").lower()
        if ext == "bin":
            ext = "mp4" if hint == "video" else "jpg"
        path = folder / f"{idx:03d}_{int(media.id)}.{ext}"
        path.write_bytes(data)
        paths.append(path)

    if not paths:
        for u in promo_urls or []:
            if len(paths) >= lim:
                break
            p = promo_path_from_public_url(str(u))
            if not p:
                continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if len(data) < 200:
                continue
            _kind, ext = sniff_media_kind(data)
            if ext == "bin":
                ext = p.suffix.lstrip(".") or "jpg"
            path = folder / f"{len(paths):03d}_promo.{ext}"
            path.write_bytes(data)
            paths.append(path)

    valid, skipped = filter_valid_staged_files(paths)
    if skipped:
        logger.info("erome mirror skipped invalid staged files post=%s: %s", post.id, skipped[:5])
    return folder, valid[:lim]


def mirror_scheduled_post_to_erome_sync(post_id: int) -> dict[str, Any]:
    from app.database.session import SessionLocal
    from app.services.erome_upload_provision import load_flow_config, selectors_ready

    if not erome_mirror_env_enabled():
        return {"ok": False, "skipped": True, "reason": "TBCC_EROME_MIRROR_ON_SCHEDULED=0"}
    if not selectors_ready(load_flow_config()):
        return {"ok": False, "skipped": True, "reason": "erome_flow_not_configured"}

    db = SessionLocal()
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
        if not post:
            return {"ok": False, "error": "post missing"}
        if not bool(getattr(post, "erome_mirror_enabled", False)):
            return {"ok": False, "skipped": True, "reason": "erome_mirror_disabled"}

        folder, files = stage_scheduled_post_for_erome(post, db)
        if not files:
            return {"ok": False, "error": "no_staged_media", "staging_path": str(folder)}

        title = _album_title_from_post(post)
        result = upload_staged_folder(
            folder,
            title=title,
            source=f"scheduled_post:{post.id}",
            force_policy=False,
            db=db,
        )
        body = result.to_dict()
        body["ok"] = bool(result.ok)
        body["post_id"] = int(post.id)
        if result.ok:
            logger.info(
                "erome mirror published post=%s url=%s files=%s",
                post.id,
                result.album_url,
                len(files),
            )
            try:
                from app.services.content_performance import latest_telegram_delivery_for_scheduled_post, record_surface_delivery_metric

                parent = latest_telegram_delivery_for_scheduled_post(db, int(post.id))
                if parent and result.album_url:
                    record_surface_delivery_metric(
                        db,
                        parent=parent,
                        surface="erome",
                        external_post_id=str(result.album_url),
                        export_source="scheduler",
                    )
                    db.commit()
            except Exception:
                logger.debug("erome surface ledger skipped", exc_info=True)
        else:
            logger.warning("erome mirror failed post=%s error=%s", post.id, result.error)
        return body
    finally:
        db.close()
