"""
HTTP client for local CLIP categorizer sidecar (OpenCLIP ViT-B/32).

Set TBCC_CLIP_CATEGORIZE_URL=http://127.0.0.1:8002
Catalog: TBCC_CLIP_CATEGORIES_FILE (loaded by sidecar at startup)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ClipClassifyResult:
    ok: bool
    top_slug: str
    top_score: float
    margin: float
    labels: list[dict[str, Any]]
    error: str | None = None


def clip_classifier_enabled() -> bool:
    return bool((os.getenv("TBCC_CLIP_CATEGORIZE_URL") or "").strip())


def _base_url() -> str:
    return (os.getenv("TBCC_CLIP_CATEGORIZE_URL") or "").strip().rstrip("/")


def _min_confidence() -> float:
    try:
        return float(os.getenv("TBCC_CLIP_MIN_CONF", "0.08"))
    except ValueError:
        return 0.08


def _min_margin() -> float:
    try:
        return float(os.getenv("TBCC_CLIP_MIN_MARGIN", "0.02"))
    except ValueError:
        return 0.02


def clip_confident(result: ClipClassifyResult) -> bool:
    if not result.ok or not result.top_slug:
        return False
    if result.top_score < _min_confidence():
        return False
    if result.margin < _min_margin():
        return False
    return True


def classify_image_path(image_path: Path, *, top_k: int = 5, timeout: float = 60.0) -> ClipClassifyResult:
    base = _base_url()
    if not base:
        return ClipClassifyResult(False, "", 0.0, 0.0, [], "clip_disabled")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{base}/classify-path",
                json={"path": str(image_path.resolve()), "top_k": top_k},
            )
            data = r.json() if r.content else {}
    except Exception as e:
        logger.warning("clip classify path failed: %s", e)
        return ClipClassifyResult(False, "", 0.0, 0.0, [], str(e))
    if not data.get("ok"):
        return ClipClassifyResult(False, "", 0.0, 0.0, [], str(data.get("error") or "clip_error"))
    labels = data.get("labels") if isinstance(data.get("labels"), list) else []
    return ClipClassifyResult(
        ok=True,
        top_slug=str(data.get("top_slug") or ""),
        top_score=float(data.get("top_score") or 0.0),
        margin=float(data.get("margin") or 0.0),
        labels=labels,
    )


def classify_image_bytes(image_bytes: bytes, *, top_k: int = 5, timeout: float = 90.0) -> ClipClassifyResult:
    base = _base_url()
    if not base or not image_bytes or len(image_bytes) < 32:
        return ClipClassifyResult(False, "", 0.0, 0.0, [], "clip_disabled_or_empty")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{base}/classify",
                files={"file": ("image.jpg", image_bytes, "application/octet-stream")},
                params={"top_k": top_k},
            )
            data = r.json() if r.content else {}
    except Exception as e:
        logger.warning("clip classify bytes failed: %s", e)
        return ClipClassifyResult(False, "", 0.0, 0.0, [], str(e))
    if not data.get("ok"):
        return ClipClassifyResult(False, "", 0.0, 0.0, [], str(data.get("error") or "clip_error"))
    labels = data.get("labels") if isinstance(data.get("labels"), list) else []
    return ClipClassifyResult(
        ok=True,
        top_slug=str(data.get("top_slug") or ""),
        top_score=float(data.get("top_score") or 0.0),
        margin=float(data.get("margin") or 0.0),
        labels=labels,
    )


def clip_label_slugs(result: ClipClassifyResult, *, max_labels: int = 3) -> list[str]:
    if not result.ok:
        return []
    out: list[str] = []
    for row in result.labels[:max_labels]:
        slug = str(row.get("slug") or "").strip()
        if slug and slug not in out:
            out.append(slug)
    return out
