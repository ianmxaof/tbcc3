"""Unwrap obfuscated link gates: LV dynamic decode → publisher session → bypass.vip."""

from __future__ import annotations

import logging
import os
import re
from base64 import b64decode
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.services.bypass_vip_client import bypass_configured, resolve_bypass_url
from app.services.link_gate_provider import GATE_HOST_SUFFIXES, publisher_id_from_env

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_LV_DYNAMIC_RE = re.compile(r"/dynamic", re.IGNORECASE)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def is_obfuscated_gate_url(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in GATE_HOST_SUFFIXES)


def linkvertise_publisher_id_from_url(url: str) -> str | None:
    """Extract publisher id from link-center.net/{pub}/... paths."""
    try:
        parts = [p for p in (urlparse(url).path or "").split("/") if p]
    except Exception:
        return None
    if not parts:
        return None
    if parts[0].isdigit():
        return parts[0]
    return None


def unwrap_linkvertise_dynamic(url: str) -> str | None:
    """
    Decode destination from Linkvertise dynamic links (?r=base64).
    No HTTP or cookies required.
    """
    parsed = urlparse(url)
    if not _LV_DYNAMIC_RE.search(parsed.path or ""):
        return None
    qs = parse_qs(parsed.query or "")
    token = (qs.get("r") or [None])[0]
    if not token:
        return None
    try:
        pad = "=" * (-len(token) % 4)
        raw = b64decode((token + pad).encode("ascii"))
        dest = unquote(raw.decode("utf-8", errors="replace")).strip()
        if dest.startswith(("http://", "https://")):
            return dest
    except Exception as e:
        logger.debug("unwrap_linkvertise_dynamic failed: %s", e)
    return None


def _linkvertise_cookie_header() -> str | None:
    inline = (os.getenv("TBCC_LINKVERTISE_COOKIE") or "").strip()
    if inline:
        return inline
    path = (os.getenv("TBCC_LINKVERTISE_COOKIE_FILE") or "").strip()
    if not path:
        return None
    try:
        from pathlib import Path

        p = Path(path)
        if not p.is_file():
            return None
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return None
        if "=" in text and ";" not in text.split("\n")[0]:
            return text.replace("\n", "; ").strip()
        return text.replace("\n", " ").strip()
    except Exception as e:
        logger.warning("linkvertise cookie file read failed: %s", e)
        return None


def resolve_linkvertise_publisher_session(url: str) -> str | None:
    """
    Follow redirects using publisher cookies (own publisher ID links only).
    Works when your logged-in LV account skips ads on your links.
    """
    cookie = _linkvertise_cookie_header()
    if not cookie:
        return None
    try:
        own_pub = publisher_id_from_env()
    except ValueError:
        return None
    url_pub = linkvertise_publisher_id_from_url(url)
    if url_pub and url_pub != own_pub:
        return None

    timeout = float(os.getenv("TBCC_LINKVERTISE_SESSION_TIMEOUT_S") or "25")
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Cookie": cookie,
            },
        ) as client:
            r = client.get(url)
        final = str(r.url)
        if final and final != url and final.startswith(("http://", "https://")):
            if not is_obfuscated_gate_url(final):
                return final
        # Some gates embed destination in HTML meta refresh / JS — light heuristic
        body = r.text or ""
        for pattern in (
            r'url=(https?://[^\s"\'<>]+)',
            r'location\.href\s*=\s*["\'](https?://[^"\']+)',
            r'window\.location\s*=\s*["\'](https?://[^"\']+)',
        ):
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if cand.startswith(("http://", "https://")) and not is_obfuscated_gate_url(cand):
                    return cand
    except Exception as e:
        logger.debug("resolve_linkvertise_publisher_session failed: %s", e)
    return None


def resolve_obfuscated_url(url: str) -> tuple[str | None, str | None]:
    """
    Resolver chain for scrape pipeline:
      1) Linkvertise dynamic ?r= decode (free, local)
      2) Publisher session cookies (own LV links)
      3) bypass.vip (paid / third-party)
    Returns (final_url, error_code).
    """
    if not is_obfuscated_gate_url(url):
        return None, "not_gate_host"

    decoded = unwrap_linkvertise_dynamic(url)
    if decoded:
        return decoded, None

    session_dest = resolve_linkvertise_publisher_session(url)
    if session_dest:
        return session_dest, None

    if not bypass_configured():
        return None, "bypass_not_configured"
    result = resolve_bypass_url(url)
    if result.ok and result.final_url:
        return result.final_url, None
    return None, result.error_message or "bypass_failed"
