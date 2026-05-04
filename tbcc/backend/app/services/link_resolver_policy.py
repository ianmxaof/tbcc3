"""URL validation and lightweight risk hints before calling a bypass provider."""

from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_SCHEMES = frozenset(
    ("file", "javascript", "vbscript", "data", "blob", "about", "chrome", "ssh", "ftp")
)
_SUSPICIOUS_SUFFIX = re.compile(
    r"\.(exe|msi|apk|bat|cmd|ps1|scr|dll|jar)(\?|$)", re.IGNORECASE
)


def normalize_input_url(raw: str) -> tuple[str | None, str | None]:
    """
    Returns (normalized_url, reason_code) where reason_code is set on hard block.
    normalized_url is suitable for provider calls.
    """
    s = (raw or "").strip()
    if not s:
        return None, "empty_url"
    if len(s) > 8192:
        return None, "url_too_long"
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", s):
        s = "https://" + s
    try:
        parsed = urlparse(s)
    except Exception:
        return None, "invalid_url"
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        return None, "blocked_scheme"
    if scheme not in ("http", "https"):
        return None, "unsupported_scheme"
    host = (parsed.hostname or "").lower()
    if not host:
        return None, "missing_host"
    if host in ("localhost", "0.0.0.0"):
        return None, "blocked_host"
    try:
        if host.startswith("[") and host.endswith("]"):
            ipaddress.ip_address(host[1:-1])
        elif re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return None, "blocked_host"
    except ValueError:
        pass
    return s, None


def risk_level_for_url(url: str, final_url: str | None = None) -> str:
    """Heuristic only — not malware analysis."""
    check = f"{url} {final_url or ''}"
    if _SUSPICIOUS_SUFFIX.search(check):
        return "high"
    if "bit.ly" in check or "tinyurl" in check.lower():
        return "medium"
    return "low"
