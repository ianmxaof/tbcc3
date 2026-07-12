from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.source import Source
from app.services.scrape_run_service import (
    cancel_scrape_run,
    create_scrape_run,
    scrape_transport_overview,
    skip_active_scrape,
)
from app.workers.mega_scraper_worker import create_link_scrape_run, run_mega_scrape_job
from app.workers.scraper_worker import run_scrape

router = APIRouter()


class MegaScrapeBody(BaseModel):
    chat_id: int | None = Field(None, description="Telegram channel id (-100…); omit to use curated list")
    message_limit: int = Field(40, ge=1, le=200)
    direct_only: bool = Field(True, description="Skip LV-gated URLs unless bypass key set")
    execute: bool = Field(True, description="Write loot_modifiers when true")
    use_admin_session: bool = Field(False, description="Reserved — worker uses scraper.session")


class SkipScrapeBody(BaseModel):
    queue_next: bool = Field(True, description="After cancel, enqueue next scheduled/active source")


@router.get("/")
def list_jobs(db: Session = Depends(get_db)):
    return []


@router.get("/scrape/transport")
def scrape_transport(db: Session = Depends(get_db)):
    """Ingest transport overview: per-source phase + active runs + lock holder."""
    return scrape_transport_overview(db)


@router.post("/scrape/skip")
def scrape_skip(body: SkipScrapeBody | None = None, db: Session = Depends(get_db)):
    """Cancel current active scrape and optionally fast-forward to the next source."""
    opts = body or SkipScrapeBody()
    return skip_active_scrape(db, queue_next=bool(opts.queue_next))


@router.post("/scrape-runs/{run_id}/cancel")
def scrape_run_cancel(run_id: int, db: Session = Depends(get_db)):
    try:
        return cancel_scrape_run(db, run_id, code="user_cancelled")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/scrape/{source_id}")
def trigger_scrape(source_id: int, db: Session = Depends(get_db)):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")
    if not src.active:
        raise HTTPException(status_code=400, detail="Source is inactive — enable Active in Sources before scraping.")
    if (src.source_type or "").strip().lower() != "telegram_channel":
        raise HTTPException(
            status_code=400,
            detail=f"Scrape only supports telegram_channel sources (this source is {src.source_type!r}).",
        )
    run = create_scrape_run(db, src, trigger="manual")
    async_result = run_scrape.delay(source_id, "manual", run.id)
    run.celery_task_id = async_result.id
    db.commit()
    return {
        "status": "scheduled",
        "source_id": source_id,
        "run_id": run.id,
        "celery_task_id": async_result.id,
    }


@router.post("/mega-scrape")
def trigger_mega_scrape(body: MegaScrapeBody, db: Session = Depends(get_db)):
    """Scrape Telegram channel messages for file-host / paste links → LV wrap → loot modifiers."""
    from app.data.mega_scrape_channel_sources import MEGA_SCRAPE_CHANNEL_SOURCES

    label = "curated channels"
    chat_ids: list[int] | None = None
    kinds: list[str] | None = None
    if body.chat_id is not None:
        chat_ids = [int(body.chat_id)]
        for row in MEGA_SCRAPE_CHANNEL_SOURCES:
            if int(row["chat_id"]) == int(body.chat_id):
                label = str(row.get("label") or body.chat_id)
                break
        else:
            label = str(body.chat_id)
    elif body.direct_only:
        kinds = ["direct_host", "mixed"]

    run = create_link_scrape_run(db, label=label, chat_id=body.chat_id, trigger="manual")
    async_result = run_mega_scrape_job.delay(
        run.id,
        chat_ids=chat_ids,
        kinds=kinds,
        message_limit=body.message_limit,
        include_obfuscated=not body.direct_only,
        execute=body.execute,
    )
    run.celery_task_id = async_result.id
    db.commit()
    return {
        "status": "scheduled",
        "run_id": run.id,
        "run_kind": "link",
        "celery_task_id": async_result.id,
        "chat_id": body.chat_id,
        "direct_only": body.direct_only,
    }
