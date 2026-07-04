"""
Client for undresstool.fun Undress API.

Docs: https://public-api.undresstool.fun/docs
Auth: X-API-KEY header (TBCC_UNDRESS_TOOL_API_KEY).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://public-api.undresstool.fun"

# Last-known-good list from GET /api/v1/photos/poses (used when vendor returns 5xx).
DEFAULT_PHOTO_POSES: tuple[str, ...] = (
    "Cumshot",
    "Missionary POV",
    "Blowjob",
    "Doggy Style",
    "Anal Fuck",
    "Cowgirl POV",
    "Spreading legs",
    "Tit Fuck",
    "Ahegao cum",
    "Cumshot POV",
    "Estival solstice",
    "Shibari",
    "Lingerie",
    "Wet girl",
)

_pose_cache: tuple[float, list[str]] | None = None
_POSE_CACHE_TTL_SEC = 3600


def api_key() -> str:
    return (os.getenv("TBCC_UNDRESS_TOOL_API_KEY") or os.getenv("UNDRESS_TOOL_API_KEY") or "").strip()


def base_url() -> str:
    return (os.getenv("TBCC_UNDRESS_TOOL_BASE_URL") or DEFAULT_BASE).rstrip("/")


def configured() -> bool:
    return bool(api_key())


@dataclass
class UndressSubmitResult:
    ok: bool
    id_gen: str
    status: str
    message: str
    raw: dict[str, Any]


@dataclass
class UndressUserInfo:
    telegram_id: int | None
    balance: int
    can_create_photos: bool
    can_create_videos: bool
    raw: dict[str, Any]


def _headers() -> dict[str, str]:
    return {"X-API-KEY": api_key()}


def _format_http_error(status_code: int, body: Any, fallback_text: str = "") -> str:
    if isinstance(body, dict):
        msg = body.get("message")
        if msg:
            return str(msg)
        detail = body.get("detail")
        if isinstance(detail, list) and detail:
            parts = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                loc = ".".join(str(x) for x in (item.get("loc") or []) if x != "body")
                parts.append(f"{loc}: {item.get('msg')}" if loc else str(item.get("msg") or ""))
            joined = "; ".join(p for p in parts if p)
            if joined:
                return joined
        if detail and not isinstance(detail, list):
            return str(detail)
    text = (fallback_text or "").strip()
    if text:
        return text[:400]
    return "request rejected"


async def get_me(*, timeout: float = 30.0) -> UndressUserInfo:
    if not configured():
        raise RuntimeError("Set TBCC_UNDRESS_TOOL_API_KEY")
    url = f"{base_url()}/api/v1/me"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers=_headers())
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("undress /me returned non-object")
    return UndressUserInfo(
        telegram_id=data.get("telegram_id"),
        balance=int(data.get("balance") or 0),
        can_create_photos=bool(data.get("can_create_photos")),
        can_create_videos=bool(data.get("can_create_videos")),
        raw=data,
    )


async def list_photo_poses(*, timeout: float = 30.0, allow_fallback: bool = True) -> list[str]:
    global _pose_cache
    now = time.time()
    if _pose_cache and (now - _pose_cache[0]) < _POSE_CACHE_TTL_SEC:
        return list(_pose_cache[1])

    url = f"{base_url()}/api/v1/photos/poses"
    headers = _headers() if configured() else None
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, headers=headers)
            if r.status_code >= 500:
                last_err = httpx.HTTPStatusError(
                    f"poses API {r.status_code}",
                    request=r.request,
                    response=r,
                )
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            poses = data.get("poses") if isinstance(data, dict) else None
            if not isinstance(poses, list):
                break
            out = [str(p) for p in poses if p]
            if out:
                _pose_cache = (now, out)
                return out
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as e:
            last_err = e
            await asyncio.sleep(0.6 * (attempt + 1))

    if allow_fallback and DEFAULT_PHOTO_POSES:
        logger.warning("list_photo_poses: vendor unavailable (%s) — using cached defaults", last_err)
        return list(DEFAULT_PHOTO_POSES)
    if last_err:
        raise last_err
    return []


async def submit_photo_undress_with_pose(
    *,
    id_gen: str,
    photo_bytes: bytes,
    webhook_url: str,
    pose: str,
    filename: str = "photo.jpg",
    timeout: float = 120.0,
) -> UndressSubmitResult:
    """POST /api/v1/photos/poses/undress — pose acts (separate from body sliders)."""
    if not configured():
        raise RuntimeError("Set TBCC_UNDRESS_TOOL_API_KEY")
    pose = (pose or "").strip()
    if not pose:
        raise ValueError("pose required")
    if not photo_bytes:
        raise ValueError("photo_bytes empty")
    if not webhook_url:
        raise ValueError("webhook_url required")

    url = f"{base_url()}/api/v1/photos/poses/undress"
    data = {"id_gen": id_gen, "webhook": webhook_url, "pose": pose}
    files = {"photo": (filename, photo_bytes, "image/jpeg")}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=_headers(), data=data, files=files)
        try:
            body = r.json() if r.content else {}
        except json.JSONDecodeError:
            body = {}
        if not r.is_success:
            msg = _format_http_error(r.status_code, body, r.text or "")
            if not msg or msg == "request rejected":
                msg = (r.text or f"HTTP {r.status_code}")[:400]
            logger.warning("undress pose submit HTTP %s: %s", r.status_code, msg)
            return UndressSubmitResult(
                ok=False,
                id_gen=id_gen,
                status="error",
                message=msg,
                raw={"status_code": r.status_code, "text": (r.text or "")[:500]},
            )

    if not isinstance(body, dict):
        body = {"raw": body}
    status = str(body.get("status") or "")
    if status.lower() in ("error", "failed"):
        return UndressSubmitResult(
            ok=False,
            id_gen=str(body.get("id_gen") or id_gen),
            status=status,
            message=str(body.get("message") or "undress failed"),
            raw=body,
        )
    return UndressSubmitResult(
        ok=True,
        id_gen=str(body.get("id_gen") or id_gen),
        status=status or "ok",
        message=str(body.get("message") or "queued"),
        raw=body,
    )


async def submit_photo_undress(
    *,
    id_gen: str,
    photo_bytes: bytes,
    webhook_url: str,
    filename: str = "photo.jpg",
    age: str | None = None,
    breast_size: str | None = None,
    body_type: str | None = None,
    butt_size: str | None = None,
    cloth: str | None = None,
    post_gen: str | None = None,
    timeout: float = 120.0,
) -> UndressSubmitResult:
    if not configured():
        raise RuntimeError("Set TBCC_UNDRESS_TOOL_API_KEY")
    if not photo_bytes:
        raise ValueError("photo_bytes empty")
    if not webhook_url:
        raise ValueError("webhook_url required")

    url = f"{base_url()}/api/v1/photos/undress"
    data: dict[str, str] = {"id_gen": id_gen, "webhook": webhook_url}
    for key, val in (
        ("age", age),
        ("breast_size", breast_size),
        ("body_type", body_type),
        ("butt_size", butt_size),
        ("cloth", cloth),
        ("post_gen", post_gen),
    ):
        if val:
            data[key] = val

    files = {"photo": (filename, photo_bytes, "image/jpeg")}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=_headers(), data=data, files=files)
        try:
            body = r.json() if r.content else {}
        except json.JSONDecodeError:
            body = {}
        if not r.is_success:
            msg = _format_http_error(r.status_code, body, r.text or "")
            if not msg or msg == "request rejected":
                msg = (r.text or f"HTTP {r.status_code}")[:400]
            logger.warning("undress submit HTTP %s: %s", r.status_code, msg)
            return UndressSubmitResult(
                ok=False,
                id_gen=id_gen,
                status="error",
                message=msg,
                raw={"status_code": r.status_code, "text": (r.text or "")[:500]},
            )

    if not isinstance(body, dict):
        body = {"raw": body}
    status = str(body.get("status") or "")
    if status.lower() in ("error", "failed"):
        return UndressSubmitResult(
            ok=False,
            id_gen=str(body.get("id_gen") or id_gen),
            status=status,
            message=str(body.get("message") or "undress failed"),
            raw=body,
        )
    return UndressSubmitResult(
        ok=True,
        id_gen=str(body.get("id_gen") or id_gen),
        status=status or "ok",
        message=str(body.get("message") or "queued"),
        raw=body,
    )
