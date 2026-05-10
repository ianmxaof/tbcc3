from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

CrawlerAdapter = Literal["auto", "erome"]

_IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif")
_VIDEO_EXTS = ("mp4", "webm", "mov", "m4v", "mkv")
_MEDIA_EXTS = _IMAGE_EXTS + _VIDEO_EXTS
_MEDIA_EXT_RE = "|".join(_MEDIA_EXTS)


@dataclass
class CrawlerMediaItem:
    url: str
    media_type: str
    filename: str | None = None
    thumbnail_url: str | None = None


@dataclass
class CrawlerResult:
    adapter: str
    source_url: str
    title: str | None
    items: list[CrawlerMediaItem]
    warnings: list[str]


def _browser_headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _is_erome_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "erome.com" or host.endswith(".erome.com")


def _clean_url(raw: str) -> str:
    value = html.unescape(str(raw or "").strip())
    value = value.replace("\\/", "/")
    value = value.replace("\\u0026", "&")
    value = value.strip(" \t\r\n\"'`<>")
    return value


def _media_type_for_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if any(path.endswith("." + ext) for ext in _VIDEO_EXTS):
        return "video"
    return "image"


def _is_erome_thumbnail_url(url: str) -> bool:
    try:
        parts = [p.lower() for p in urlparse(url).path.split("/") if p]
    except Exception:
        return False
    return "thumbs" in parts or "thumbnail" in parts


def _filename_for_url(url: str) -> str | None:
    try:
        name = urlparse(url).path.rsplit("/", 1)[-1]
    except Exception:
        return None
    name = html.unescape(name or "").strip()
    return name or None


def _stem_for_filename(filename: str | None) -> str:
    name = str(filename or "")
    stem = name.rsplit(".", 1)[0]
    return re.sub(r"_(?:\d+p|source|original)$", "", stem, flags=re.I)


def _extract_title(page: str) -> str | None:
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]
    for pattern in patterns:
        m = re.search(pattern, page, flags=re.I | re.S)
        if not m:
            continue
        value = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        if value:
            return value
    return None


def _extract_media_urls(page: str) -> list[str]:
    candidates: list[tuple[int, str]] = []

    attr_re = re.compile(
        rf'\b(?:src|href|data-src|data-url|data-video|data-video-src|poster)=["\']([^"\']+\.({_MEDIA_EXT_RE})(?:\?[^"\']*)?)["\']',
        flags=re.I,
    )
    for m in attr_re.finditer(page):
        candidates.append((m.start(1), m.group(1)))

    direct_re = re.compile(
        rf"https?:\\?/\\?/[^\"'<>\\\s]+?\.({_MEDIA_EXT_RE})(?:\?[^\"'<>\\\s]*)?",
        flags=re.I,
    )
    for m in direct_re.finditer(page):
        candidates.append((m.start(), m.group(0)))

    candidates.sort(key=lambda pair: pair[0])
    seen: set[str] = set()
    out: list[str] = []
    for _, raw in candidates:
        url = _clean_url(raw)
        if not url.startswith(("http://", "https://")):
            continue
        if not _is_erome_url(url):
            continue
        if _is_erome_thumbnail_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _album_id_from_url(url: str) -> str | None:
    try:
        m = re.search(r"/a/([A-Za-z0-9_-]+)", urlparse(url).path)
        return m.group(1) if m else None
    except Exception:
        return None


async def _fetch_erome_album(url: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=45.0, headers=_browser_headers()) as client:
        last_response: httpx.Response | None = None
        for attempt in range(5):
            response = await client.get(url)
            last_response = response
            response.raise_for_status()
            if b" Please wait a few moments " not in response.content[:900]:
                return response.text, warnings
            if attempt == 0:
                warnings.append("Erome asked for a short browser check; retried like a downloader plugin.")
            await asyncio.sleep(5.0)
    assert last_response is not None
    return last_response.text, warnings


async def resolve_erome_album(url: str, limit: int = 250) -> CrawlerResult:
    if not _is_erome_url(url) or "/a/" not in urlparse(url).path:
        raise ValueError("Erome crawler expects an album URL like https://www.erome.com/a/<id>.")

    page, warnings = await _fetch_erome_album(url)
    album_id = _album_id_from_url(url)
    urls = _extract_media_urls(page)
    if album_id:
        album_urls = [u for u in urls if f"/{album_id}/" in urlparse(u).path]
        if album_urls:
            urls = album_urls

    if limit > 0:
        urls = urls[:limit]

    video_stems = {
        _stem_for_filename(_filename_for_url(u))
        for u in urls
        if _media_type_for_url(u) == "video"
    }
    poster_by_stem = {
        _stem_for_filename(_filename_for_url(u)): u
        for u in urls
        if _media_type_for_url(u) == "image" and _stem_for_filename(_filename_for_url(u)) in video_stems
    }
    items: list[CrawlerMediaItem] = []
    for u in urls:
        media_type = _media_type_for_url(u)
        filename = _filename_for_url(u)
        stem = _stem_for_filename(filename)
        if media_type == "image" and stem in video_stems:
            continue
        items.append(
            CrawlerMediaItem(
                url=u,
                media_type=media_type,
                filename=filename,
                thumbnail_url=poster_by_stem.get(stem) if media_type == "video" else None,
            )
        )
    if not items:
        warnings.append("No direct Erome media URLs were found in the album HTML.")

    return CrawlerResult(
        adapter="erome",
        source_url=url,
        title=_extract_title(page),
        items=items,
        warnings=warnings,
    )


async def resolve_crawler_url(url: str, adapter: CrawlerAdapter = "auto", limit: int = 250) -> dict:
    clean = str(url or "").strip()
    if not clean.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://.")
    selected = adapter
    if adapter == "auto":
        selected = "erome" if _is_erome_url(clean) and "/a/" in urlparse(clean).path else "auto"
    if selected == "erome":
        return asdict(await resolve_erome_album(clean, limit=limit))
    raise ValueError("No crawler adapter is available for this URL yet.")
