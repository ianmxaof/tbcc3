"""Keep2Share library ops — lane folders, dead-link checks, mirror triggers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.keep2share_client import (
    get_files_list,
    k2s_configured,
    k2s_enabled,
)
from app.services.k2s_lane_folders import ensure_all_lane_folders, list_lane_status, mirror_enabled
from app.services.k2s_mirror_service import check_file_host_url, mirror_modifier_by_id
from fastapi import Depends

router = APIRouter()


class K2sCheckUrlBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)


class K2sMirrorBody(BaseModel):
    modifier_id: int = Field(..., ge=1)
    lane: str | None = Field(default=None, max_length=32)


@router.get("/status")
def k2s_status():
    from app.services.keep2share_client import k2s_partner_referral_urls

    return {
        "enabled": k2s_enabled(),
        "configured": k2s_configured(),
        "mirror_enabled": mirror_enabled(),
        "affiliate_urls": k2s_partner_referral_urls(),
        "lanes": list_lane_status(),
    }


@router.post("/ensure-folders")
def k2s_ensure_folders():
    if not k2s_configured():
        raise HTTPException(status_code=503, detail="k2s_not_configured")
    folders = ensure_all_lane_folders()
    return {"ok": True, "folders": folders, "lanes": list_lane_status()}


@router.get("/library")
def k2s_library(
    lane: str = Query("packs"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if not k2s_configured():
        raise HTTPException(status_code=503, detail="k2s_not_configured")
    from app.services.k2s_lane_folders import get_lane_folder_id

    folder_id = get_lane_folder_id(lane, create=False) or "/"
    files = get_files_list(parent=folder_id, limit=limit, offset=offset)
    rows: list[dict[str, Any]] = []
    for f in files:
        fid = str(f.get("id") or "")
        rows.append(
            {
                "id": fid,
                "name": f.get("name"),
                "size": f.get("size"),
                "is_folder": bool(f.get("is_folder")),
                "is_available": bool(f.get("is_available", True)),
                "date_created": f.get("date_created"),
                "public_url": f"https://k2s.cc/file/{fid}" if fid and not f.get("is_folder") else None,
            }
        )
    return {"lane": lane, "folder_id": folder_id, "files": rows, "count": len(rows)}


@router.post("/check-url")
def k2s_check_url(body: K2sCheckUrlBody):
    return check_file_host_url(body.url.strip())


@router.post("/mirror")
def k2s_mirror(body: K2sMirrorBody, db: Session = Depends(get_db)):
    if not mirror_enabled():
        raise HTTPException(status_code=503, detail="k2s_mirror_disabled")
    result = mirror_modifier_by_id(db, body.modifier_id, lane=body.lane)
    if not result.get("ok") and not result.get("skipped"):
        raise HTTPException(status_code=400, detail=result.get("error") or "mirror_failed")
    return result
