"""On-disk promo assets injected into zip bundles."""

from __future__ import annotations

import os
from pathlib import Path

from app.services.promo_image_convert import normalize_promo_image_bytes
from app.services.promo_storage import MAX_PROMO_IMAGE_BYTES


def zip_promo_root() -> Path:
    env = (os.getenv("TBCC_ZIP_PROMO_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent
    return (tbcc / "uploads" / "zip_promo").resolve()


def ensure_zip_promo_dir() -> Path:
    root = zip_promo_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def zip_promo_image_path(filename: str | None) -> Path | None:
    fn = (filename or "").strip()
    if not fn or "/" in fn or "\\" in fn or ".." in fn:
        return None
    p = ensure_zip_promo_dir() / fn
    return p if p.is_file() else None


def save_zip_promo_image(raw: bytes, suggested_name: str | None = None) -> tuple[str, Path]:
    if len(raw) > MAX_PROMO_IMAGE_BYTES:
        raise ValueError(f"Image too large (max {MAX_PROMO_IMAGE_BYTES // (1024 * 1024)} MB)")
    raw_out, ext = normalize_promo_image_bytes(raw)
    root = ensure_zip_promo_dir()
    base = (suggested_name or "promo").strip()
    if not base.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        base = base + ext
    safe = Path(base).name
    path = root / safe
    path.write_bytes(raw_out)
    return safe, path
