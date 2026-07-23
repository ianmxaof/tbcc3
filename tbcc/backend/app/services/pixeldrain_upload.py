"""Pixeldrain binary file upload (zip / video) → https://pixeldrain.com/u/{id}."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PIXELDRAIN_API_BASE = (os.environ.get("TBCC_PIXELDRAIN_API_BASE") or "https://pixeldrain.com/api").rstrip("/")


class PixeldrainUploadError(RuntimeError):
    pass


def pixeldrain_api_key() -> str:
    """Canonical TBCC_PIXELDRAIN_API_KEY, then short/dated capture-secret aliases."""
    for name in (
        "TBCC_PIXELDRAIN_API_KEY",
        "TBCC_PD",
        "PD_KEY",
        "PIXELDRAIN_API_KEY",
        "PIXELDRAIN_API_KEY_071726",
    ):
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    # Any dated PIXELDRAIN_API_KEY_* from capture-secret
    for key, val in os.environ.items():
        if key.startswith("PIXELDRAIN_API_KEY") and (val or "").strip():
            return val.strip()
    return ""


def pixeldrain_configured() -> bool:
    return bool(pixeldrain_api_key())


def _safe_upload_name(filename: str) -> str:
    base = Path(filename or "pack.zip").name
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "pack.zip"
    return base[:120]


def upload_bytes_to_pixeldrain(
    data: bytes,
    *,
    filename: str = "pack.zip",
    content_type: str = "application/octet-stream",
    timeout: float = 300.0,
) -> dict[str, str]:
    """PUT file to Pixeldrain; returns {id, public_url, filename}."""
    key = pixeldrain_api_key()
    if not key:
        raise PixeldrainUploadError("TBCC_PIXELDRAIN_API_KEY not set")
    if not data:
        raise PixeldrainUploadError("empty_file")
    fname = _safe_upload_name(filename)
    url_put = f"{_PIXELDRAIN_API_BASE}/file/{fname}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.put(
                url_put,
                content=data,
                headers={"Content-Type": content_type},
                auth=("", key),
            )
    except httpx.RequestError as e:
        logger.warning("pixeldrain file PUT failed: %s", e)
        raise PixeldrainUploadError("pixeldrain request failed") from e
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = (r.text or "")[:400]
        raise PixeldrainUploadError(f"pixeldrain HTTP {r.status_code}: {detail}") from e
    try:
        payload = r.json()
    except ValueError as e:
        raise PixeldrainUploadError("pixeldrain returned non-JSON") from e
    fid = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(fid, str) or not fid.strip():
        raise PixeldrainUploadError("pixeldrain response missing id")
    host = _PIXELDRAIN_API_BASE.replace("/api", "").rstrip("/")
    if not host.startswith("http"):
        host = "https://pixeldrain.com"
    public = f"{host}/u/{fid.strip()}"
    return {"id": fid.strip(), "public_url": public, "filename": fname}
