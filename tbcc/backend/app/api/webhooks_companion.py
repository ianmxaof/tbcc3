"""
Webhooks for companion image providers (undress API, nudify).

POST /webhooks/companion/undress
POST /webhooks/companion/nudify

undresstool.fun may deliver multipart (id_gen + file) or JSON (`id` + base64 `photo`).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.services.companion_character import save_character
from app.services.companion_generation import cleanup_temp_image_from_url, companion_webhook_base, extract_result_urls
from app.services.companion_image_utils import compress_image_for_api_upload
from app.services.companion_jobs import CompanionJob, get_job, new_job_id, parse_telegram_job_id, pop_job, put_job
from app.services.companion_telegram_dispatch import (
    send_result_message,
    send_result_photo,
    send_result_photo_bytes,
)
from app.services.undress_tool_client import submit_photo_undress, submit_photo_undress_with_pose

logger = logging.getLogger(__name__)

router = APIRouter()


def _webhook_secret_ok(request: Request) -> bool:
    expected = (os.getenv("TBCC_COMPANION_WEBHOOK_SECRET") or "").strip()
    if not expected:
        return True
    got = (
        request.headers.get("x-companion-webhook-secret")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    return got == expected


def _extract_job_key(payload: dict[str, Any]) -> str | None:
    for field in ("id_gen", "id", "job_id", "jobId"):
        key = parse_telegram_job_id(str(payload.get(field) or ""))
        if key:
            return key
    return None


def _decode_payload_image(payload: dict[str, Any], image_bytes: bytes | None) -> bytes | None:
    if image_bytes and len(image_bytes) > 100:
        return image_bytes
    for field in ("photo", "image", "result", "image_base64"):
        raw = payload.get(field)
        if not isinstance(raw, str) or len(raw) < 50:
            continue
        try:
            decoded = base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) > 100:
            return decoded
    return image_bytes


async def _parse_webhook_body(request: Request) -> tuple[dict[str, Any], bytes | None, str]:
    """Return (fields dict, optional image bytes, filename hint)."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        payload: dict[str, Any] = {}
        image_bytes: bytes | None = None
        filename = "result.jpg"
        for key, value in form.multi_items():
            if hasattr(value, "read"):
                image_bytes = await value.read()
                filename = getattr(value, "filename", None) or filename
                payload[key] = filename
            else:
                payload[key] = value
        return payload, image_bytes, filename

    raw = await request.body()
    if not raw:
        return {}, None, "result.jpg"
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        # Raw image body fallback
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG":
            return {}, raw, "result.jpg"
        raise
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="invalid body")
    image_bytes = _decode_payload_image(parsed, None)
    return parsed, image_bytes, "result.jpg"


async def _download_image_url(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            if len(r.content) > 100:
                return r.content
    except Exception as e:
        logger.warning("companion webhook: download failed %s: %s", url[:80], e)
    return None


async def _chain_pose_pass(job: CompanionJob, image_bytes: bytes, filename: str) -> dict[str, Any]:
    new_id = new_job_id(chat_id=job.chat_id, user_id=job.user_id)
    bimbo_refine = job.wants_bimbo_refine()
    put_job(
        CompanionJob(
            job_id=new_id,
            chat_id=job.chat_id,
            user_id=job.user_id,
            provider=job.provider,
            created_at=job.created_at,
            pending_body_refine=bimbo_refine,
            hold_delivery=bimbo_refine,
            refine_breast_size=job.refine_breast_size,
            refine_body_type=job.refine_body_type or "curvy",
            refine_butt_size=job.refine_butt_size,
            refine_age=job.refine_age,
            character_look=job.character_look,
            character_pose=job.character_pose,
        )
    )
    webhook = f"{companion_webhook_base()}/undress"
    try:
        chain_bytes, chain_name = compress_image_for_api_upload(image_bytes, filename=filename)
        logger.info(
            "companion chain pose: %s bytes -> %s bytes pose=%s",
            len(image_bytes),
            len(chain_bytes),
            job.pending_pose,
        )
        result = await submit_photo_undress_with_pose(
            id_gen=new_id,
            photo_bytes=chain_bytes,
            webhook_url=webhook,
            filename=chain_name,
            pose=job.pending_pose,
        )
    except Exception as e:
        logger.exception("companion chain pose failed: %s", e)
        await send_result_message(
            chat_id=job.chat_id,
            text=f"Body pass finished but pose step crashed: {e!s}"[:400],
        )
        return {"ok": True, "delivered": "pose_chain_error"}
    if not result.ok:
        await send_result_message(
            chat_id=job.chat_id,
            text=f"Body pass OK but pose step failed: {(result.message or 'unknown')[:400]}",
        )
        return {"ok": True, "delivered": "pose_chain_failed"}
    await send_result_message(chat_id=job.chat_id, text="Body sizing applied — finishing pose pass…")
    return {"ok": True, "chained_pose": new_id}


async def _chain_body_refine_pass(job: CompanionJob, image_bytes: bytes, filename: str) -> dict[str, Any]:
    new_id = new_job_id(chat_id=job.chat_id, user_id=job.user_id)
    put_job(
        CompanionJob(
            job_id=new_id,
            chat_id=job.chat_id,
            user_id=job.user_id,
            provider=job.provider,
            created_at=job.created_at,
            character_look=job.character_look,
            character_pose=job.character_pose,
        )
    )
    webhook = f"{companion_webhook_base()}/undress"
    try:
        chain_bytes, chain_name = compress_image_for_api_upload(image_bytes, filename=filename)
        logger.info(
            "companion chain bimbo refine: %s bytes -> %s bytes",
            len(image_bytes),
            len(chain_bytes),
        )
        result = await submit_photo_undress(
            id_gen=new_id,
            photo_bytes=chain_bytes,
            webhook_url=webhook,
            filename=chain_name,
            age=job.refine_age or None,
            breast_size=job.refine_breast_size or "big",
            body_type=job.refine_body_type or "curvy",
            butt_size=job.refine_butt_size or None,
        )
    except Exception as e:
        logger.exception("companion chain bimbo refine failed: %s", e)
        await send_result_message(
            chat_id=job.chat_id,
            text=f"Pose OK but bimbo sizing pass crashed: {e!s}"[:400],
        )
        return {"ok": True, "delivered": "refine_chain_error"}
    if not result.ok:
        await send_result_message(
            chat_id=job.chat_id,
            text=f"Pose OK but bimbo sizing pass failed: {(result.message or 'unknown')[:400]}",
        )
        return {"ok": True, "delivered": "refine_chain_failed"}
    await send_result_message(chat_id=job.chat_id, text="Pose locked — applying bimbo max sizing pass…")
    return {"ok": True, "chained_refine": new_id}


async def _deliver_final_photo(job: CompanionJob, image_bytes: bytes, filename: str) -> dict[str, Any]:
    char = save_character(
        user_id=job.user_id,
        look_summary=job.character_look or "glamorous, curvy",
        pose=job.character_pose,
    )
    caption = (
        f"<b>{char.name}</b> is ready — she's yours now.\n"
        "Chat anytime (she remembers you). /name to rename her."
    )
    ok = await send_result_photo_bytes(
        chat_id=job.chat_id,
        image_bytes=image_bytes,
        caption=caption,
        filename=filename,
        parse_mode="HTML",
    )
    if ok:
        try:
            from app.services.companion_stars import maybe_offer_stars_after_delivery

            await maybe_offer_stars_after_delivery(chat_id=job.chat_id, user_id=job.user_id)
        except Exception as e:
            logger.debug("stars upsell after delivery skipped: %s", e)
    return {"ok": True, "delivered": "photo_bytes" if ok else "photo_bytes_failed"}


async def _handle_payload(
    provider: str,
    payload: dict[str, Any],
    *,
    image_bytes: bytes | None = None,
    filename: str = "result.jpg",
) -> dict:
    image_bytes = _decode_payload_image(payload, image_bytes)
    logger.info(
        "companion webhook %s keys=%s image_bytes=%s",
        provider,
        list(payload.keys())[:12],
        len(image_bytes) if image_bytes else 0,
    )
    job_key = _extract_job_key(payload)
    if not job_key:
        logger.warning("companion webhook %s: missing job id in %s", provider, list(payload.keys())[:8])
        return {"ok": True, "ignored": "no_job_id"}

    job = get_job(job_key)
    if not job:
        logger.warning("companion webhook %s: unknown job %s", provider, job_key)
        return {"ok": True, "ignored": "unknown_job"}

    status = str(payload.get("status") or "").lower()
    has_image = bool(image_bytes and len(image_bytes) > 100)
    if status in ("processing", "pending", "queued", "created", "ping") and not has_image:
        return {"ok": True, "ignored": "still_processing"}

    job = pop_job(job_key) or job

    if status in ("error", "failed", "failure"):
        msg = str(payload.get("message") or payload.get("error") or "Generation failed")
        await send_result_message(chat_id=job.chat_id, text=f"Generation failed: {msg[:500]}")
        return {"ok": True, "delivered": "error"}

    if job.hold_delivery and job.pending_pose:
        chain_image = image_bytes if image_bytes and len(image_bytes) > 100 else None
        if not chain_image:
            urls = extract_result_urls(payload)
            if urls:
                chain_image = await _download_image_url(urls[0])
                for u in urls:
                    cleanup_temp_image_from_url(u)
        if chain_image:
            return await _chain_pose_pass(job, chain_image, filename)

    if job.hold_delivery and job.pending_body_refine:
        chain_image = image_bytes if image_bytes and len(image_bytes) > 100 else None
        if not chain_image:
            urls = extract_result_urls(payload)
            if urls:
                chain_image = await _download_image_url(urls[0])
                for u in urls:
                    cleanup_temp_image_from_url(u)
        if chain_image:
            return await _chain_body_refine_pass(job, chain_image, filename)

    if image_bytes and len(image_bytes) > 100:
        return await _deliver_final_photo(job, image_bytes, filename)

    urls = extract_result_urls(payload)
    if not urls:
        if status in ("processing", "pending", "queued", "created", "ping", "") and not has_image:
            return {"ok": True, "ignored": "still_processing"}
        await send_result_message(
            chat_id=job.chat_id,
            text="Generation finished but no image was returned. Try again or switch provider.",
        )
        return {"ok": True, "delivered": "no_image"}

    ok = await send_result_photo(chat_id=job.chat_id, image_url=urls[0], caption="Here is your result.")
    for u in urls:
        cleanup_temp_image_from_url(u)
    inp = payload.get("input")
    if isinstance(inp, dict):
        cleanup_temp_image_from_url(str(inp.get("imageUrl") or ""))
    if ok:
        save_character(
            user_id=job.user_id,
            look_summary=job.character_look or "glamorous, curvy",
            pose=job.character_pose,
        )
        await send_result_message(
            chat_id=job.chat_id,
            text="She's ready — chat with her anytime. /name to rename.",
        )
        try:
            from app.services.companion_stars import maybe_offer_stars_after_delivery

            await maybe_offer_stars_after_delivery(chat_id=job.chat_id, user_id=job.user_id)
        except Exception as e:
            logger.debug("stars upsell after url delivery skipped: %s", e)
    return {"ok": True, "delivered": "photo" if ok else "photo_failed"}


async def _companion_webhook(request: Request, provider: str) -> dict:
    if not _webhook_secret_ok(request):
        raise HTTPException(status_code=403, detail="invalid webhook secret")
    try:
        payload, image_bytes, filename = await _parse_webhook_body(request)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid json") from e
    except UnicodeDecodeError as e:
        logger.warning("companion webhook %s: undecodable body: %s", provider, e)
        raise HTTPException(status_code=400, detail="unsupported body encoding") from e
    return await _handle_payload(provider, payload, image_bytes=image_bytes, filename=filename)


@router.post("/companion/undress")
async def companion_undress_webhook(request: Request):
    return await _companion_webhook(request, "undress")


@router.post("/companion/nudify")
async def companion_nudify_webhook(request: Request):
    return await _companion_webhook(request, "nudify")
