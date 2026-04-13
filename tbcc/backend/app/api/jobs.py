from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.workers.scraper_worker import run_scrape

router = APIRouter()


@router.get("/")
def list_jobs(db: Session = Depends(get_db)):
    return []


@router.post("/scrape/{source_id}")
def trigger_scrape(source_id: int, db: Session = Depends(get_db)):
    run_scrape.delay(source_id)
    return {"status": "scheduled", "source_id": source_id}


@router.post("/post/{pool_id}")
def trigger_post(pool_id: int, db: Session = Depends(get_db)):
    return {
        "error": "Pool posting from Jobs is disabled. Use Scheduler recurring posts to publish pool media."
    }
