"""
Fetch page metadata from a self-hosted Lustpress instance for URL → tag hints.

TBCC_LUSTPRESS_URL=http://127.0.0.1:3000 (no trailing slash).
Supports pornhub, xvideos, xnxx, redtube, xhamster, youporn, eporner page URLs.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9\-]+")


@dataclass
class LustpressMetadata:
    platform: str
    title: str = ""
    tag_names: list[str] = field(default_factory=list)
    category_names: list[str] = field(default_factory=list)
    performer_names: list[str] = field(default_factory=list)
    raw: dict[str, Any] | None = None


def lustpress_enabled() -> bool:
    return bool((os.getenv("TBCC_LUSTPRESS_URL") or "").strip())


def _base() -> str:
    return (os.getenv("TBCC_LUSTPRESS_URL") or "").strip().rstrip("/")


def _platform_from_host(host: str) -> str | None:
    h = host.lower()
    if "pornhub.com" in h:
        return "pornhub"
    if "xvideos.com" in h:
        return "xvideos"
    if "xnxx.com" in h:
        return "xnxx"
    if "redtube.com" in h:
        return "redtube"
    if "xhamster.com" in h:
        return "xhamster"
    if "youporn.com" in h:
        return "youporn"
    if "eporner.com" in h:
        return "eporner"
    return None


def _extract_id(platform: str, url: str) -> str | None:
    try:
        p = urlparse(url)
        path = (p.path or "").strip("/")
        if not path:
            return None
        if platform == "pornhub":
            # view_video.php?viewkey=… or /view/ph…
            if "viewkey=" in url:
                from urllib.parse import parse_qs

                q = parse_qs(p.query)
                vk = q.get("viewkey", [None])[0]
                if vk:
                    return str(vk)
            m = re.search(r"/view/([^/?#]+)", path)
            if m:
                return m.group(1)
            return path.split("/")[-1] or None
        if platform in ("xvideos", "xnxx", "xhamster", "youporn"):
            return path  # lustpress expects full path slug
        if platform == "redtube":
            m = re.search(r"/(\d+)", path)
            return m.group(1) if m else path.split("/")[-1]
        if platform == "eporner":
            return path
    except Exception:
        return None
    return path or None


def _collect_strings(obj: Any, keys: tuple[str, ...], out: list[str], limit: int = 24) -> None:
    if len(out) >= limit:
        return
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
                    elif isinstance(item, dict):
                        for nk in ("name", "tag", "title", "label", "category", "pornstar"):
                            x = item.get(nk)
                            if isinstance(x, str) and x.strip():
                                out.append(x.strip())
        for v in obj.values():
            if len(out) >= limit:
                break
            if isinstance(v, (dict, list)):
                _collect_strings(v, keys, out, limit)
    elif isinstance(obj, list):
        for item in obj:
            if len(out) >= limit:
                break
            _collect_strings(item, keys, out, limit)


def _parse_lustpress_body(platform: str, body: Any) -> LustpressMetadata:
    meta = LustpressMetadata(platform=platform, raw=body if isinstance(body, dict) else None)
    if not isinstance(body, dict):
        return meta
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    if isinstance(data, dict):
        meta.title = str(data.get("title") or data.get("name") or "")[:512]
    tags: list[str] = []
    cats: list[str] = []
    performers: list[str] = []
    _collect_strings(data, ("tags", "tag", "tag_name", "keywords"), tags)
    _collect_strings(data, ("categories", "category", "category_name"), cats)
    _collect_strings(data, ("pornstars", "pornstar", "models", "model", "actors", "actor"), performers)
    if meta.title:
        tags.append(meta.title)
    meta.tag_names = _dedupe_strings(tags, 20)
    meta.category_names = _dedupe_strings(cats, 12)
    meta.performer_names = _dedupe_strings(performers, 8)
    return meta


def _dedupe_strings(items: list[str], cap: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        s = str(raw).strip()
        if not s or len(s) < 2:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:128])
        if len(out) >= cap:
            break
    return out


def fetch_metadata_for_url(page_url: str, *, timeout: float = 25.0) -> LustpressMetadata | None:
    base = _base()
    if not base or not page_url.startswith(("http://", "https://")):
        return None
    try:
        host = (urlparse(page_url).hostname or "").lower()
    except Exception:
        return None
    platform = _platform_from_host(host)
    if not platform:
        return None
    vid = _extract_id(platform, page_url)
    if not vid:
        return None
    api_url = f"{base}/{platform}/get"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(api_url, params={"id": vid})
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        logger.debug("lustpress fetch failed platform=%s: %s", platform, e)
        return None
    return _parse_lustpress_body(platform, body)


def metadata_to_tag_slugs(meta: LustpressMetadata) -> list[tuple[str, str, str | None]]:
    """Return (slug, display_name, category) tuples for ensure_tag."""
    rows: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()

    def add(name: str, category: str | None) -> None:
        slug = _SLUG_SAFE.sub("-", name.lower().replace(" ", "-"))[:64].strip("-") or "tag"
        if slug in seen:
            return
        seen.add(slug)
        rows.append((slug, name[:128], category))

    add(f"src-{meta.platform}", meta.platform, "source")
    for c in meta.category_names:
        add(c, "category")
    for t in meta.tag_names:
        add(t, "topic")
    for p in meta.performer_names:
        add(p, "performer")
    return rows[:32]
