from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.source import Source
from app.services.scrape_run_service import create_scrape_run
from app.workers.scraper_worker import run_scrape

router = APIRouter()


@router.get("/")
def list_jobs(db: Session = Depends(get_db)):
    return []


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
