"""Background My.JDownloader add-links (does not block API request thread)."""

from __future__ import annotations

import logging

from app.services.myjd_service import _add_links_sync, reset_myjd_session
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.myjd_worker.add_links", bind=True, max_retries=0)
def add_links(self, links: str, package_name: str | None = None, autostart: bool = False) -> dict:
    try:
        out = _add_links_sync(links, package_name=package_name, autostart=autostart)
        logger.info(
            "myjd add_links task ok links=%s batches=%s",
            out.get("link_count"),
            out.get("batches"),
        )
        return out
    except Exception as e:
        logger.exception("myjd add_links task failed")
        reset_myjd_session()
        raise e


def enqueue_myjd_add_links(
    links: str,
    *,
    package_name: str | None = None,
    autostart: bool = False,
) -> str:
    async_result = add_links.delay(links, package_name=package_name, autostart=autostart)
    return str(async_result.id)
