"""Public click beacon + Zeus admin create/list."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services import click_beacon as cb

# Public hit route (allowlisted when TBCC_API_REQUIRE_INTERNAL=1)
public_router = APIRouter(tags=["click-beacon"])

# Authenticated Zeus surface (same internal key as rest of API)
zeus_router = APIRouter(prefix="/zeus/v1", tags=["zeus-v1"])


class ClickLinkCreateBody(BaseModel):
    destination_url: str = Field(..., min_length=8, max_length=2048)
    label: str | None = Field(None, max_length=128)
    slug: str | None = Field(None, max_length=32)


@zeus_router.post("/click-links")
def create_click_link(body: ClickLinkCreateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = cb.create_click_link(
            db,
            destination_url=body.destination_url,
            label=body.label,
            slug=body.slug,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "link": cb.link_as_dict(row)}


@zeus_router.get("/click-links")
def list_click_links(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = cb.list_click_links(db, limit=limit)
    return {"ok": True, "links": [cb.link_as_dict(r) for r in rows]}


@zeus_router.get("/click-links/{slug}/hits")
def list_click_hits(
    slug: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    link = cb.get_by_slug(db, slug)
    if not link:
        # Also allow inactive for ops read
        from app.models.click_link import ClickLink

        link = db.query(ClickLink).filter(ClickLink.slug == slug).one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="not_found")
    from app.models.click_link import ClickLinkHit

    hits = (
        db.query(ClickLinkHit)
        .filter(ClickLinkHit.link_id == int(link.id))
        .order_by(ClickLinkHit.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "ok": True,
        "link": cb.link_as_dict(link),
        "hits": [
            {
                "id": h.id,
                "campaign_id": h.campaign_id,
                "ip": h.ip,
                "user_agent": h.user_agent,
                "referer": h.referer,
                "country": h.country,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in hits
        ],
    }


@public_router.get("/r/{slug}")
def click_beacon_hit(
    slug: str,
    request: Request,
    id: str | None = Query(None, alias="id"),
    db: Session = Depends(get_db),
):
    """iplogger-inspired: log hit → notify admin → 302 to destination. No geox."""
    link = cb.get_by_slug(db, slug)
    if not link:
        raise HTTPException(status_code=404, detail="not_found")
    ip = (
        (request.headers.get("cf-connecting-ip") or "").strip()
        or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )
    if not cb.rate_limit_ip(ip or "unknown"):
        raise HTTPException(status_code=429, detail="rate_limited")
    ua = (request.headers.get("user-agent") or "")[:512]
    referer = (request.headers.get("referer") or request.headers.get("referrer") or "")[:512]
    country = (
        (request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country") or "")
        .strip()
        .upper()[:8]
        or None
    )
    hit = cb.record_hit(
        db,
        link,
        ip=ip,
        user_agent=ua,
        referer=referer or None,
        country=country,
        campaign_id=id,
    )
    cb.notify_admin_click(link, hit)
    return RedirectResponse(url=link.destination_url, status_code=302)
