"""
Normalize dashboard promo uploads to Telegram-friendly JPEG or PNG.

Decodes with Pillow (JPEG, PNG, WebP, GIF first frame, BMP, etc.), applies EXIF orientation,
resizes if very large, then saves as:
- JPEG (quality 88) for opaque images
- PNG only when transparency fits under the size limit; otherwise flattens to JPEG on white
"""

from __future__ import annotations

import io
import logging
from typing import Final

from PIL import Image, ImageOps

from app.services.promo_storage import MAX_PROMO_IMAGE_BYTES

logger = logging.getLogger(__name__)

_MAX_LONG_EDGE: Final[int] = 4096
_INITIAL_JPEG_QUALITY: Final[int] = 88


def normalize_promo_image_bytes(raw: bytes) -> tuple[bytes, str]:
    """
    Return (normalized_bytes, file_extension) — ".jpg" or ".png".

    Raises ValueError if bytes are not a valid image.
    """
    if not raw or len(raw) < 8:
        raise ValueError("empty or too small")

    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception as e:
        raise ValueError(f"not a supported image: {e}") from e

    try:
        im = ImageOps.exif_transpose(im)
    except Exception as e:
        logger.debug("exif_transpose skipped: %s", e)

    w, h = im.size
    if w < 1 or h < 1:
        raise ValueError("invalid dimensions")

    long_edge = max(w, h)
    if long_edge > _MAX_LONG_EDGE:
        ratio = _MAX_LONG_EDGE / float(long_edge)
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))
        im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

    has_alpha = im.mode in ("RGBA", "LA") or (
        im.mode == "P" and ("transparency" in im.info or _palette_has_alpha(im))
    )
    if im.mode == "P" and has_alpha:
        im = im.convert("RGBA")

    if has_alpha and im.mode in ("RGBA", "LA"):
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        png_data = out.getvalue()
        if len(png_data) <= MAX_PROMO_IMAGE_BYTES:
            return png_data, ".png"
        # Oversized PNG with alpha → flatten to JPEG (white background)
        bg = Image.new("RGB", im.size, (255, 255, 255))
        if im.mode == "RGBA":
            bg.paste(im, mask=im.split()[3])
        else:
            bg.paste(im.convert("RGBA"), mask=im.split()[-1])
        return _jpeg_under_limit(bg), ".jpg"

    # Opaque
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    return _jpeg_under_limit(im), ".jpg"


def _palette_has_alpha(im: Image.Image) -> bool:
    if im.mode != "P":
        return False
    if im.info.get("transparency") is not None:
        return True
    return "transparency" in im.info


def _jpeg_under_limit(im: Image.Image) -> bytes:
    q = _INITIAL_JPEG_QUALITY
    data = _encode_jpeg(im, q)
    while len(data) > MAX_PROMO_IMAGE_BYTES and q > 50:
        q -= 8
        data = _encode_jpeg(im, q)
    if len(data) > MAX_PROMO_IMAGE_BYTES:
        im = im.resize(
            (max(1, im.width // 2), max(1, im.height // 2)),
            Image.Resampling.LANCZOS,
        )
        data = _encode_jpeg(im, 82)
    if len(data) > MAX_PROMO_IMAGE_BYTES:
        raise ValueError("image still too large after compression; use a smaller source")
    return data


def _encode_jpeg(im: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()
