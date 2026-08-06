"""
Orchestrate companion image generation (undress / nudify) + temp public URLs.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.services.companion_jobs import CompanionJob, new_job_id, put_job
from app.services.nowpayments_client import public_api_base_url
from app.services.nudify_client import configured as nudify_configured, submit_nudify_job
from app.services.undress_tool_client import (
    configured as undress_configured,
    submit_photo_undress,
    submit_photo_undress_with_pose,
    submit_video_undress,
    submit_video_undress_with_pose,
)

logger = logging.getLogger(__name__)


def image_provider() -> str:
    raw = (os.getenv("TBCC_COMPANION_IMAGE_PROVIDER") or "undress").strip().lower()
    if raw == "nudify" and nudify_configured():
        return "nudify"
    if undress_configured():
        return "undress"
    if nudify_configured():
        return "nudify"
    return raw


def generation_configured() -> bool:
    return undress_configured() or nudify_configured()


def video_enabled() -> bool:
    raw = (os.getenv("TBCC_COMPANION_VIDEO_ENABLED") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return undress_configured()


def video_credit_units() -> int:
    raw = (os.getenv("TBCC_COMPANION_VIDEO_CREDIT_UNITS") or "2").strip()
    try:
        return max(1, min(10, int(raw)))
    except ValueError:
        return 2


def companion_webhook_base() -> str:
    base = public_api_base_url()
    if not base:
        raise RuntimeError(
            "Set TBCC_PUBLIC_API_BASE_URL to your public https API root (ngrok/Cloudflare in dev)"
        )
    return f"{base}/webhooks/companion"


async def check_public_webhook_reachable(*, timeout: float = 12.0) -> tuple[bool, str]:
    """Verify TBCC_PUBLIC_API_BASE_URL is reachable (ngrok/tunnel must be running)."""
    base = public_api_base_url()
    if not base:
        return False, "TBCC_PUBLIC_API_BASE_URL is not set"
    if "localhost" in base or "127.0.0.1" in base:
        return False, "TBCC_PUBLIC_API_BASE_URL cannot be localhost — undress API must POST webhooks from the internet"
    probe = f"{base}/webhooks/companion/undress"
    headers = {"ngrok-skip-browser-warning": "1", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.post(probe, headers=headers, json={"id_gen": "healthcheck", "status": "ping"})
            # 404/405 still means tunnel reached something; ngrok offline returns HTML error page
            ct = (r.headers.get("content-type") or "").lower()
            if "text/html" in ct and r.status_code >= 400:
                return False, "Public URL looks offline (ngrok tunnel down or wrong host). Start ngrok → port 8000 and update TBCC_PUBLIC_API_BASE_URL"
            if r.status_code == 0:
                return False, "Could not reach public URL"
            return True, probe
    except Exception as e:
        return False, f"Public webhook URL unreachable: {e!s}"[:200]


def _public_static_base() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or public_api_base_url()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").strip()
    ).rstrip("/")


def _companion_tmp_dir() -> Path:
    from app.services.bundle_storage import bundle_root

    folder = bundle_root() / "companion_tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def publish_temp_image(image_bytes: bytes, *, suffix: str = ".jpg") -> str:
    """Write image to /static/bundles/companion_tmp/ and return public URL (for nudify input)."""
    name = f"{uuid.uuid4().hex}{suffix}"
    path = _companion_tmp_dir() / name
    path.write_bytes(image_bytes[:12_000_000])
    return f"{_public_static_base()}/static/bundles/companion_tmp/{name}"


def cleanup_temp_image_from_url(url: str) -> None:
    marker = "/static/bundles/companion_tmp/"
    if marker not in url:
        return
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not name or ".." in name:
        return
    try:
        (_companion_tmp_dir() / name).unlink(missing_ok=True)
    except OSError:
        pass


@dataclass
class GenerationQueued:
    job_id: str
    provider: str
    message: str


async def queue_photo_generation(
    *,
    chat_id: int,
    user_id: int,
    photo_bytes: bytes,
    filename: str = "photo.jpg",
    provider: str | None = None,
    pose: str | None = None,
    age: str | None = None,
    breast_size: str | None = None,
    body_type: str | None = None,
    butt_size: str | None = None,
    cloth: str | None = None,
) -> GenerationQueued:
    ok, reach_msg = await check_public_webhook_reachable()
    if not ok:
        raise RuntimeError(reach_msg)

    prov = (provider or image_provider()).lower()
    if prov != "undress":
        raise RuntimeError("Video reveals require undress API — set TBCC_UNDRESS_TOOL_API_KEY")

    job_id = new_job_id(chat_id=chat_id, user_id=user_id)
    pose_val = (pose or "").strip() or None
    body_params = {
        "age": (age or "").strip() or None,
        "breast_size": (breast_size or "").strip() or None,
        "body_type": (body_type or "").strip() or None,
        "butt_size": (butt_size or "").strip() or None,
        "cloth": (cloth or "").strip() or None,
    }
    if body_params.get("breast_size") == "big" and not body_params.get("body_type"):
        body_params["body_type"] = "curvy"
    has_body = any(body_params.values())
    chain_pose = bool(pose_val and has_body)
    look_summary = ", ".join(f"{k}={v}" for k, v in body_params.items() if v) or "default"

    logger.info(
        "companion queue photo uid=%s job=%s pose=%s api_params=%s chain_pose=%s",
        user_id,
        job_id,
        pose_val,
        {k: v for k, v in body_params.items() if v},
        chain_pose,
    )

    put_job(
        CompanionJob(
            job_id=job_id,
            chat_id=chat_id,
            user_id=user_id,
            provider=prov,
            created_at=time.time(),
            pending_pose=pose_val if chain_pose else "",
            hold_delivery=chain_pose,
            refine_breast_size=body_params.get("breast_size") or "",
            refine_body_type=body_params.get("body_type") or "",
            refine_butt_size=body_params.get("butt_size") or "",
            refine_age=body_params.get("age") or "",
            character_look=look_summary,
            character_pose=pose_val or "",
        )
    )
    webhook = f"{companion_webhook_base()}/{prov}"

    if prov == "nudify":
        if not nudify_configured():
            raise RuntimeError("Nudify not configured — set TBCC_NUDIFY_API_KEY")
        image_url = publish_temp_image(photo_bytes, suffix=Path(filename).suffix or ".jpg")
        result = await submit_nudify_job(image_url=image_url, webhook_url=webhook)
        if not result.ok:
            raise RuntimeError("Nudify job rejected")
        return GenerationQueued(job_id=job_id, provider=prov, message="Nudify job queued — I'll DM the result.")

    if not undress_configured():
        raise RuntimeError("Undress API not configured — set TBCC_UNDRESS_TOOL_API_KEY")

    if chain_pose:
        result = await submit_photo_undress(
            id_gen=job_id,
            photo_bytes=photo_bytes,
            webhook_url=webhook,
            filename=filename,
            age=body_params["age"],
            breast_size=body_params["breast_size"],
            body_type=body_params["body_type"],
            butt_size=body_params["butt_size"],
            cloth=body_params["cloth"],
        )
        refine_note = " + bimbo refine" if body_params.get("breast_size") == "big" else ""
        user_msg = f"Creating your character — body → pose{refine_note} (auto chain)…"
    elif pose_val:
        result = await submit_photo_undress_with_pose(
            id_gen=job_id,
            photo_bytes=photo_bytes,
            webhook_url=webhook,
            filename=filename,
            pose=pose_val,
        )
        user_msg = result.message or "Creating your character…"
    else:
        result = await submit_photo_undress(
            id_gen=job_id,
            photo_bytes=photo_bytes,
            webhook_url=webhook,
            filename=filename,
            age=body_params["age"],
            breast_size=body_params["breast_size"],
            body_type=body_params["body_type"],
            butt_size=body_params["butt_size"],
            cloth=body_params["cloth"],
        )
        user_msg = result.message or "Creating your character…"
    if not result.ok:
        raise RuntimeError(result.message or "Undress API rejected the photo")
    return GenerationQueued(job_id=job_id, provider="undress", message=user_msg)


async def queue_video_generation(
    *,
    chat_id: int,
    user_id: int,
    photo_bytes: bytes,
    filename: str = "photo.jpg",
    video_pose_id: str | None = None,
    video_pose_name: str | None = None,
) -> GenerationQueued:
    ok, reach_msg = await check_public_webhook_reachable()
    if not ok:
        raise RuntimeError(reach_msg)
    if not undress_configured():
        raise RuntimeError("Undress API not configured — set TBCC_UNDRESS_TOOL_API_KEY")

    job_id = new_job_id(chat_id=chat_id, user_id=user_id)
    pose_id = (video_pose_id or "").strip() or None
    pose_name = (video_pose_name or "").strip() or ""
    logger.info(
        "companion queue video uid=%s job=%s pose_id=%s pose_name=%s",
        user_id,
        job_id,
        pose_id,
        pose_name,
    )

    put_job(
        CompanionJob(
            job_id=job_id,
            chat_id=chat_id,
            user_id=user_id,
            provider="undress",
            created_at=time.time(),
            media_type="video",
            video_pose_id=pose_id or "",
            video_pose_name=pose_name,
            character_pose=pose_name,
        )
    )
    webhook = f"{companion_webhook_base()}/undress"
    if pose_id:
        result = await submit_video_undress_with_pose(
            id_gen=job_id,
            photo_bytes=photo_bytes,
            webhook_url=webhook,
            filename=filename,
            pose_id=pose_id,
        )
        user_msg = result.message or f"Video queued — pose: {pose_name or pose_id}…"
    else:
        result = await submit_video_undress(
            id_gen=job_id,
            photo_bytes=photo_bytes,
            webhook_url=webhook,
            filename=filename,
        )
        user_msg = result.message or "Video queued — I'll DM her when she's ready."
    if not result.ok:
        raise RuntimeError(result.message or "Undress video API rejected the photo")
    return GenerationQueued(job_id=job_id, provider="undress", message=user_msg)


def extract_result_urls(payload: dict[str, Any]) -> list[str]:
    """Best-effort parse of undress / nudify webhook bodies."""
    urls: list[str] = []

    def add(val: Any) -> None:
        if isinstance(val, str):
            if val.startswith(("http://", "https://")):
                urls.append(val)
            elif val.strip().startswith(("{", "[")):
                try:
                    walk(json.loads(val))
                except json.JSONDecodeError:
                    pass
        elif isinstance(val, list):
            for item in val:
                add(item)
        elif isinstance(val, dict):
            walk(val)

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key in ("result_url", "image_url", "imageUrl", "url", "photo_url", "output_url", "output", "video_url", "videoUrl"):
                if key in obj:
                    add(obj[key])
            raw = obj.get("raw_data")
            if raw is not None:
                add(raw)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, str):
            add(obj)

    walk(payload)

    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
