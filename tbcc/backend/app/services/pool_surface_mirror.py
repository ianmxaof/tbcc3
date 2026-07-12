"""Thin pool-post mirrors for export flywheel (env-gated)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.post_delivery_metric import PostDeliveryMetric
from app.services.erome_telegram_ingest import filter_valid_staged_files, upload_staged_folder
from app.services.local_media_storage import read_local_media_bytes
from app.services.media_sniff import sniff_media_kind
from app.services.mega_erome_staging import erome_staging_dir

logger = logging.getLogger(__name__)


def _stage_media_ids(db: Session, pool_id: int, media_ids: list[int]) -> tuple[Path, list[Path]]:
    rows = db.query(Media).filter(Media.id.in_([int(x) for x in media_ids])).all()
    order = {int(mid): i for i, mid in enumerate(media_ids)}
    rows.sort(key=lambda m: order.get(int(m.id), 999999))
    folder = erome_staging_dir() / "pool" / f"pool_{int(pool_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for idx, media in enumerate(rows):
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
    valid, _skipped = filter_valid_staged_files(paths)
    return folder, valid


def mirror_pool_media_to_erome(
    db: Session,
    *,
    pool_id: int,
    media_ids: list[int],
    network_key: str | None = None,
) -> dict[str, Any]:
    from app.services.erome_upload_provision import load_flow_config, selectors_ready

    if not selectors_ready(load_flow_config()):
        return {"ok": False, "skipped": True, "reason": "erome_flow_not_configured"}
    folder, files = _stage_media_ids(db, pool_id, media_ids)
    if not files:
        return {"ok": False, "error": "no_staged_media"}
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    title = (pool.name or f"pool_{pool_id}")[:120] if pool else f"pool_{pool_id}"
    result = upload_staged_folder(
        folder,
        title=title,
        source=f"pool:{pool_id}",
        force_policy=False,
        db=db,
    )
    body = result.to_dict()
    body["ok"] = bool(result.ok)
    if result.album_url:
        body["album_url"] = result.album_url
    if network_key:
        body["network_key"] = network_key
    return body


def mirror_pool_delivery_to_buffer(
    db: Session,
    *,
    pool_id: int,
    parent: PostDeliveryMetric | None,
    network_key: str | None = None,
    erome_album_url: str | None = None,
) -> dict[str, Any]:
    from app.data.aof_network import network_channel_by_key
    from app.services.buffer_flywheel_copy import build_flywheel_x_caption, pick_flywheel_promo_image
    from app.services.buffer_graphql import buffer_target_channel_ids, create_post, scheduled_buffer_share_mode
    from app.services.buffer_post_result import buffer_create_post_id, buffer_create_post_succeeded

    ids = buffer_target_channel_ids()
    if not ids:
        return {"ok": False, "error": "no buffer channel ids"}
    net = network_channel_by_key(network_key) if network_key else None
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    lane = (net.display_name if net else (pool.name if pool else f"pool {pool_id}")).strip()
    invite = (net.invite if net else "") or ""
    image_url, viewer_url = pick_flywheel_promo_image()
    text = build_flywheel_x_caption(
        lane,
        erome_album_url=erome_album_url,
        telegram_invite=invite or None,
        promo_viewer_url=viewer_url,
        db=db,
        advance_link_cycle=True,
    )
    share_mode = scheduled_buffer_share_mode(buffer_publish_now=False)
    res = create_post(ids[0], text, mode=share_mode, image_url=image_url)
    ok = buffer_create_post_succeeded(res)
    post_id = buffer_create_post_id(res)
    return {
        "ok": ok,
        "post_id": post_id,
        "channel_id": ids[0],
        "image_url": image_url,
        "erome_album_url": erome_album_url,
    }
