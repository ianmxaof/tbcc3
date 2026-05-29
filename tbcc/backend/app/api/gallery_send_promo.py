"""Gallery batch send-promo: tail image on Saved Messages / channel album sends."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.gallery_send_promo import (
    MAX_IMAGES,
    _ensure_row,
    _parse_images,
    _serialize_images,
    extension_payload,
    get_gallery_send_promo_public,
)
from app.services.send_promo_storage import save_send_promo_image, send_promo_image_path

router = APIRouter()


class GallerySendPromoPatch(BaseModel):
    enabled: bool | None = None
    active_image_id: str | None = Field(None, max_length=64)


class GallerySendPromoLabelPatch(BaseModel):
    label: str = ""


@router.get("")
def get_gallery_send_promo(db: Session = Depends(get_db)):
    return {"settings": get_gallery_send_promo_public(db)}


@router.get("/extension-payload")
def get_gallery_send_promo_extension_payload(db: Session = Depends(get_db)):
    return extension_payload(db)


@router.patch("")
def patch_gallery_send_promo(body: GallerySendPromoPatch, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.active_image_id is not None:
        aid = (body.active_image_id or "").strip() or None
        images = _parse_images(row.images_json)
        if aid and not any(i["id"] == aid for i in images):
            raise HTTPException(status_code=400, detail="active_image_id not found")
        row.active_image_id = aid
    db.commit()
    return {"ok": True, "settings": get_gallery_send_promo_public(db)}


@router.post("/images")
async def upload_gallery_send_promo_image(
    file: UploadFile = File(...),
    label: str = Form(""),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    row = _ensure_row(db)
    images = _parse_images(row.images_json)
    if len(images) >= MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_IMAGES} promo images")
    try:
        image_id, fname, _ = save_send_promo_image(raw, file.filename or "promo.jpg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    images.append({"id": image_id, "filename": fname, "label": (label or "").strip()[:64]})
    row.images_json = _serialize_images(images)
    if not row.active_image_id:
        row.active_image_id = image_id
    db.commit()
    pub = get_gallery_send_promo_public(db)
    img = next((i for i in pub["images"] if i["id"] == image_id), None)
    return {"ok": True, "image": img, "settings": pub}


@router.delete("/images/{image_id}")
def delete_gallery_send_promo_image(image_id: str, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    images = _parse_images(row.images_json)
    kept = []
    removed = None
    for img in images:
        if img["id"] == image_id:
            removed = img
            p = send_promo_image_path(img["filename"])
            if p:
                p.unlink(missing_ok=True)
        else:
            kept.append(img)
    if not removed:
        raise HTTPException(status_code=404, detail="Image not found")
    row.images_json = _serialize_images(kept)
    if row.active_image_id == image_id:
        row.active_image_id = kept[0]["id"] if kept else None
    db.commit()
    return {"ok": True, "settings": get_gallery_send_promo_public(db)}


@router.patch("/images/{image_id}")
def patch_gallery_send_promo_image_label(
    image_id: str,
    body: GallerySendPromoLabelPatch,
    db: Session = Depends(get_db),
):
    label = (body.label or "").strip()[:64]
    row = _ensure_row(db)
    try:
        images = json.loads(row.images_json or "[]")
    except json.JSONDecodeError:
        images = []
    found = False
    for item in images:
        if isinstance(item, dict) and str(item.get("id")) == image_id:
            item["label"] = label
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Image not found")
    row.images_json = json.dumps(images)
    db.commit()
    return {"ok": True, "settings": get_gallery_send_promo_public(db)}
