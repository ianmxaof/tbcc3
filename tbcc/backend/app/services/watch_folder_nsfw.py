"""NSFW tier/class + CLIP niche + optional vision LLM for watch-folder sorting."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic", ".jfif"})
_CLASS_FOLDER_NAMES = {
    "neutral": "neutral",
    "drawings": "drawings",
    "sexy": "sexy",
    "porn": "porn",
    "hentai": "hentai",
}


def _is_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def watch_nsfw_tier_subfolders_enabled() -> bool:
    return _is_truthy(os.environ.get("TBCC_WATCH_NSFW_TIER_SUBFOLDERS"))


def watch_nsfw_class_subfolders_enabled() -> bool:
    return _is_truthy(os.environ.get("TBCC_WATCH_NSFW_CLASS_SUBFOLDERS"))


def watch_llm_tag_enabled() -> bool:
    """Legacy flag — prefer TBCC_VISION_LLM_PROVIDER=openrouter|openai|ollama."""
    from app.services.vision_llm import vision_llm_enabled

    if vision_llm_enabled():
        return True
    return _is_truthy(os.environ.get("TBCC_WATCH_LLM_TAG")) and bool(
        (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    )


def is_watch_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def _safe_folder_segment(raw: str, *, fallback: str = "unknown") -> str:
    import re

    s = re.sub(r"[^\w\-]+", "-", (raw or "").strip().lower()).strip("-")
    return (s[:48] or fallback) if s else fallback


def classify_watch_image(path: Path) -> dict[str, Any]:
    """Run HamkerCat NSFW sidecar on a local image."""
    from app.services.nsfw_classifier import classify_image_path, nsfw_classifier_enabled

    out: dict[str, Any] = {
        "nsfw_enabled": nsfw_classifier_enabled(),
        "nsfw_tier": "unknown",
        "top_class": "",
        "top_probability": 0.0,
        "confident": False,
    }
    if not nsfw_classifier_enabled() or not is_watch_image(path):
        return out
    try:
        res = classify_image_path(path)
    except Exception as e:
        logger.warning("watch nsfw classify failed %s: %s", path.name, e)
        return out
    out["nsfw_tier"] = res.nsfw_tier or "unknown"
    out["top_class"] = res.top_class or ""
    out["top_probability"] = float(res.top_probability or 0.0)
    out["confident"] = bool(res.confident)
    return out


def classify_watch_niche(path: Path) -> dict[str, Any]:
    """CLIP + optional vision LLM niche classification."""
    from app.services.media_niche_classify import classify_image_path_niche

    if not is_watch_image(path):
        return {}
    try:
        return classify_image_path_niche(path)
    except Exception as e:
        logger.warning("watch niche classify failed %s: %s", path.name, e)
        return {}


def image_library_subdir(category: str, path: Path, nsfw_meta: dict[str, Any] | None) -> str:
    """
    Relative path under library root.
    Images: Images/{tier}/{class}/{niche_slug}/ when enabled.
    """
    from app.services.media_niche_classify import niche_slug_for_folder, watch_clip_niche_subfolders_enabled

    if category != "Images" or not watch_nsfw_tier_subfolders_enabled() or not is_watch_image(path):
        return category
    meta = nsfw_meta or {}
    tier = _safe_folder_segment(str(meta.get("nsfw_tier") or "unknown"), fallback="unknown")
    parts = ["Images", tier]
    if watch_nsfw_class_subfolders_enabled():
        top = str(meta.get("top_class") or "").strip().lower()
        cls = _CLASS_FOLDER_NAMES.get(top) or _safe_folder_segment(top, fallback="unclassified")
        if cls:
            parts.append(cls)
    if watch_clip_niche_subfolders_enabled():
        niche_slug = niche_slug_for_folder(meta)
        if niche_slug and niche_slug not in ("other", "unknown", "unclassified"):
            parts.append(niche_slug)
    return "/".join(parts)


def sidecar_path_for(dest: Path) -> Path:
    return dest.with_name(dest.stem + ".tbcc-meta.json")


def write_watch_sidecar(dest: Path, meta: dict[str, Any]) -> None:
    try:
        sidecar_path_for(dest).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("watch sidecar write failed %s: %s", dest.name, e)


def llm_niche_metadata_for_image(path: Path) -> dict[str, Any]:
    """Vision LLM pass (interchangeable provider) for watch sidecars."""
    from app.services.vision_llm import analyze_image_bytes, vision_llm_enabled

    if not watch_llm_tag_enabled() or not is_watch_image(path):
        return {}
    try:
        raw = path.read_bytes()[:4_000_000]
    except OSError:
        return {}
    if len(raw) < 32:
        return {}
    if not vision_llm_enabled():
        return {}
    import mimetypes

    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    try:
        parsed = analyze_image_bytes(raw, mime=mime)
        if isinstance(parsed.get("facets"), list):
            parsed["facets"] = [str(x).strip()[:64] for x in parsed["facets"] if str(x).strip()][:10]
        return parsed
    except Exception as e:
        logger.warning("watch vision LLM failed %s: %s", path.name, e)
        return {}


def build_watch_metadata(path: Path) -> dict[str, Any]:
    meta = classify_watch_image(path)
    meta["source_file"] = path.name

    niche = classify_watch_niche(path)
    if niche:
        meta["niche"] = niche
        if meta.get("nsfw_tier") == "unknown" and isinstance(niche.get("vision"), dict):
            vt = str((niche["vision"] or {}).get("nsfw_tier") or "").strip().lower()
            if vt:
                meta["nsfw_tier"] = vt

    if watch_llm_tag_enabled() and not (niche.get("vision") if niche else None):
        llm = llm_niche_metadata_for_image(path)
        if llm:
            meta["llm"] = llm
            if meta.get("nsfw_tier") == "unknown" and llm.get("nsfw_tier"):
                meta["nsfw_tier"] = str(llm["nsfw_tier"]).strip().lower()
    return meta
