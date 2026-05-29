from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import myjd_service
logger = logging.getLogger(__name__)

router = APIRouter()


class JdAddLinksBody(BaseModel):
    links: str = Field(..., min_length=4, max_length=500_000)
    package_name: str | None = Field(default=None, max_length=200)
    autostart: bool = False


class JdResolveBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=8192)
    package_name: str | None = Field(default=None, max_length=200)
    autostart: bool = False


@router.get("/status")
async def jd_status():
    return await myjd_service.myjd_status()


@router.post("/add-links")
async def jd_add_links(body: JdAddLinksBody):
    if not myjd_service.myjd_enabled():
        raise HTTPException(
            status_code=503,
            detail="My.JDownloader not configured (TBCC_MYJD_EMAIL / TBCC_MYJD_PASSWORD in tbcc/.env)",
        )
    try:
        return await myjd_service.myjd_add_links(
            body.links,
            package_name=body.package_name,
            autostart=body.autostart,
        )
    except Exception as e:
        logger.exception("MyJD add-links failed")
        myjd_service.reset_myjd_session()
        raise HTTPException(status_code=502, detail=f"JDownloader: {e}") from e


@router.post("/resolve")
async def jd_resolve(body: JdResolveBody):
    if not myjd_service.myjd_enabled():
        raise HTTPException(status_code=503, detail="My.JDownloader not configured")
    try:
        items = await myjd_service.myjd_resolve_page(
            body.url,
            package_name=body.package_name,
            autostart=body.autostart,
        )
        def _media_type(u: str) -> str:
            low = u.lower().split("?", 1)[0]
            return "video" if any(low.endswith("." + e) for e in ("mp4", "webm", "mkv", "m4v", "mov")) else "image"

        return {
            "adapter": "myjd",
            "source_url": body.url,
            "title": None,
            "items": [
                {
                    "url": it.url,
                    "media_type": _media_type(it.url),
                    "filename": it.name,
                    "thumbnail_url": None,
                }
                for it in items
            ],
            "warnings": [] if items else ["JDownloader found no direct http(s) links for this URL"],
        }
    except Exception as e:
        logger.exception("MyJD resolve failed url=%s", body.url[:180])
        myjd_service.reset_myjd_session()
        raise HTTPException(status_code=502, detail=f"JDownloader resolve failed: {e}") from e
