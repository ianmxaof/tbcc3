from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.content_pool import ContentPool
from app.models.channel import Channel
from app.workers.scraper_worker import run_scrape
from app.workers.poster_worker import post_pool

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
    pool = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
    if not pool or not pool.channel_id:
        return {"error": "Pool not found or has no channel"}
    channel = db.query(Channel).filter(Channel.id == pool.channel_id).first()
    if not channel:
        return {"error": "Channel not found"}
    post_pool.delay(pool_id, channel.identifier)
    return {"status": "scheduled", "pool_id": pool_id}
