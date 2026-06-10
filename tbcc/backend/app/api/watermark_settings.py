"""Dashboard API for promo watermark settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.watermark_settings_effective import (
    ROW_ID,
    _ensure_row,
    get_effective_watermark_settings,
    row_to_dict,
)

router = APIRouter()


class WatermarkSettingsPatch(BaseModel):
    enabled: bool | None = None
    text_primary: str | None = Field(None, max_length=120)
    text_secondary: str | None = Field(None, max_length=120)
    text_tertiary: str | None = Field(None, max_length=120)
    opacity: float | None = Field(None, ge=0.15, le=1.0)
    color: str | None = Field(None, max_length=16)
    strip_previous: bool | None = None
    apply_on_saved_import: bool | None = None
    apply_on_album_composer: bool | None = None


@router.get("")
def get_watermark_settings(db: Session = Depends(get_db)):
    row = _ensure_row(db)
    return {
        "effective": get_effective_watermark_settings(db),
        "overrides": row_to_dict(row),
        "row_id": ROW_ID,
    }


@router.patch("")
def patch_watermark_settings(body: WatermarkSettingsPatch, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    for field in (
        "enabled",
        "text_primary",
        "text_secondary",
        "text_tertiary",
        "opacity",
        "color",
        "strip_previous",
        "apply_on_saved_import",
        "apply_on_album_composer",
    ):
        val = getattr(body, field, None)
        if val is not None:
            if field.startswith("text_"):
                val = (val or "").strip()[:120] or None
            elif field == "color":
                val = (val or "").strip()[:16] or None
            setattr(row, field, val)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "effective": get_effective_watermark_settings(db),
        "overrides": row_to_dict(row),
    }
