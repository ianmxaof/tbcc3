"""
Client for nudify.me / Deepixels generation API.

Docs: https://docs.nudify.me/generations/pro-nudification
Auth: x-api-key header (TBCC_NUDIFY_API_KEY).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API = "https://api.deepixels.co/v1/generate"
INSTANT_MODEL = "nudifyme/img/instant"
PRO_MODEL = "nudifyme/img/pro-nudification"


def api_key() -> str:
    return (os.getenv("TBCC_NUDIFY_API_KEY") or os.getenv("NUDIFY_API_KEY") or "").strip()


def generate_url() -> str:
    return (os.getenv("TBCC_NUDIFY_GENERATE_URL") or DEFAULT_API).strip()


def configured() -> bool:
    return bool(api_key())


def model_name() -> str:
    raw = (os.getenv("TBCC_NUDIFY_MODEL") or INSTANT_MODEL).strip()
    return raw or INSTANT_MODEL


@dataclass
class NudifySubmitResult:
    ok: bool
    job_id: str
    status: str
    raw: dict[str, Any]


async def submit_nudify_job(
    *,
    image_url: str,
    webhook_url: str,
    mask_url: str | None = None,
    mode: str = "undress",
    size: str = "auto",
    shape: str = "auto",
    prompt: str | None = None,
    timeout: float = 60.0,
) -> NudifySubmitResult:
    if not configured():
        raise RuntimeError("Set TBCC_NUDIFY_API_KEY")
    if not image_url:
        raise ValueError("image_url required")
    if not webhook_url:
        raise ValueError("webhook_url required")

    inp: dict[str, Any] = {"imageUrl": image_url}
    if mask_url:
        inp["maskUrl"] = mask_url
    if prompt:
        inp["prompt"] = prompt
    else:
        inp["mode"] = mode
        inp["size"] = size
        inp["shape"] = shape

    payload = {
        "model": model_name(),
        "input": inp,
        "webhook": webhook_url,
    }
    headers = {"Content-Type": "application/json", "x-api-key": api_key()}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(generate_url(), headers=headers, json=payload)
        body = r.json() if r.content else {}
        if not r.is_success:
            detail = body if isinstance(body, dict) else {"text": (r.text or "")[:300]}
            logger.warning("nudify submit HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"Nudify API {r.status_code}")

    if not isinstance(body, dict):
        body = {"raw": body}
    job_id = str(body.get("jobId") or body.get("job_id") or "")
    status = str(body.get("status") or "created")
    return NudifySubmitResult(ok=bool(job_id), job_id=job_id, status=status, raw=body)
