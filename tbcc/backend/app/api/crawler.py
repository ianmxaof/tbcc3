from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.crawler_resolver import resolve_crawler_url
from app.services import myjd_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CrawlerResolveBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=8192)
    adapter: Literal["auto", "erome", "bunkr", "onlyfans", "madeporn", "generic"] = "auto"
    limit: int = Field(default=500, ge=1, le=2000)
    cookies: str | None = Field(
        default=None,
        max_length=16000,
        description="Browser cookie header for sites requiring login (e.g. OnlyFans). "
        "The extension collects these ephemerally from chrome.cookies; they are never stored.",
    )


@router.post("/resolve")
async def resolve(body: CrawlerResolveBody):
    """
    Resolve a source page into direct media URLs.

    This is the JDownloader-like layer: use site-specific crawling when the
    extension's live DOM/network scan cannot discover downloadable media.

    For authenticated sites (OnlyFans, etc.), the extension can pass the
    browser's session cookies in the ``cookies`` field. These are used for
    the single request and never persisted.
    """
    try:
        result = await resolve_crawler_url(
            body.url,
            adapter=body.adapter,
            limit=body.limit,
            cookies=body.cookies,
        )
        items = result.get("items") if isinstance(result, dict) else getattr(result, "items", None)
        count = len(items or [])
        adapter_used = result.get("adapter") if isinstance(result, dict) else getattr(result, "adapter", body.adapter)
        if myjd_service.myjd_enabled() and myjd_service.should_use_myjd_for_url(
            body.url, local_adapter=str(adapter_used or ""), local_count=count
        ):
            try:
                jd_items = await myjd_service.myjd_resolve_page(body.url)
                if jd_items:
                    merged = result if isinstance(result, dict) else asdict(result)
                    merged["adapter"] = "myjd+" + str(merged.get("adapter") or "auto")
                    merged["items"] = [
                        {
                            "url": it.url,
                            "media_type": "video"
                            if any(it.url.lower().endswith("." + e) for e in ("mp4", "webm", "mkv", "m4v", "mov"))
                            else "image",
                            "filename": it.name,
                            "thumbnail_url": None,
                        }
                        for it in jd_items
                    ]
                    w = list(merged.get("warnings") or [])
                    w.append(f"Resolved via JDownloader ({len(jd_items)} link(s))")
                    merged["warnings"] = w
                    return merged
            except Exception as e:
                logger.warning("MyJD fallback after local crawl failed: %s", e)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("crawler resolve failed url=%s adapter=%s", body.url[:180], body.adapter)
        raise HTTPException(status_code=502, detail=f"Crawler failed: {e}") from e
