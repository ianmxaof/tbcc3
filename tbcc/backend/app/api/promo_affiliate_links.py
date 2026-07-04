"""Dashboard: curated promo / affiliate URLs for quick insert into captions."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, nullslast
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.promo_affiliate_rotation import (
    AFFILIATE_PLACEMENTS,
    affiliate_rotation_stats,
    preview_affiliates,
)
from app.services.promo_shorten import PromoShortenError, validate_and_shorten

router = APIRouter()

SORT_MODES = frozenset(
    {
        "name_asc",
        "name_desc",
        "priority_asc",
        "priority_desc",
        "expires_asc",
        "expires_desc",
        "created_desc",
        "created_asc",
    }
)


def _encode_json_list(values: list[str] | None) -> str | None:
    if not values:
        return None
    cleaned = [str(v).strip().lower() for v in values if str(v).strip()]
    if not cleaned:
        return None
    return json.dumps(cleaned)


def _decode_json_list(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x).strip() for x in data if str(x).strip()] if isinstance(data, list) else []


def _row_out(row: PromoAffiliateLink) -> "PromoAffiliateLinkOut":
    return PromoAffiliateLinkOut(
        id=row.id,
        label=row.label,
        url=row.url,
        short_url=row.short_url,
        payout_kind=row.payout_kind,
        payout_detail=row.payout_detail,
        priority_tier=row.priority_tier,
        expires_at=row.expires_at,
        active=bool(row.active),
        created_at=row.created_at,
        placements=_decode_json_list(getattr(row, "placements_json", None)),
        network_keys=_decode_json_list(getattr(row, "network_keys_json", None)),
        copy_template=getattr(row, "copy_template", None),
    )


class PromoAffiliateLinkCreate(BaseModel):
    label: str = Field(..., max_length=512)
    url: str = Field(..., min_length=4, max_length=8192)
    short_url: str | None = Field(default=None, max_length=8192)
    payout_kind: str = Field(default="other", max_length=16)
    payout_detail: str | None = Field(default=None, max_length=64)
    priority_tier: int = Field(default=10, ge=0, le=999)
    expires_at: datetime | None = None
    active: bool = True
    placements: list[str] = Field(default_factory=lambda: ["manual_only"])
    network_keys: list[str] = Field(default_factory=list)
    copy_template: str | None = Field(default=None, max_length=1024)


class PromoAffiliateLinkPatch(BaseModel):
    label: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, min_length=4, max_length=8192)
    short_url: str | None = Field(default=None, max_length=8192)
    payout_kind: str | None = Field(default=None, max_length=16)
    payout_detail: str | None = Field(default=None, max_length=64)
    priority_tier: int | None = Field(default=None, ge=0, le=999)
    expires_at: datetime | None = None
    active: bool | None = None
    placements: list[str] | None = None
    network_keys: list[str] | None = None
    copy_template: str | None = Field(default=None, max_length=1024)


class PromoAffiliateLinkOut(BaseModel):
    id: int
    label: str
    url: str
    short_url: str | None
    payout_kind: str
    payout_detail: str | None
    priority_tier: int
    expires_at: datetime | None
    active: bool
    created_at: datetime | None
    placements: list[str] = Field(default_factory=list)
    network_keys: list[str] = Field(default_factory=list)
    copy_template: str | None = None

    class Config:
        from_attributes = True


class PromoBulkIn(BaseModel):
    items: list[PromoAffiliateLinkCreate] = Field(..., min_length=1, max_length=2000)


def _validate_placements(placements: list[str]) -> list[str]:
    out = [p.strip().lower() for p in placements if p.strip()]
    bad = [p for p in out if p not in AFFILIATE_PLACEMENTS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown placements: {', '.join(bad)}")
    return out or ["manual_only"]


def _apply_create_fields(row: PromoAffiliateLink, data: PromoAffiliateLinkCreate) -> None:
    placements = _validate_placements(data.placements)
    row.label = data.label.strip()
    row.url = data.url.strip()
    row.short_url = (data.short_url.strip()[:8192] if data.short_url and data.short_url.strip() else None)
    row.payout_kind = (data.payout_kind or "other").strip()[:16] or "other"
    row.payout_detail = (data.payout_detail.strip()[:64] if data.payout_detail else None)
    row.priority_tier = int(data.priority_tier)
    row.expires_at = data.expires_at
    row.active = bool(data.active)
    row.placements_json = _encode_json_list(placements)
    row.network_keys_json = _encode_json_list([k.strip().lower() for k in data.network_keys if k.strip()])
    row.copy_template = (data.copy_template.strip()[:1024] if data.copy_template and data.copy_template.strip() else None)


def _apply_sort(q, sort: str):
    if sort == "name_desc":
        return q.order_by(desc(PromoAffiliateLink.label))
    if sort == "priority_asc":
        return q.order_by(asc(PromoAffiliateLink.priority_tier), asc(PromoAffiliateLink.label))
    if sort == "priority_desc":
        return q.order_by(desc(PromoAffiliateLink.priority_tier), asc(PromoAffiliateLink.label))
    if sort == "expires_asc":
        return q.order_by(nullslast(asc(PromoAffiliateLink.expires_at)), asc(PromoAffiliateLink.label))
    if sort == "expires_desc":
        return q.order_by(nullslast(desc(PromoAffiliateLink.expires_at)), asc(PromoAffiliateLink.label))
    if sort == "created_asc":
        return q.order_by(asc(PromoAffiliateLink.id))
    if sort == "created_desc":
        return q.order_by(desc(PromoAffiliateLink.id))
    return q.order_by(asc(PromoAffiliateLink.label))


@router.get("/placements")
def list_affiliate_placements() -> dict[str, list[str]]:
    return {"placements": sorted(AFFILIATE_PLACEMENTS)}


@router.get("/stats")
def promo_affiliate_stats(db: Session = Depends(get_db)) -> dict:
    return affiliate_rotation_stats(db)


@router.get("/preview-rotation")
def get_preview_rotation(
    placement: str = Query(..., min_length=3, max_length=32),
    network_key: str | None = Query(default=None, max_length=32),
    count: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    placement = placement.strip().lower()
    if placement not in AFFILIATE_PLACEMENTS:
        raise HTTPException(status_code=400, detail=f"Unknown placement: {placement}")
    picks = preview_affiliates(db, placement, network_key=network_key, count=count)
    return {"placement": placement, "network_key": network_key, "picks": picks}


@router.get("/", response_model=list[PromoAffiliateLinkOut])
def list_promo_affiliate_links(
    sort: str = Query(default="priority_asc"),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    if sort not in SORT_MODES:
        sort = "priority_asc"
    q = db.query(PromoAffiliateLink)
    if active_only:
        q = q.filter(PromoAffiliateLink.active.is_(True))
    q = _apply_sort(q, sort)
    rows = q.all()
    return [_row_out(r) for r in rows]


@router.post("/", response_model=PromoAffiliateLinkOut)
def create_promo_affiliate_link(data: PromoAffiliateLinkCreate, db: Session = Depends(get_db)):
    row = PromoAffiliateLink()
    _apply_create_fields(row, data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.post("/bulk", response_model=dict)
def bulk_create_promo_affiliate_links(data: PromoBulkIn, db: Session = Depends(get_db)):
    """Commit in chunks so SQLite stays under bind-parameter limits and huge batches don't single-flush."""
    n = 0
    pending = 0
    chunk_size = 50
    for it in data.items:
        url = str(it.url or "").strip()
        label = str(it.label or "").strip()
        if not url or not label:
            continue
        row = PromoAffiliateLink()
        _apply_create_fields(row, it)
        db.add(row)
        n += 1
        pending += 1
        if pending >= chunk_size:
            db.commit()
            pending = 0
    if pending:
        db.commit()
    return {"created": n}


@router.patch("/{link_id}", response_model=PromoAffiliateLinkOut)
def patch_promo_affiliate_link(link_id: int, data: PromoAffiliateLinkPatch, db: Session = Depends(get_db)):
    row = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.id == link_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if data.label is not None:
        row.label = data.label.strip()[:512]
    if data.url is not None:
        row.url = data.url.strip()[:8192]
    if data.short_url is not None:
        s = data.short_url.strip()
        row.short_url = s[:8192] if s else None
    if data.payout_kind is not None:
        row.payout_kind = data.payout_kind.strip()[:16] or "other"
    if data.payout_detail is not None:
        row.payout_detail = data.payout_detail.strip()[:64] if data.payout_detail.strip() else None
    if data.priority_tier is not None:
        row.priority_tier = int(data.priority_tier)
    if data.expires_at is not None:
        row.expires_at = data.expires_at
    if data.active is not None:
        row.active = bool(data.active)
    if data.placements is not None:
        row.placements_json = _encode_json_list(_validate_placements(data.placements))
    if data.network_keys is not None:
        row.network_keys_json = _encode_json_list([k.strip().lower() for k in data.network_keys if k.strip()])
    if data.copy_template is not None:
        s = data.copy_template.strip()
        row.copy_template = s[:1024] if s else None
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.delete("/{link_id}")
def delete_promo_affiliate_link(link_id: int, db: Session = Depends(get_db)):
    row = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.id == link_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": link_id}


@router.post("/{link_id}/shorten", response_model=PromoAffiliateLinkOut)
def shorten_promo_affiliate_link(link_id: int, db: Session = Depends(get_db)):
    """Fill short_url via TBCC_PROMO_SHORTEN_PROVIDER (isgd | tinyurl). Requires outbound HTTPS from API."""
    row = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.id == link_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        short = validate_and_shorten(row.url)
    except PromoShortenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    row.short_url = short.strip()[:8192]
    db.commit()
    db.refresh(row)
    return _row_out(row)
