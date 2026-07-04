"""Main-group post dividers — ornamental spacer images between feed posts."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.main_channel_post_divider import (
    MAX_IMAGES,
    _ensure_row,
    _parse_images,
    _serialize_images,
    get_main_channel_divider_public,
)
from app.services.emoji_factory_divider_sources import (
    emoji_factory_preview_png,
    import_emoji_factory_row_as_divider,
    import_emoji_factory_tile_as_divider,
    list_emoji_factory_divider_sources,
)
from app.services.post_divider_storage import post_divider_image_path, save_post_divider_image

router = APIRouter()


class MainChannelDividerPatch(BaseModel):
    enabled: bool | None = None
    rotate_images: bool | None = None
    apply_in_topics: bool | None = None
    active_image_id: str | None = Field(None, max_length=64)


class MainChannelDividerLabelPatch(BaseModel):
    label: str = ""


class ImportEmojiFactoryDividerBody(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=32)
    tile: str | None = Field(default=None, max_length=64, description="tile_00_00 or normalized")
    row: int | None = Field(default=None, ge=0, le=32, description="grid row index for stitched strip export")
    label: str = Field("", max_length=64)


@router.get("/emoji-factory-sources")
def get_emoji_factory_divider_sources():
    return {"jobs": list_emoji_factory_divider_sources()}


@router.get("/emoji-factory-preview/{job_id}/{tile}")
def get_emoji_factory_divider_preview(job_id: str, tile: str):
    try:
        png = emoji_factory_preview_png(job_id, tile)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return Response(content=png, media_type="image/png")


@router.post("/import-from-emoji-factory")
def import_divider_from_emoji_factory(body: ImportEmojiFactoryDividerBody, db: Session = Depends(get_db)):
    try:
        if body.row is not None:
            result = import_emoji_factory_row_as_divider(
                db,
                job_id=body.job_id.strip(),
                row=int(body.row),
                label=body.label,
            )
        elif body.tile:
            result = import_emoji_factory_tile_as_divider(
                db,
                job_id=body.job_id.strip(),
                tile=body.tile.strip(),
                label=body.label,
            )
        else:
            raise HTTPException(status_code=400, detail="tile or row required")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {**result, "settings": get_main_channel_divider_public(db)}


@router.get("")
def get_main_channel_divider(db: Session = Depends(get_db)):
    return {"settings": get_main_channel_divider_public(db)}


@router.patch("")
def patch_main_channel_divider(body: MainChannelDividerPatch, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.rotate_images is not None:
        row.rotate_images = bool(body.rotate_images)
    if body.apply_in_topics is not None:
        row.apply_in_topics = bool(body.apply_in_topics)
    if body.active_image_id is not None:
        aid = (body.active_image_id or "").strip() or None
        images = _parse_images(row.images_json)
        if aid and not any(i["id"] == aid for i in images):
            raise HTTPException(status_code=400, detail="active_image_id not found")
        row.active_image_id = aid
    db.commit()
    return {"ok": True, "settings": get_main_channel_divider_public(db)}


@router.post("/images")
async def upload_main_channel_divider_image(
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
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_IMAGES} divider images")
    try:
        image_id, fname, _ = save_post_divider_image(raw, file.filename or "divider.png")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    images.append({"id": image_id, "filename": fname, "label": (label or "").strip()[:64]})
    row.images_json = _serialize_images(images)
    if not row.active_image_id:
        row.active_image_id = image_id
    db.commit()
    pub = get_main_channel_divider_public(db)
    img = next((i for i in pub["images"] if i["id"] == image_id), None)
    return {"ok": True, "image": img, "settings": pub}


@router.delete("/images/{image_id}")
def delete_main_channel_divider_image(image_id: str, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    images = _parse_images(row.images_json)
    kept = []
    removed = None
    for img in images:
        if img["id"] == image_id:
            removed = img
            p = post_divider_image_path(img["filename"])
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
    return {"ok": True, "settings": get_main_channel_divider_public(db)}


@router.patch("/images/{image_id}")
def patch_main_channel_divider_image_label(
    image_id: str,
    body: MainChannelDividerLabelPatch,
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
    return {"ok": True, "settings": get_main_channel_divider_public(db)}
