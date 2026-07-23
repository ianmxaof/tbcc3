"""Migrate dead Linkvertise gates to Work.ink (or other providers)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.services.link_gate_provider import (
    PROVIDER_WORKINK,
    is_gate_host,
    is_linkvertise_host,
    wrap_gate_url,
)
from app.services.link_gate_unwrap import is_obfuscated_gate_url, resolve_obfuscated_url, unwrap_linkvertise_dynamic

_DEST_NOTE_RE = re.compile(r"\|dest=(https?://[^\|]+)")
_URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.I)

# Legacy link-center slugs → raw destination (created before LV policy takedown).
_LEGACY_LV_SLUG_DEST: dict[str, str] = {
    "irj3uxd3iYV": "https://t.me/+hMQzGsBFjF02MDkx",
    "7XeubkKSFA8j": "https://t.me/addlist/r-7_7CGIkExhMDcx",
    "XeuokKSFA8j": "https://t.me/addlist/r-7_7CGIkExhMDcx",
    "DgIo85a7oux0": "https://telegram.me/aofmainhub",
}

_WRAP_CACHE: dict[tuple[str, str], str] = {}


def _slug_from_gate_url(url: str) -> str | None:
    try:
        parts = [p for p in (urlparse(url).path or "").split("/") if p]
    except Exception:
        return None
    return parts[-1] if parts else None


def resolve_gate_destination(
    url: str,
    *,
    source_note: str | None = None,
    try_bypass: bool = False,
) -> str | None:
    """Best-effort destination behind a gated URL (Linkvertise static/dynamic)."""
    if not is_obfuscated_gate_url(url):
        return None

    decoded = unwrap_linkvertise_dynamic(url)
    if decoded:
        return decoded

    if source_note:
        m = _DEST_NOTE_RE.search(source_note)
        if m:
            return m.group(1).strip()

    slug = _slug_from_gate_url(url)
    if slug and slug in _LEGACY_LV_SLUG_DEST:
        return _LEGACY_LV_SLUG_DEST[slug]

    if is_linkvertise_host(url) and try_bypass:
        dest, _err = resolve_obfuscated_url(url)
        if dest and not is_obfuscated_gate_url(dest):
            return dest

    return None


def rewrap_linkvertise_gate(
    url: str,
    *,
    provider: str = PROVIDER_WORKINK,
    source_note: str | None = None,
    try_bypass: bool = False,
) -> str | None:
    """Replace a dead Linkvertise URL with a fresh gate on another provider."""
    u = (url or "").strip().split()[0]
    if not u.startswith("http") or not is_linkvertise_host(u):
        return None
    dest = resolve_gate_destination(u, source_note=source_note, try_bypass=try_bypass)
    if not dest or is_gate_host(dest):
        return None
    cache_key = (provider, dest)
    if cache_key in _WRAP_CACHE:
        return _WRAP_CACHE[cache_key]
    wrapped, _prov = wrap_gate_url(dest, provider=provider, seed=dest)
    _WRAP_CACHE[cache_key] = wrapped
    return wrapped


def replace_linkvertise_urls_in_text(
    text: str,
    *,
    provider: str = PROVIDER_WORKINK,
    source_note: str | None = None,
    try_bypass: bool = False,
) -> tuple[str, list[dict]]:
    """Swap link-center / Linkvertise URLs in a string for Work.ink equivalents."""
    if not text:
        return text or "", []

    changes: list[dict] = []
    out = text

    for match in list(_URL_RE.finditer(text)):
        old = match.group(0)
        if not is_linkvertise_host(old):
            continue
        new = rewrap_linkvertise_gate(
            old,
            provider=provider,
            source_note=source_note,
            try_bypass=try_bypass,
        )
        if new and new != old:
            out = out.replace(old, new)
            changes.append({"from": old, "to": new})

    return out, changes
