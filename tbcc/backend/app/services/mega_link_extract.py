"""Extract file-host URLs from text/HTML and score pack volume for loot rarity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.services.linkvertise_wrap import _URL_IN_TEXT_RE

# Hosts we treat as distributable file destinations (after bypass / paste unwrap).
FILE_HOST_MARKERS: tuple[str, ...] = (
    "mega.nz",
    "mega.co.nz",
    "keep2share.cc",
    "k2s.cc",
    "tezfiles.com",
    "fboom.me",
    "pixeldrain.com",
    "gofile.io",
    "mediafire.com",
    "terabox.com",
    "terabox.app",
    "bunkr.",
    "bunkrr.",
    "bunkr.ru",
    "bunkr.si",
    "bunkr.sk",
    "bunkr.black",
    "bunkr.la",
    "epicload.com",
    "dropbox.com",
    "krakenfiles.com",
    "workupload.com",
    "cyberdrop.me",
    "cyberfile.me",
)

PASTE_HOST_MARKERS: tuple[str, ...] = (
    "rentry.co",
    "rentry.org",
    "pastetoday.com",
    "pastelink.net",
    "justpaste.it",
    "paste.ee",
    "pastebin.com",
    "pastefy.app",
)

SOPHON_HOST_MARKERS: tuple[str, ...] = (
    "newsophon.com",
    "link.newsophon.com",
    "sophon.io",
)

OBFUSCATED_HOST_MARKERS: tuple[str, ...] = (
    "linkvertise.com",
    "link-center.net",
    "link-to.net",
    "direct-link.net",
    "up-to-down.net",
    "admaven.com",
    "onepiecered.co",
    "speedy-links.com",
    "boost.ink",
    "work.ink",
    "paster.so",
    "loot-link.com",
    "lootlinks.com",
    "sub2unlock.com",
    "sub2get.com",
)

_AFFILIATE_SKIP: tuple[str, ...] = (
    "adultforce.com",
    "nodress.site",
    "nutaku.net",
    "landing.",
    "onlyfans.com",
)

_SIZE_GB_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\b",
    re.IGNORECASE,
)
_SIZE_MB_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mb|mib)\b",
    re.IGNORECASE,
)
_MEGA_FOLDER_RE = re.compile(
    r"https?://(?:mega\.nz|mega\.co\.nz)/folder/[^\s\]\)<>\"']+",
    re.IGNORECASE,
)
_OG_TITLE_RE = re.compile(
    r'<meta\s+property="og:title"\s+content="([^"]*)"',
    re.IGNORECASE,
)
_OG_DESCRIPTION_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]*)"',
    re.IGNORECASE,
)
_OG_SIZE_GB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*gb\b", re.IGNORECASE)
_OG_FILE_COUNT_RE = re.compile(r"(\d+)\s*files?\b", re.IGNORECASE)


@dataclass
class ExtractedUrl:
    url: str
    host_kind: str  # file_host | paste | obfuscated | sophon | other
    size_gb_hint: float | None = None


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def classify_url_host(url: str) -> str:
    host = _host(url)
    if not host:
        return "other"
    low = (url or "").lower()
    if host.endswith(("t.me", "telegram.me", "telegram.dog")) or "t.me/" in low:
        return "telegram"
    if "erome.com" in host:
        return "gallery_erome"
    if "bunkr." in host or host.startswith("bunkr"):
        if re.search(r"/[fv]/", low):
            return "file_host"
        return "gallery_bunkr"
    if host in ("video.twimg.com", "pbs.twimg.com") or low.endswith((".mp4", ".webm", ".mov", ".m4v")):
        return "direct_video"
    if any(m in host for m in OBFUSCATED_HOST_MARKERS):
        return "obfuscated"
    if any(m in host for m in SOPHON_HOST_MARKERS):
        return "sophon"
    if any(m in host for m in PASTE_HOST_MARKERS):
        return "paste"
    if any(m in host for m in FILE_HOST_MARKERS):
        return "file_host"
    if any(m in host for m in _AFFILIATE_SKIP):
        return "affiliate"
    return "other"


def parse_mega_folder_page_meta(html: str) -> tuple[float | None, int | None]:
    """
    Parse MEGA folder size + file count from static HTML og: tags.
    Example title: '13.73 GB folder on MEGA' · description: '698 files'.
    """
    title_m = _OG_TITLE_RE.search(html or "")
    desc_m = _OG_DESCRIPTION_RE.search(html or "")
    size_gb: float | None = None
    file_count: int | None = None
    if title_m:
        gb_m = _OG_SIZE_GB_RE.search(title_m.group(1))
        if gb_m:
            try:
                size_gb = float(gb_m.group(1))
            except ValueError:
                pass
    if desc_m:
        fc_m = _OG_FILE_COUNT_RE.search(desc_m.group(1))
        if fc_m:
            try:
                file_count = int(fc_m.group(1))
            except ValueError:
                pass
    return size_gb, file_count


def extract_urls_from_text(text: str) -> list[ExtractedUrl]:
    seen: set[str] = set()
    out: list[ExtractedUrl] = []
    for m in _URL_IN_TEXT_RE.finditer(text or ""):
        raw = m.group(0).rstrip(".,;)]")
        if raw in seen:
            continue
        seen.add(raw)
        kind = classify_url_host(raw)
        if kind == "affiliate":
            continue
        hint = parse_size_gb_hint(text, near_url=raw)
        out.append(ExtractedUrl(url=raw, host_kind=kind, size_gb_hint=hint))
    return out


def parse_size_gb_hint(text: str, *, near_url: str | None = None) -> float | None:
    """Best-effort GB from surrounding caption (e.g. epicload '8.67 GB')."""
    blob = text or ""
    if near_url and near_url in blob:
        idx = blob.find(near_url)
        blob = blob[max(0, idx - 200) : idx + len(near_url) + 200]
    for rx in (_SIZE_GB_RE,):
        m = rx.search(blob)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    m = _SIZE_MB_RE.search(blob)
    if m:
        try:
            return round(float(m.group(1)) / 1024.0, 3)
        except ValueError:
            pass
    return None


def pick_best_file_url(candidates: list[ExtractedUrl]) -> ExtractedUrl | None:
    """Prefer mega folders, then other file hosts, then paste/sophon for further resolve."""
    if not candidates:
        return None
    priority = {"file_host": 0, "sophon": 1, "paste": 2, "obfuscated": 3, "other": 4}

    def score(e: ExtractedUrl) -> tuple:
        host = _host(e.url)
        mega_folder = 0 if "mega.nz/folder" in e.url.lower() or "mega.co.nz/folder" in e.url.lower() else 1
        size = -(e.size_gb_hint or 0.0)
        return (priority.get(e.host_kind, 9), mega_folder, size)

    return sorted(candidates, key=score)[0]


def volume_to_rarity_tier(
    *,
    size_gb: float | None = None,
    host_kind: str = "file_host",
    is_folder: bool = False,
) -> int:
    """
    Loot modifier min_rarity_tier from pack volume — not explicitness.
    Single small file → lower tier; huge folder/album → vault tier.
    """
    gb = size_gb or 0.0
    if gb >= 30 or (is_folder and gb >= 15):
        return 9
    if gb >= 15 or (is_folder and gb >= 8):
        return 8
    if gb >= 8:
        return 7
    if gb >= 3 or is_folder:
        return 6
    if gb >= 1:
        return 5
    if host_kind in ("file_host", "sophon"):
        return 4
    return 3


def extract_mega_urls_from_html(html: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _MEGA_FOLDER_RE.finditer(html or ""):
        u = m.group(0).rstrip(".,;)]")
        if u not in seen:
            seen.add(u)
            out.append(u)
    for e in extract_urls_from_text(html):
        if e.host_kind == "file_host" and e.url not in seen:
            seen.add(e.url)
            out.append(e.url)
    return out
