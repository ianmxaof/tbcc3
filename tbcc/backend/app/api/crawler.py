from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.crawler_resolver import resolve_crawler_url

logger = logging.getLogger(__name__)

router = APIRouter()


class CrawlerResolveBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=8192)
    adapter: Literal["auto", "erome"] = "auto"
    limit: int = Field(default=250, ge=1, le=500)


@router.post("/resolve")
async def resolve(body: CrawlerResolveBody):
    """
    Resolve a source page into direct media URLs.

    This is the JDownloader-like layer: use site-specific crawling when the
    extension's live DOM/network scan cannot discover downloadable media.
    """
    try:
        return await resolve_crawler_url(body.url, adapter=body.adapter, limit=body.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("crawler resolve failed url=%s adapter=%s", body.url[:180], body.adapter)
        raise HTTPException(status_code=502, detail=f"Crawler failed: {e}") from e
