from __future__ import annotations



import logging



from celery.result import AsyncResult

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field



from app.services import myjd_service

from app.workers.celery_app import celery



logger = logging.getLogger(__name__)



router = APIRouter()





class JdAddLinksBody(BaseModel):

    links: str = Field(..., min_length=4, max_length=500_000)

    package_name: str | None = Field(default=None, max_length=200)

    autostart: bool = False

    background: bool = False





class JdResolveBody(BaseModel):

    url: str = Field(..., min_length=8, max_length=8192)

    package_name: str | None = Field(default=None, max_length=200)

    autostart: bool = False





def _should_queue_add_links(body: JdAddLinksBody) -> bool:

    if body.background or myjd_service.myjd_prefer_async():

        return True

    return myjd_service.count_link_lines(body.links) >= myjd_service.myjd_async_min_links()





def _enqueue_add_links(body: JdAddLinksBody) -> dict:

    from app.workers.myjd_worker import enqueue_myjd_add_links



    link_count = myjd_service.count_link_lines(body.links)

    if link_count < 1:

        raise HTTPException(status_code=400, detail="No http(s) links in payload")

    task_id = enqueue_myjd_add_links(

        body.links,

        package_name=body.package_name,

        autostart=body.autostart,

    )

    return {

        "ok": True,

        "queued": True,

        "task_id": task_id,

        "link_count": link_count,

        "hint": "Poll GET /jd/add-links/task/{task_id} or check JDownloader LinkGrabber.",

    }





@router.get("/status")

async def jd_status():

    return await myjd_service.myjd_status()





@router.get("/add-links/task/{task_id}")

async def jd_add_links_task(task_id: str):

    result = AsyncResult(task_id, app=celery)

    payload: dict = {"ok": True, "task_id": task_id, "state": result.state}

    if result.successful():

        payload["result"] = result.result

    elif result.failed():

        payload["ok"] = False

        payload["error"] = str(result.result)[:500] if result.result else "task failed"

    return payload





@router.post("/add-links")

async def jd_add_links(body: JdAddLinksBody):

    if not myjd_service.myjd_enabled():

        raise HTTPException(

            status_code=503,

            detail="My.JDownloader not configured (TBCC_MYJD_EMAIL / TBCC_MYJD_PASSWORD in tbcc/.env)",

        )

    if _should_queue_add_links(body):

        try:

            return _enqueue_add_links(body)

        except HTTPException:

            raise

        except Exception as e:

            logger.warning("MyJD queue failed, falling back to sync: %s", e)

    try:

        out = await myjd_service.myjd_add_links(

            body.links,

            package_name=body.package_name,

            autostart=body.autostart,

        )

        out["queued"] = False

        return out

    except Exception as e:

        logger.exception("MyJD add-links failed")

        myjd_service.reset_myjd_session()

        msg = str(e).strip()

        if isinstance(e, TimeoutError) or "Timeout" in type(e).__name__:

            raise HTTPException(

                status_code=504,

                detail=f"JDownloader timed out after {myjd_service.myjd_request_timeout_s():.0f}s — try fewer links or check JD is online.",

            ) from e

        raise HTTPException(status_code=502, detail=f"JDownloader: {msg}") from e





@router.post("/resolve")

async def jd_resolve(body: JdResolveBody):

    if not myjd_service.myjd_enabled():

        raise HTTPException(status_code=503, detail="My.JDownloader not configured")

    try:

        items = await myjd_service.myjd_resolve_page(

            body.url,

            package_name=body.package_name,

            autostart=body.autostart,

        )

        def _media_type(u: str) -> str:

            low = u.lower().split("?", 1)[0]

            return "video" if any(low.endswith("." + e) for e in ("mp4", "webm", "mkv", "m4v", "mov")) else "image"



        return {

            "adapter": "myjd",

            "source_url": body.url,

            "title": None,

            "items": [

                {

                    "url": it.url,

                    "media_type": _media_type(it.url),

                    "filename": it.name,

                    "thumbnail_url": None,

                }

                for it in items

            ],

            "warnings": [] if items else ["JDownloader found no direct http(s) links for this URL"],

        }

    except Exception as e:

        logger.exception("MyJD resolve failed url=%s", body.url[:180])

        myjd_service.reset_myjd_session()

        if isinstance(e, TimeoutError) or "Timeout" in type(e).__name__:

            raise HTTPException(

                status_code=504,

                detail="JDownloader resolve timed out — JD may still be crawling; try again with a smaller page.",

            ) from e

        raise HTTPException(status_code=502, detail=f"JDownloader resolve failed: {e}") from e

