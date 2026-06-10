"""Album composer saved workshop drafts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.album_composer_drafts import delete_draft, get_draft, list_drafts, save_draft

router = APIRouter()


class AlbumComposerDraftBody(BaseModel):
    id: str | None = None
    name: str = Field("Untitled draft", max_length=80)
    items: list[dict[str, Any]] = Field(default_factory=list)
    caption: str = ""
    buttons: list[dict[str, str]] = Field(default_factory=list)
    promo_enabled: bool = True
    send_silent: bool = False
    channel_id: int | None = None
    thread_id: int | None = None
    crop: dict[str, Any] | None = None
    watermark_skip: bool = False
    watermark_enabled: bool | None = None
    watermark_text: str = ""
    watermark_text_secondary: str = ""
    watermark_text_tertiary: str = ""
    watermark_opacity: float | None = None
    watermark_color: str | None = None
    watermark_strip_previous: bool | None = None


@router.get("")
def get_drafts() -> dict[str, Any]:
    return {"drafts": list_drafts()}


@router.get("/{draft_id}")
def get_one_draft(draft_id: str) -> dict[str, Any]:
    row = get_draft(draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"draft": row}


@router.post("")
def create_draft(body: AlbumComposerDraftBody) -> dict[str, Any]:
    row = save_draft(body.model_dump())
    return {"draft": row}


@router.patch("/{draft_id}")
def patch_draft(draft_id: str, body: AlbumComposerDraftBody) -> dict[str, Any]:
    if not get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    row = save_draft(body.model_dump(), draft_id=draft_id)
    return {"draft": row}


@router.delete("/{draft_id}")
def remove_draft(draft_id: str) -> dict[str, Any]:
    if not delete_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"ok": True}
