"""Global zip promo insert: readme + image inside gallery zips and uploaded bundle zips."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.zip_bundle_settings import ZipBundleSettings
from app.services.zip_promo_inject import get_effective_zip_promo_settings
from app.services.zip_promo_storage import save_zip_promo_image, zip_promo_image_path

router = APIRouter()

ROW_ID = 1


class ZipBundleSettingsPatch(BaseModel):
    enabled: bool | None = None
    include_text_file: bool | None = None
    text_filename: str | None = Field(None, max_length=128)
    text_body: str | None = None
    include_image: bool | None = None
    clear_image: bool | None = None


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _row_public(db: Session) -> dict[str, Any]:
    eff = get_effective_zip_promo_settings(db)
    img_fn = eff.get("image_filename")
    image_url = None
    if img_fn and eff.get("has_image_on_disk"):
        image_url = f"{_public_base_url()}/static/zip-promo/{img_fn}"
    return {
        **eff,
        "image_url": image_url,
    }


def _ensure_row(db: Session) -> ZipBundleSettings:
    r = db.query(ZipBundleSettings).filter(ZipBundleSettings.id == ROW_ID).first()
    if r:
        return r
    r = ZipBundleSettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("")
def get_zip_bundle_settings(db: Session = Depends(get_db)):
    _ensure_row(db)
    return {"settings": _row_public(db)}


@router.get("/extension-payload")
def get_zip_bundle_extension_payload(db: Session = Depends(get_db)):
    """Lightweight payload for gallery JSZip (text inline; image via URL)."""
    s = _row_public(db)
    if not s.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "include_text_file": s.get("include_text_file"),
        "include_image": s.get("include_image"),
        "text_filename": s.get("text_filename"),
        "text_body": s.get("text_body") if s.get("include_text_file") else "",
        "image_filename": s.get("image_filename"),
        "image_url": s.get("image_url"),
    }


@router.patch("")
def patch_zip_bundle_settings(body: ZipBundleSettingsPatch, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    data = body.model_dump(exclude_unset=True)
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "include_text_file" in data and data["include_text_file"] is not None:
        row.include_text_file = bool(data["include_text_file"])
    if "text_filename" in data and data["text_filename"] is not None:
        fn = str(data["text_filename"]).strip()
        if fn and "/" not in fn and "\\" not in fn:
            row.text_filename = fn[:128]
    if "text_body" in data:
        row.text_body = (str(data["text_body"] or "").strip() or None)
    if "include_image" in data and data["include_image"] is not None:
        row.include_image = bool(data["include_image"])
    if data.get("clear_image"):
        fn = (row.image_filename or "").strip()
        if fn:
            p = zip_promo_image_path(fn)
            if p:
                p.unlink(missing_ok=True)
        row.image_filename = None
    db.commit()
    db.refresh(row)
    return {"ok": True, "settings": _row_public(db)}


@router.post("/promo-image")
async def upload_zip_promo_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        fname, _ = save_zip_promo_image(raw, file.filename or "promo.jpg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    row = _ensure_row(db)
    row.image_filename = fname
    row.include_image = True
    db.commit()
    return {"ok": True, "filename": fname, "url": f"{_public_base_url()}/static/zip-promo/{fname}"}
