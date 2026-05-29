"""Fetch a URL, optionally wrap in zip, inject promo, save for local_zip_pack loot modifiers."""

from __future__ import annotations

import io
import logging
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.bundle_storage import MAX_BUNDLE_ZIP_BYTES, bundle_root, is_zip_magic

logger = logging.getLogger(__name__)


def _filename_from_url(url: str, content_type: str = "") -> str:
    try:
        path = urlparse(url).path or ""
        base = Path(path).name
        if base and "." in base:
            return base[:200]
    except Exception:
        pass
    ct = (content_type or "").lower()
    if "zip" in ct:
        return "download.zip"
    if "video" in ct or url.lower().split("?", 1)[0].endswith((".mp4", ".webm", ".mkv")):
        return "video.mp4"
    if "gif" in ct:
        return "image.gif"
    return "file.bin"


def wrap_bytes_in_zip(inner: bytes, inner_name: str) -> bytes:
    out = io.BytesIO()
    safe = Path(inner_name or "file.bin").name[:200] or "file.bin"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(safe, inner)
    return out.getvalue()


async def fetch_url_bytes(url: str) -> tuple[bytes, str, str]:
    """Return (bytes, content_type, suggested_filename)."""
    from app.api.import_ import _httpx_get_media

    url_l = url.lower()
    is_large = any(url_l.split("?", 1)[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".zip"))
    timeout = 300.0 if is_large else 90.0
    data, content_type = await _httpx_get_media(url, timeout)
    if not data:
        raise ValueError("Empty download")
    if len(data) > MAX_BUNDLE_ZIP_BYTES:
        raise ValueError(f"File too large (max {MAX_BUNDLE_ZIP_BYTES // (1024 * 1024)} MiB)")
    fname = _filename_from_url(url, content_type)
    return data, content_type or "", fname


def prepare_zip_bytes(raw: bytes, url: str, content_type: str) -> bytes:
    """Use existing zip as-is or wrap single file."""
    if is_zip_magic(raw[:8]):
        return raw
    inner_name = _filename_from_url(url, content_type)
    return wrap_bytes_in_zip(raw, inner_name)


def save_loot_modifier_zip(
    zip_bytes: bytes,
    *,
    db: Session,
    include_promo: bool = True,
    original_label: str | None = None,
) -> tuple[Path, str]:
    """Write zip under bundles/loot_modifiers; optionally inject promo. Returns (path, public_filename)."""
    if len(zip_bytes) > MAX_BUNDLE_ZIP_BYTES:
        raise ValueError(f"Zip too large (max {MAX_BUNDLE_ZIP_BYTES // (1024 * 1024)} MiB)")
    folder = bundle_root() / "loot_modifiers"
    folder.mkdir(parents=True, exist_ok=True)
    base = Path(original_label or "pack.zip").name
    if not base.lower().endswith(".zip"):
        base = f"{base}.zip"
    fname = f"{uuid.uuid4().hex}_{base[:180]}"
    out = folder / fname
    out.write_bytes(zip_bytes)
    if include_promo:
        from app.services.zip_promo_inject import inject_promo_into_zip_path

        inject_promo_into_zip_path(out, db)
    return out, fname
