"""HTTP bridge — macro search bot ↔ AOF archive search API."""

from __future__ import annotations

import html
import logging
import os

import httpx

from app.services.aof_macro_search_router import pick_best_search_surface

logger = logging.getLogger(__name__)

_API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=5.0)
_PREVIEW_TIMEOUT = httpx.Timeout(connect=15.0, read=45.0, write=30.0, pool=5.0)


def _internal_headers() -> dict[str, str]:
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        return {"X-TBCC-Internal-Key": key}
    return {}


def fetch_search_access(telegram_user_id: int) -> dict:
    url = f"{_API_BASE}/aof-search/status"
    with httpx.Client(timeout=_PREVIEW_TIMEOUT) as client:
        r = client.get(url, params={"telegram_user_id": int(telegram_user_id)}, headers=_internal_headers())
    r.raise_for_status()
    return r.json()


def post_aof_preview(*, telegram_user_id: int, query: str, surface: str | None = None) -> dict:
    url = f"{_API_BASE}/aof-search/preview"
    body = {
        "telegram_user_id": int(telegram_user_id),
        "query": query,
        "surface": surface,
    }
    with httpx.Client(timeout=_PREVIEW_TIMEOUT) as client:
        r = client.post(url, json=body, headers=_internal_headers())
    if r.status_code == 503:
        return {"ok": False, "reason": "disabled"}
    r.raise_for_status()
    return r.json()


def post_aof_find(*, telegram_user_id: int, query: str, surface: str | None = None) -> dict:
    url = f"{_API_BASE}/aof-search/find"
    body = {
        "telegram_user_id": int(telegram_user_id),
        "query": query,
        "surface": surface,
    }
    with httpx.Client(timeout=_TIMEOUT) as client:
        r = client.post(url, json=body, headers=_internal_headers())
    if r.status_code == 403:
        return {"ok": False, "forbidden": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


def try_aof_archive_delivery(telegram_user_id: int, query: str) -> dict:
    """
    Preview then deliver archive hits. Does not raise on miss — returns routing dict.
    """
    try:
        access = fetch_search_access(telegram_user_id)
    except Exception as e:
        logger.debug("aof search access failed uid=%s: %s", telegram_user_id, e)
        return {"ok": False, "reason": "access_unavailable"}

    if not access.get("enabled", True):
        return {"ok": False, "reason": "disabled"}

    surface = pick_best_search_surface(access)
    try:
        preview = post_aof_preview(
            telegram_user_id=telegram_user_id,
            query=query,
            surface=surface,
        )
    except Exception as e:
        logger.debug("aof preview failed uid=%s: %s", telegram_user_id, e)
        return {"ok": False, "reason": "preview_failed"}

    if not preview.get("has_matches"):
        return {
            "ok": False,
            "reason": "no_matches",
            "match_count": 0,
            "access": access,
        }

    if not access.get("can_search"):
        return {
            "ok": False,
            "reason": "quota_exhausted",
            "forbidden": True,
            "detail": {
                "message": "Daily archive search limit reached.",
                "searches_remaining": access.get("searches_remaining"),
            },
            "access": access,
            "match_count": preview.get("match_count"),
        }

    try:
        delivered = post_aof_find(
            telegram_user_id=telegram_user_id,
            query=query,
            surface=surface,
        )
    except Exception as e:
        logger.warning("aof find failed uid=%s: %s", telegram_user_id, e)
        return {"ok": False, "reason": "delivery_failed"}

    if not delivered.get("ok"):
        return {
            "ok": False,
            "reason": delivered.get("reason") or "delivery_failed",
            "access": access,
            "delivery": delivered.get("delivery"),
        }

    sent = int((delivered.get("delivery") or {}).get("media_sent") or 0)
    res = delivered.get("result") or {}
    emoji = res.get("primary_emoji") or "🔍"
    remaining = (delivered.get("access") or {}).get("searches_remaining")
    rem_note = f" · {remaining} archive searches left today" if remaining is not None else ""
    summary_html = (
        f"<b>{emoji} Archive hit — sent {sent} item(s) to your DM</b>{html.escape(rem_note)}"
    )
    return {
        "ok": True,
        "summary_html": summary_html,
        "delivery": delivered.get("delivery"),
        "result": res,
        "access": delivered.get("access"),
    }
