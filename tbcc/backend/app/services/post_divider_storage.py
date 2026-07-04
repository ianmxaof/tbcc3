"""On-disk ornamental divider images for main-group post spacing."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.services.promo_image_convert import normalize_promo_image_bytes
from app.services.promo_storage import MAX_PROMO_IMAGE_BYTES


def post_divider_root() -> Path:
    env = (os.getenv("TBCC_POST_DIVIDER_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent
    return (tbcc / "uploads" / "post_dividers").resolve()


def ensure_post_divider_dir() -> Path:
    root = post_divider_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def post_divider_image_path(filename: str | None) -> Path | None:
    fn = (filename or "").strip()
    if not fn or "/" in fn or "\\" in fn or ".." in fn:
        return None
    p = ensure_post_divider_dir() / fn
    return p if p.is_file() else None


def save_post_divider_image(raw: bytes, suggested_name: str | None = None) -> tuple[str, str, Path]:
    if len(raw) > MAX_PROMO_IMAGE_BYTES:
        raise ValueError(f"Image too large (max {MAX_PROMO_IMAGE_BYTES // (1024 * 1024)} MB)")
    raw_out, ext = normalize_promo_image_bytes(raw)
    root = ensure_post_divider_dir()
    image_id = uuid.uuid4().hex[:16]
    base = (suggested_name or "divider").strip()
    stem = Path(base).stem[:48] or "divider"
    safe = f"{image_id}_{stem}{ext}"
    path = root / safe
    path.write_bytes(raw_out)
    return image_id, safe, path
