"""
Local NSFW classifier via TheHamkerCat/NSFW_Detection_API (GET ?url=…).

Set TBCC_NSFW_DETECT_URL=http://127.0.0.1:8001 (no trailing slash).
Maps model classes → Media.nsfw_tier (sfw | suggestive | explicit | unknown).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VALID_TIERS = frozenset({"sfw", "suggestive", "explicit", "unknown"})

_CLASS_TO_TIER = {
    "neutral": "sfw",
    "drawings": "sfw",
    "sexy": "suggestive",
    "porn": "explicit",
    "hentai": "explicit",
}


@dataclass
class NsfwClassifyResult:
    nsfw_tier: str
    top_class: str
    top_probability: float
    confident: bool
    raw: dict[str, Any] | None = None


def nsfw_classifier_enabled() -> bool:
    return bool((os.getenv("TBCC_NSFW_DETECT_URL") or "").strip())


def _base_url() -> str:
    return (os.getenv("TBCC_NSFW_DETECT_URL") or "").strip().rstrip("/")


def _min_confidence() -> float:
    try:
        return float(os.getenv("TBCC_NSFW_DETECT_MIN_CONF", "0.55"))
    except ValueError:
        return 0.55


def _parse_predictions(body: Any) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    if not isinstance(body, dict):
        return out
    # TheHamkerCat/NSFW_Detection_API: { "data": { "neutral": 72.1, "porn": 3.2, ... } } (0–100)
    data = body.get("data")
    if isinstance(data, dict):
        for key in ("drawings", "hentai", "neutral", "porn", "sexy"):
            if key not in data:
                continue
            try:
                val = float(data[key])
                prob = val / 100.0 if val > 1.0 else val
                out.append((key, prob))
            except (TypeError, ValueError):
                continue
    preds = body.get("prediction") or body.get("predictions") or body.get("result")
    if isinstance(preds, list):
        for p in preds:
            if not isinstance(p, dict):
                continue
            name = (
                p.get("className")
                or p.get("class_name")
                or p.get("class")
                or p.get("label")
                or ""
            )
            prob = p.get("probability") or p.get("score") or p.get("confidence") or 0
            try:
                out.append((str(name).strip().lower(), float(prob)))
            except (TypeError, ValueError):
                continue
    elif isinstance(body.get("className"), str):
        try:
            out.append((body["className"].strip().lower(), float(body.get("probability", 0))))
        except (TypeError, ValueError):
            pass
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _tier_from_predictions(preds: list[tuple[str, float]]) -> NsfwClassifyResult:
    if not preds:
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    top_class, top_prob = preds[0]
    tier = _CLASS_TO_TIER.get(top_class, "unknown")
    if tier == "unknown" and top_class:
        if "porn" in top_class or "hentai" in top_class:
            tier = "explicit"
        elif "sexy" in top_class:
            tier = "suggestive"
        elif top_class in ("neutral", "drawing", "drawings", "sfw"):
            tier = "sfw"
    confident = top_prob >= _min_confidence()
    return NsfwClassifyResult(tier, top_class, top_prob, confident, {"prediction": preds})


def classify_image_url(image_url: str, *, timeout: float = 45.0) -> NsfwClassifyResult:
    base = _base_url()
    if not base:
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(base + "/", params={"url": image_url})
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        err = str(e).lower()
        if "actively refused" in err or "connection refused" in err or "10061" in err:
            logger.debug("nsfw classify url skipped (service offline): %s", e)
        else:
            logger.warning("nsfw classify url failed: %s", e)
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    preds = _parse_predictions(body)
    res = _tier_from_predictions(preds)
    res.raw = body if isinstance(body, dict) else {"body": body}
    return res


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def classify_image_bytes(image_bytes: bytes, *, suffix: str = ".jpg") -> NsfwClassifyResult:
    """Write a short-lived JPEG under /static/bundles/nsfw_classify_tmp/ and classify by URL."""
    if not nsfw_classifier_enabled() or not image_bytes or len(image_bytes) < 32:
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    from app.services.bundle_storage import bundle_root

    folder = bundle_root() / "nsfw_classify_tmp"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{suffix}"
    path = folder / name
    try:
        path.write_bytes(image_bytes[:8_000_000])
        rel_url = f"{_public_base_url()}/static/bundles/nsfw_classify_tmp/{name}"
        return classify_image_url(rel_url)
    except Exception as e:
        logger.warning("nsfw classify bytes failed: %s", e)
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def classify_image_path(image_path: Path, *, max_bytes: int = 8_000_000) -> NsfwClassifyResult:
    """Classify a local image file (watch-folder / offline paths). Requires API + NSFW sidecar for URL fetch."""
    from pathlib import Path as _Path

    p = _Path(image_path)
    if not p.is_file():
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    try:
        data = p.read_bytes()
    except OSError as e:
        logger.warning("nsfw classify path read failed: %s", e)
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    if not data:
        return NsfwClassifyResult("unknown", "", 0.0, False, None)
    return classify_image_bytes(data, suffix=p.suffix.lower() or ".jpg")
