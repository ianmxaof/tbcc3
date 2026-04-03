"""
Detect TBCC API URLs that must not be fetched via HTTP (recursive 502 via Vite proxy).

When `Media.source_channel` was set to a dashboard thumbnail URL like
`http://localhost:5173/api/media/{id}/thumbnail`, the thumbnail handler would
HTTP-fetch that URL, which proxied back to the same endpoint → infinite loop → 502.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


_MEDIA_PATH_RE = re.compile(r"/media/(\d+)/(thumbnail|file)(?:/|$)", re.IGNORECASE)


def looks_like_tbcc_internal_media_url(url: str) -> bool:
    """
    True if `url` points at this app's /media/{id}/thumbnail|file on loopback.

    Includes Vite dev URLs (/api/media/...) and direct backend URLs (/media/...).
    """
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1"):
        return False
    path = p.path or ""
    if "/media/" not in path:
        return False
    return _MEDIA_PATH_RE.search(path) is not None


def sanitize_import_source_url(url: str) -> str:
    """Avoid storing self-referential TBCC URLs as source_channel (use Telegram path instead)."""
    if looks_like_tbcc_internal_media_url(url):
        return "extension:tbcc-internal-url-omitted"
    return url
