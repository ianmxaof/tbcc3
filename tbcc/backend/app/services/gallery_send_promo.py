"""Gallery batch send-promo settings (JSON + files on disk)."""

from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.gallery_send_promo_settings import GallerySendPromoSettings
from app.services.send_promo_storage import save_send_promo_image, send_promo_image_path

ROW_ID = 1
MAX_IMAGES = 12


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _parse_images(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "").strip()
        fn = str(item.get("filename") or "").strip()
        if not iid or not fn:
            continue
        if not send_promo_image_path(fn):
            continue
        out.append(
            {
                "id": iid,
                "filename": fn,
                "label": str(item.get("label") or "").strip()[:64],
            }
        )
    return out[:MAX_IMAGES]


def _serialize_images(images: list[dict[str, Any]]) -> str:
    slim = [{"id": i["id"], "filename": i["filename"], "label": i.get("label") or ""} for i in images[:MAX_IMAGES]]
    return json.dumps(slim)


def _ensure_row(db: Session) -> GallerySendPromoSettings:
    r = db.query(GallerySendPromoSettings).filter(GallerySendPromoSettings.id == ROW_ID).first()
    if r:
        return r
    r = GallerySendPromoSettings(id=ROW_ID, enabled=True, images_json="[]")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_gallery_send_promo_public(db: Session) -> dict[str, Any]:
    row = _ensure_row(db)
    base = _public_base_url()
    images_in = _parse_images(row.images_json)
    images: list[dict[str, Any]] = []
    for img in images_in:
        fn = img["filename"]
        images.append(
            {
                **img,
                "url": f"{base}/static/send-promo/{fn}",
            }
        )
    active_id = (row.active_image_id or "").strip() or None
    if active_id and not any(i["id"] == active_id for i in images):
        active_id = images[0]["id"] if images else None
    if not active_id and images:
        active_id = images[0]["id"]
    active = next((i for i in images if i["id"] == active_id), None)
    return {
        "enabled": bool(row.enabled),
        "active_image_id": active_id,
        "active_image": active,
        "images": images,
    }


def extension_payload(db: Session) -> dict[str, Any]:
    pub = get_gallery_send_promo_public(db)
    if not pub.get("enabled"):
        return {"enabled": False, "images": [], "active_image": None}
    return {
        "enabled": True,
        "active_image_id": pub.get("active_image_id"),
        "active_image": pub.get("active_image"),
        "images": pub.get("images") or [],
    }
