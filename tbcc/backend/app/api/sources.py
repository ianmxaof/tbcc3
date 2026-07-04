from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.source import Source
from app.models.scrape_channel_profile import ScrapeChannelProfile
from app.services.scrape_run_service import (
    list_scrape_runs,
    normalize_media_types,
    scrape_run_to_dict,
    validate_schedule_cron,
)
from app.services import scraper_telethon_auth

router = APIRouter()

SOURCE_TYPES = ("telegram_channel", "reddit", "manual")


class SourceCreate(BaseModel):
    name: str
    source_type: str = "telegram_channel"
    identifier: str
    pool_id: int
    active: bool = True
    schedule_cron: str | None = None
    schedule_enabled: bool = False
    media_types: str = "both"
    max_messages_per_run: int = Field(default=50, ge=1, le=500)


class SourceUpdate(BaseModel):
    name: str | None = None
    source_type: str | None = None
    identifier: str | None = None
    pool_id: int | None = None
    active: bool | None = None
    schedule_cron: str | None = None
    schedule_enabled: bool | None = None
    media_types: str | None = None
    max_messages_per_run: int | None = Field(default=None, ge=1, le=500)


class ScraperAuthPhoneBody(BaseModel):
    phone: str


class ScraperAuthCodeBody(BaseModel):
    code: str


class ScraperAuthPasswordBody(BaseModel):
    password: str


def _get_source_or_404(source_id: int, db: Session) -> Source:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    return s


def _source_dict(s: Source) -> dict:
    d = orm_to_dict(s)
    d["media_types"] = normalize_media_types(getattr(s, "media_types", None))
    return d


def _apply_scrape_settings(src: Source, body: SourceCreate | SourceUpdate) -> None:
    if hasattr(body, "schedule_cron") and body.schedule_cron is not None:
        src.schedule_cron = validate_schedule_cron(body.schedule_cron)
    if hasattr(body, "schedule_enabled") and body.schedule_enabled is not None:
        src.schedule_enabled = bool(body.schedule_enabled)
    if hasattr(body, "media_types") and body.media_types is not None:
        src.media_types = normalize_media_types(body.media_types)
    if hasattr(body, "max_messages_per_run") and body.max_messages_per_run is not None:
        src.max_messages_per_run = int(body.max_messages_per_run)


@router.get("/scrape-runs/latest")
def list_latest_scrape_runs(
    limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
):
    rows = list_scrape_runs(db, limit=limit)
    return [scrape_run_to_dict(r) for r in rows]


@router.get("/scraper-auth/status")
async def scraper_auth_status():
    try:
        return await scraper_telethon_auth.scraper_auth_status()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/scraper-auth/phone")
async def scraper_auth_phone(body: ScraperAuthPhoneBody):
    try:
        return await scraper_telethon_auth.scraper_send_phone(body.phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/scraper-auth/code")
async def scraper_auth_code(body: ScraperAuthCodeBody):
    try:
        return await scraper_telethon_auth.scraper_submit_code(body.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/scraper-auth/password")
async def scraper_auth_password(body: ScraperAuthPasswordBody):
    try:
        return await scraper_telethon_auth.scraper_submit_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/scraper-auth/cancel")
async def scraper_auth_cancel():
    return await scraper_telethon_auth.scraper_cancel_login()


@router.get("/channel-intel")
def list_channel_intel(
    forward_enabled: bool | None = Query(None),
    pool_key: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Backlog of inbound Telegram channel metadata (forward policy, AOF lane, posting cadence)."""
    from app.services.scrape_channel_intel import profile_to_dict

    q = db.query(ScrapeChannelProfile).order_by(ScrapeChannelProfile.updated_at.desc())
    if forward_enabled is not None:
        q = q.filter(ScrapeChannelProfile.forward_enabled == forward_enabled)
    if pool_key:
        q = q.filter(ScrapeChannelProfile.pool_key == pool_key.strip().lower())
    rows = q.limit(limit).all()
    return [profile_to_dict(r) for r in rows]


@router.get("/")
def list_sources(db: Session = Depends(get_db)):
    return [_source_dict(s) for s in db.query(Source).order_by(Source.id).all()]


@router.get("/{source_id}/scrape-runs")
def list_source_scrape_runs(
    source_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _get_source_or_404(source_id, db)
    rows = list_scrape_runs(db, source_id=source_id, limit=limit)
    return [scrape_run_to_dict(r) for r in rows]


@router.get("/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    return _source_dict(_get_source_or_404(source_id, db))


@router.post("/", status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)):
    st = (body.source_type or "telegram_channel").strip().lower()
    if st not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of: {', '.join(SOURCE_TYPES)}")
    try:
        cron = validate_schedule_cron(body.schedule_cron) if body.schedule_cron else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    src = Source(
        name=body.name.strip() or "New source",
        source_type=st,
        identifier=(body.identifier or "").strip(),
        pool_id=body.pool_id,
        active=body.active,
        schedule_cron=cron,
        schedule_enabled=body.schedule_enabled,
        media_types=normalize_media_types(body.media_types),
        max_messages_per_run=body.max_messages_per_run,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return _source_dict(src)


def _apply_source_update(src: Source, body: SourceUpdate) -> None:
    if body.name is not None:
        src.name = body.name.strip() or src.name
    if body.source_type is not None:
        st = body.source_type.strip().lower()
        if st not in SOURCE_TYPES:
            raise HTTPException(status_code=400, detail=f"source_type must be one of: {', '.join(SOURCE_TYPES)}")
        src.source_type = st
    if body.identifier is not None:
        src.identifier = body.identifier.strip()
    if body.pool_id is not None:
        src.pool_id = body.pool_id
    if body.active is not None:
        src.active = body.active
    if body.schedule_cron is not None:
        try:
            src.schedule_cron = validate_schedule_cron(body.schedule_cron)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if body.schedule_enabled is not None:
        src.schedule_enabled = bool(body.schedule_enabled)
    if body.media_types is not None:
        src.media_types = normalize_media_types(body.media_types)
    if body.max_messages_per_run is not None:
        src.max_messages_per_run = int(body.max_messages_per_run)


@router.patch("/{source_id}")
@router.put("/{source_id}")
def update_source(source_id: int, body: SourceUpdate, db: Session = Depends(get_db)):
    src = _get_source_or_404(source_id, db)
    _apply_source_update(src, body)
    db.commit()
    db.refresh(src)
    return _source_dict(src)


@router.post("/{source_id}/update")
def update_source_post(source_id: int, body: SourceUpdate, db: Session = Depends(get_db)):
    return update_source(source_id, body, db)


@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    src = _get_source_or_404(source_id, db)
    db.delete(src)
    db.commit()
    return {"deleted": True, "id": source_id}


@router.post("/{source_id}/delete")
def delete_source_post(source_id: int, db: Session = Depends(get_db)):
    return delete_source(source_id, db)
