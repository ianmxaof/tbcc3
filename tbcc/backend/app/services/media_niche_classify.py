"""
Shared niche classification: local CLIP (primary) → interchangeable vision LLM (gap fill).

Used by watch-folder organizer, import enrich, and extension send enrich.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _is_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def watch_clip_niche_subfolders_enabled() -> bool:
    if not clip_niche_enabled():
        return False
    raw = (os.getenv("TBCC_WATCH_CLIP_NICHE_SUBFOLDERS") or "").strip()
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    return True


def clip_niche_enabled() -> bool:
    from app.services.clip_classifier import clip_classifier_enabled

    return clip_classifier_enabled()


def vision_gap_fill_enabled() -> bool:
    from app.services.vision_llm import vision_llm_enabled

    return vision_llm_enabled()


def _safe_folder_segment(raw: str, *, fallback: str = "other") -> str:
    s = re.sub(r"[^\w\-]+", "-", (raw or "").strip().lower()).strip("-")
    return (s[:48] or fallback) if s else fallback


def _vision_on_low_clip() -> bool:
    if not vision_gap_fill_enabled():
        return False
    raw = (os.getenv("TBCC_VISION_LLM_ON_LOW_CLIP") or "").strip()
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    return True


def _clip_top_slugs(result, *, max_labels: int = 5) -> list[str]:
    from app.services.clip_classifier import clip_label_slugs

    return clip_label_slugs(result, max_labels=max_labels)


def classify_image_path_niche(path: Path, *, top_k: int = 5) -> dict[str, Any]:
    """CLIP on local path; optional vision LLM when CLIP confidence is low."""
    from app.services.clip_classifier import classify_image_path, clip_confident
    from app.services.vision_llm import analyze_image_bytes

    out: dict[str, Any] = {
        "clip_enabled": clip_niche_enabled(),
        "vision_enabled": vision_gap_fill_enabled(),
        "primary_slug": "",
        "primary_source": "",
        "clip": None,
        "vision": None,
        "labels": [],
    }
    if not clip_niche_enabled():
        return out

    clip_res = classify_image_path(path, top_k=top_k)
    out["clip"] = {
        "ok": clip_res.ok,
        "top_slug": clip_res.top_slug,
        "top_score": clip_res.top_score,
        "margin": clip_res.margin,
        "confident": clip_confident(clip_res),
        "labels": clip_res.labels[:top_k],
    }
    if clip_res.ok and clip_res.top_slug and clip_confident(clip_res):
        out["primary_slug"] = clip_res.top_slug
        out["primary_source"] = "clip"
        out["labels"] = _clip_top_slugs(clip_res, max_labels=3)
        return out

    if not _vision_on_low_clip():
        if clip_res.ok and clip_res.top_slug:
            out["primary_slug"] = clip_res.top_slug
            out["primary_source"] = "clip_low_conf"
            out["labels"] = _clip_top_slugs(clip_res, max_labels=2)
        return out

    try:
        raw = path.read_bytes()[:4_000_000]
    except OSError:
        return out
    if len(raw) < 32:
        return out
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    allowed = _clip_top_slugs(clip_res, max_labels=8) if clip_res.ok else None
    vision = analyze_image_bytes(raw, mime=mime, allowed_slugs=allowed)
    if vision:
        out["vision"] = vision
        slug = str(vision.get("primary_slug") or vision.get("sort_folder") or "").strip()
        if slug:
            out["primary_slug"] = _safe_folder_segment(slug)
            out["primary_source"] = "vision_llm"
        elif clip_res.ok and clip_res.top_slug:
            out["primary_slug"] = clip_res.top_slug
            out["primary_source"] = "clip"
        facets = vision.get("facets")
        labels: list[str] = []
        if out["primary_slug"]:
            labels.append(out["primary_slug"])
        if isinstance(facets, list):
            for f in facets:
                s = _safe_folder_segment(str(f))
                if s and s not in labels:
                    labels.append(s)
        out["labels"] = labels[:5]
    elif clip_res.ok and clip_res.top_slug:
        out["primary_slug"] = clip_res.top_slug
        out["primary_source"] = "clip_low_conf"
        out["labels"] = _clip_top_slugs(clip_res, max_labels=2)
    return out


def classify_image_bytes_niche(image_bytes: bytes, *, mime: str = "image/jpeg", top_k: int = 5) -> dict[str, Any]:
    """CLIP on bytes; optional vision LLM when CLIP confidence is low."""
    from app.services.clip_classifier import classify_image_bytes, clip_confident
    from app.services.vision_llm import analyze_image_bytes

    out: dict[str, Any] = {
        "clip_enabled": clip_niche_enabled(),
        "vision_enabled": vision_gap_fill_enabled(),
        "primary_slug": "",
        "primary_source": "",
        "clip": None,
        "vision": None,
        "labels": [],
    }
    if not image_bytes or len(image_bytes) < 32:
        return out
    if not clip_niche_enabled():
        return out

    clip_res = classify_image_bytes(image_bytes, top_k=top_k)
    out["clip"] = {
        "ok": clip_res.ok,
        "top_slug": clip_res.top_slug,
        "top_score": clip_res.top_score,
        "margin": clip_res.margin,
        "confident": clip_confident(clip_res),
        "labels": clip_res.labels[:top_k],
    }
    if clip_res.ok and clip_res.top_slug and clip_confident(clip_res):
        out["primary_slug"] = clip_res.top_slug
        out["primary_source"] = "clip"
        out["labels"] = _clip_top_slugs(clip_res, max_labels=3)
        return out

    if not _vision_on_low_clip():
        if clip_res.ok and clip_res.top_slug:
            out["primary_slug"] = clip_res.top_slug
            out["primary_source"] = "clip_low_conf"
            out["labels"] = _clip_top_slugs(clip_res, max_labels=2)
        return out

    allowed = _clip_top_slugs(clip_res, max_labels=8) if clip_res.ok else None
    vision = analyze_image_bytes(image_bytes, mime=mime, allowed_slugs=allowed)
    if vision:
        out["vision"] = vision
        slug = str(vision.get("primary_slug") or vision.get("sort_folder") or "").strip()
        if slug:
            out["primary_slug"] = _safe_folder_segment(slug)
            out["primary_source"] = "vision_llm"
        elif clip_res.ok and clip_res.top_slug:
            out["primary_slug"] = clip_res.top_slug
            out["primary_source"] = "clip"
        facets = vision.get("facets")
        labels: list[str] = []
        if out["primary_slug"]:
            labels.append(out["primary_slug"])
        if isinstance(facets, list):
            for f in facets:
                s = _safe_folder_segment(str(f))
                if s and s not in labels:
                    labels.append(s)
        out["labels"] = labels[:5]
    elif clip_res.ok and clip_res.top_slug:
        out["primary_slug"] = clip_res.top_slug
        out["primary_source"] = "clip_low_conf"
        out["labels"] = _clip_top_slugs(clip_res, max_labels=2)
    return out


def niche_slug_for_folder(meta: dict[str, Any] | None) -> str:
    """Best folder slug from niche classify meta or legacy LLM sidecar."""
    if not meta:
        return ""
    niche = meta.get("niche") or {}
    if isinstance(niche, dict):
        slug = str(niche.get("primary_slug") or "").strip()
        if slug:
            return _safe_folder_segment(slug)
    llm = meta.get("llm")
    if isinstance(llm, dict):
        sort = str(llm.get("sort_folder") or llm.get("niche") or "").strip()
        if sort:
            return _safe_folder_segment(sort)
    return ""
