"""Rotate SFW promo image direct URLs for Buffer X posts (top-of-funnel teasers)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_POOL_JSON = Path(__file__).resolve().parent.parent / "data" / "aof_x_promo_image_pool.json"
_DIRECT_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp)(\?|$)", re.I)
_KNOWN_DIRECT_HOSTS = (
    "i.ibb.co",
    "i.imgur.com",
    "cdn.",
    "r2.dev",
    "cloudflare",
    "/static/promo/",
)


def promo_images_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_X_PROMO_IMAGES") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _pool_json_path() -> Path:
    override = (os.getenv("TBCC_X_PROMO_IMAGE_POOL_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _POOL_JSON


def _normalize_entry(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, str):
        direct = raw.strip()
        if direct.startswith("https://"):
            return {"direct_url": direct}
        return None
    if not isinstance(raw, dict):
        return None
    direct = str(raw.get("direct_url") or raw.get("url") or "").strip()
    if not direct.startswith("https://"):
        return None
    out: dict[str, str] = {"direct_url": direct}
    viewer = str(raw.get("viewer_url") or raw.get("monetized_url") or "").strip()
    if viewer.startswith("https://"):
        out["viewer_url"] = viewer
    label = str(raw.get("label") or "").strip()
    if label:
        out["label"] = label[:80]
    return out


def load_promo_image_pool() -> list[dict[str, str]]:
    """Entries from JSON file and/or TBCC_X_PROMO_IMAGE_URLS (comma-separated direct URLs)."""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    path = _pool_json_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("images") or data.get("entries") or []
            for row in rows:
                entry = _normalize_entry(row)
                if entry and entry["direct_url"] not in seen:
                    seen.add(entry["direct_url"])
                    entries.append(entry)
        except Exception as e:
            logger.warning("x promo image pool: failed to read %s: %s", path, e)

    env_urls = (os.getenv("TBCC_X_PROMO_IMAGE_URLS") or "").strip()
    for part in env_urls.split(","):
        entry = _normalize_entry(part.strip())
        if entry and entry["direct_url"] not in seen:
            seen.add(entry["direct_url"])
            entries.append(entry)

    return entries


def looks_like_direct_image_url(url: str) -> bool:
    """Heuristic: Buffer must fetch raw image bytes, not an HTML viewer page."""
    u = (url or "").strip()
    if not u.startswith("https://"):
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    if not p.netloc:
        return False
    low = u.lower()
    if _DIRECT_EXT_RE.search(p.path or ""):
        return True
    return any(marker in low for marker in _KNOWN_DIRECT_HOSTS)


def pick_promo_image(*, exclude: set[str] | None = None) -> dict[str, str] | None:
    """Random pool entry with a Buffer-safe direct_url."""
    if not promo_images_enabled():
        return None
    pool = [e for e in load_promo_image_pool() if looks_like_direct_image_url(e.get("direct_url", ""))]
    if not pool:
        return None
    blocked = {x.strip() for x in (exclude or set()) if x.strip()}
    candidates = [e for e in pool if e["direct_url"] not in blocked]
    if not candidates:
        candidates = pool
    return random.choice(candidates)


def direct_url_for_buffer(entry: dict[str, str] | None) -> str | None:
    if not entry:
        return None
    direct = str(entry.get("direct_url") or "").strip()
    if direct.startswith("https://") and looks_like_direct_image_url(direct):
        return direct
    return None
