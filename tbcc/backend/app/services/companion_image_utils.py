"""Resize/compress companion pipeline images for undress API re-upload."""

from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

# Pose re-upload rejects multi-MB bodies; body-pass output is often ~3–4MB.
_DEFAULT_MAX_BYTES = 1_400_000
_DEFAULT_MAX_EDGE = 2048


def compress_image_for_api_upload(
    photo_bytes: bytes,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_edge: int = _DEFAULT_MAX_EDGE,
    filename: str = "result.jpg",
) -> tuple[bytes, str]:
    """Return JPEG bytes under max_bytes when possible (for pose chain step)."""
    if not photo_bytes:
        raise ValueError("photo_bytes empty")
    if len(photo_bytes) <= max_bytes and filename.lower().endswith((".jpg", ".jpeg")):
        return photo_bytes, filename

    try:
        old_max = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = max(old_max or 0, 50_000_000)
        try:
            with Image.open(io.BytesIO(photo_bytes)) as im:
                im = im.convert("RGB")
                w, h = im.size
                longest = max(w, h)
                if longest > max_edge:
                    scale = max_edge / float(longest)
                    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

                quality = 88
                out = photo_bytes
                for _ in range(8):
                    buf = io.BytesIO()
                    im.save(buf, format="JPEG", quality=quality, optimize=True)
                    out = buf.getvalue()
                    if len(out) <= max_bytes:
                        return out, "result.jpg"
                    quality = max(55, quality - 8)

                if len(out) < len(photo_bytes):
                    return out, "result.jpg"
        finally:
            Image.MAX_IMAGE_PIXELS = old_max
    except Exception as e:
        logger.warning("companion_image_utils: compress failed, using original: %s", e)

    return photo_bytes, filename
