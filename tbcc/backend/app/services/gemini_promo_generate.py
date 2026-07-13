"""Call Gemini image API (Nano Banana) for AOF promo assets."""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def gemini_api_key() -> str:
    # Capture-secret registry suggests TBCC_GEMINI_API_KEY; also accept Google SDK names.
    return (
        os.getenv("TBCC_GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip()


def gemini_image_model() -> str:
    return (os.getenv("TBCC_GEMINI_IMAGE_MODEL") or "gemini-2.5-flash-image").strip()


def output_dir() -> Path:
    override = (os.getenv("TBCC_PROMO_GENERATED_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    root = Path(__file__).resolve().parent.parent.parent.parent
    return root / "assets" / "promo-generated"


def generate_image_bytes(*, prompt: str, aspect_ratio: str) -> bytes:
    key = gemini_api_key()
    if not key:
        raise ValueError("TBCC_GEMINI_API_KEY (or GEMINI_API_KEY) not set in tbcc/.env")

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise ImportError("Install google-genai: py -m pip install google-genai") from e

    client = genai.Client(api_key=key)
    model = gemini_image_model()

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
    )

    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=config,
    )

    # Walk candidates/parts for inline image data
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                data = inline.data
                if isinstance(data, str):
                    return base64.b64decode(data)
                return bytes(data)

    # Fallback: response.parts API (newer SDK shapes)
    for part in getattr(response, "parts", None) or []:
        if hasattr(part, "inline_data") and part.inline_data:
            data = part.inline_data.data
            if isinstance(data, str):
                return base64.b64decode(data)
            return bytes(data)
        if hasattr(part, "as_image"):
            try:
                img = part.as_image()
                from io import BytesIO

                buf = BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                pass

    raise RuntimeError("Gemini response contained no image data")


def save_generated_image(
    data: bytes,
    *,
    slug: str,
    ext: str = "png",
    out: Path | None = None,
) -> Path:
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("saved promo image %s (%s bytes)", path, len(data))
        return path
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug.lower())[:80]
    path = out_dir / f"{safe}-{ts}.{ext}"
    path.write_bytes(data)
    logger.info("saved promo image %s (%s bytes)", path, len(data))
    return path
