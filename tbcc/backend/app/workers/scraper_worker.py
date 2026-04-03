import asyncio
import os
from app.workers.celery_app import celery


@celery.task(name="app.workers.scraper_worker.run_scrape")
def run_scrape(source_id: int):
    from bots.scraper_bot import run_scraper

    asyncio.run(
        run_scraper(
            api_id=os.environ["API_ID"],
            api_hash=os.environ["API_HASH"],
            source_id=source_id,
        )
    )
