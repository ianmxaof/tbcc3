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

CrawlerAdapter = Literal["auto", "erome", "onlyfans", "bunkr", "madeporn", "generic"]

_RATE_LIMITS: dict[str, float] = {}
_RATE_LIMIT_INTERVAL = 1.0

async def _rate_limit(domain: str, min_interval: float = _RATE_LIMIT_INTERVAL) -> None:
    import time
    now = time.monotonic()
    last = _RATE_LIMITS.get(domain, 0.0)
    wait = max(0.0, min_interval - (now - last))
    if wait > 0:
        await asyncio.sleep(wait)
    _RATE_LIMITS[domain] = time.monotonic()

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


_EROME_RESERVED_SEGMENTS = frozenset({
    "a",
    "search",
    "explore",
    "popular",
    "hot",
    "login",
    "register",
    "oauth",
    "api",
    "static",
    "video",
    "m",
    "i",
    "privacy",
    "terms",
    "dmca",
    "contact",
})

_EROME_ALBUM_LINK_RE = re.compile(
    r"""(?:href|data-url)=["'](?:https?://(?:www\.)?erome\.com)?/a/([A-Za-z0-9_-]+)""",
    flags=re.I,
)
_EROME_ALBUM_DIRECT_RE = re.compile(
    r"https?://(?:www\.)?erome\.com/a/([A-Za-z0-9_-]+)",
    flags=re.I,
)


def _classify_erome_url(url: str) -> Literal["album", "profile", "search", "other"]:
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0].lower() == "a":
            return "album"
        if parts and parts[0].lower() == "search":
            return "search"
        if parts and parts[0].lower() not in _EROME_RESERVED_SEGMENTS:
            return "profile"
    except Exception:
        pass
    return "other"


def _normalize_erome_album_url(album_id: str) -> str:
    return f"https://www.erome.com/a/{album_id}"


def _extract_erome_album_urls(page: str, base_url: str | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for pattern in (_EROME_ALBUM_LINK_RE, _EROME_ALBUM_DIRECT_RE):
        for m in pattern.finditer(page or ""):
            album_id = m.group(1)
            if not album_id or album_id in seen:
                continue
            seen.add(album_id)
            out.append(_normalize_erome_album_url(album_id))
    return out


def _erome_listing_page_urls(url: str, page_html: str, max_pages: int) -> list[str]:
    """Return listing URLs to fetch (current + pagination hints)."""
    from urllib.parse import parse_qs, urlencode, urlunparse

    urls = [url]
    if max_pages <= 1:
        return urls
    try:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        for m in re.finditer(r'href=["\']([^"\']*\?[^"\']*page=(\d+)[^"\']*)["\']', page_html, flags=re.I):
            page_num = int(m.group(2))
            if 1 < page_num <= max_pages:
                candidate = _clean_url(html.unescape(m.group(1)))
                if candidate.startswith("/"):
                    candidate = base + candidate
                if candidate.startswith("http") and candidate not in urls:
                    urls.append(candidate)
        for n in range(2, max_pages + 1):
            qs = parse_qs(parsed.query)
            qs["page"] = [str(n)]
            synthetic = urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(qs, doseq=True), "")
            )
            if synthetic not in urls:
                urls.append(synthetic)
    except Exception:
        pass
    return urls[:max_pages]


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


async def resolve_erome_listing(
    url: str,
    limit: int = 500,
    *,
    max_listing_pages: int = 5,
    max_albums: int = 40,
) -> CrawlerResult:
    """Profile or search page → discover album links → resolve each album's media."""
    if not _is_erome_url(url):
        raise ValueError("Erome listing crawler expects an erome.com URL.")

    kind = _classify_erome_url(url)
    if kind not in ("profile", "search"):
        raise ValueError(
            "Erome listing crawler expects a user profile (https://www.erome.com/<user>) "
            "or search URL (https://www.erome.com/search?q=…)."
        )

    warnings: list[str] = []
    listing_pages = max(1, min(max_listing_pages, 20))
    album_cap = max(1, min(max_albums, 200))

    first_html, fetch_warnings = await _fetch_erome_album(url)
    warnings.extend(fetch_warnings)
    page_urls = _erome_listing_page_urls(url, first_html, listing_pages)

    album_urls: list[str] = []
    seen_albums: set[str] = set()
    title = _extract_title(first_html)

    for page_url in page_urls:
        if page_url == url:
            page_html = first_html
        else:
            await _rate_limit("erome.com", 1.2)
            page_html, more = await _fetch_erome_album(page_url)
            warnings.extend(more)
        for album in _extract_erome_album_urls(page_html, page_url):
            if album in seen_albums:
                continue
            seen_albums.add(album)
            album_urls.append(album)
            if len(album_urls) >= album_cap:
                break
        if len(album_urls) >= album_cap:
            break

    if not album_urls:
        warnings.append(
            f"No album links found on this Erome {kind} page. "
            "Open the page in a browser to confirm it lists galleries."
        )
        return CrawlerResult(
            adapter="erome",
            source_url=url,
            title=title,
            items=[],
            warnings=warnings,
        )

    warnings.append(
        f"Erome {kind}: resolving up to {len(album_urls)} album(s) from {len(page_urls)} listing page(s)."
    )

    items: list[CrawlerMediaItem] = []
    item_urls: set[str] = set()
    for i, album_url in enumerate(album_urls):
        if limit > 0 and len(items) >= limit:
            break
        await _rate_limit("erome.com", 1.0)
        try:
            album_result = await resolve_erome_album(
                album_url, limit=max(1, limit - len(items)) if limit > 0 else 0
            )
        except Exception as exc:
            warnings.append(f"Album {album_url} failed: {exc.__class__.__name__}: {exc}")
            continue
        warnings.extend(album_result.warnings)
        for it in album_result.items:
            if it.url in item_urls:
                continue
            item_urls.add(it.url)
            items.append(it)
        if (i + 1) % 10 == 0:
            logger.info("Erome listing %s: resolved %d/%d albums, %d items", kind, i + 1, len(album_urls), len(items))

    if not items:
        warnings.append("Album links were found but no direct media URLs could be extracted.")

    return CrawlerResult(
        adapter="erome",
        source_url=url,
        title=title,
        items=items,
        warnings=warnings,
    )


async def resolve_erome_album(url: str, limit: int = 250) -> CrawlerResult:
    if not _is_erome_url(url) or _classify_erome_url(url) != "album":
        raise ValueError("Erome album crawler expects an album URL like https://www.erome.com/a/<id>.")

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


# ---------------------------------------------------------------------------
# Bunkr adapter — mirrors the gallery-dl / JDownloader approach
# ---------------------------------------------------------------------------

_BUNKR_DOMAINS = {
    "bunkr.ac", "bunkr.ci", "bunkr.cr", "bunkr.fi", "bunkr.ph",
    "bunkr.pk", "bunkr.ps", "bunkr.si", "bunkr.sk", "bunkr.ws",
    "bunkr.black", "bunkr.red", "bunkr.media", "bunkr.site",
}
_BUNKR_LEGACY_DOMAINS = {
    "bunkr.ax", "bunkr.cat", "bunkr.ru", "bunkrr.ru", "bunkr.su",
    "bunkrr.su", "bunkr.la", "bunkr.is", "bunkr.to",
}
_BUNKR_DL_ROOT = "https://get.bunkrr.su"
_BUNKR_API_ROOT = "https://apidl.bunkr.ru"
_BUNKR_API_ENDPOINT = _BUNKR_API_ROOT + "/api/_001_v2"


def _is_bunkr_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if host.startswith("app."):
        host = host[4:]
    return host in _BUNKR_DOMAINS or host in _BUNKR_LEGACY_DOMAINS


def _decrypt_xor(data: str, key: bytes) -> str:
    """Bunkr API returns encrypted URLs as base64(XOR(plaintext, key)).

    The matching deobfuscator pattern used by gallery-dl is to base64-decode
    first, then XOR with a key derived from the API response timestamp.
    """
    import base64
    raw = base64.b64decode(data)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8", errors="replace")


def _walk_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Return index of matching close char for the bracket at *start*. -1 if unbalanced."""
    depth = 0
    in_string = False
    string_char = ""
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == string_char:
                in_string = False
        else:
            if c in ('"', "'"):
                in_string = True
                string_char = c
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _parse_bunkr_album_files(page: str) -> list[dict]:
    """Extract file entries from the embedded ``window.albumFiles`` JS array.

    Bunkr serves an "advanced" album page that embeds a JS array of file
    metadata objects. Each object contains the numeric file id, the original
    filename, a direct thumbnail URL, the MIME type, and a relative
    ``cdnEndpoint``. We use this metadata both for instant tile previews and
    as input to the per-file resolver API.
    """
    anchor = page.find("window.albumFiles")
    if anchor < 0:
        return []
    bracket_start = page.find("[", anchor)
    if bracket_start < 0:
        return []
    bracket_end = _walk_balanced(page, bracket_start, "[", "]")
    if bracket_end < 0:
        return []

    body = page[bracket_start + 1:bracket_end]

    items: list[dict] = []
    pos = 0
    while True:
        obj_start = body.find("{", pos)
        if obj_start < 0:
            break
        obj_end = _walk_balanced(body, obj_start, "{", "}")
        if obj_end < 0:
            break
        chunk = body[obj_start + 1:obj_end]
        pos = obj_end + 1

        def _str(key: str) -> str | None:
            m = re.search(
                rf'\b{re.escape(key)}\s*:\s*"((?:[^"\\]|\\.)*)"',
                chunk,
            )
            if not m:
                return None
            value = m.group(1).replace('\\"', '"').replace("\\'", "'").replace("\\/", "/")
            return value or None

        def _num(key: str) -> int | None:
            m = re.search(rf"\b{re.escape(key)}\s*:\s*(-?\d+)", chunk)
            return int(m.group(1)) if m else None

        file_id = _num("id")
        if file_id is None:
            continue

        items.append({
            "id": str(file_id),
            "original": _str("original") or "",
            "slug": _str("slug") or "",
            "name": _str("name") or "",
            "type": _str("type") or "",
            "extension": _str("extension") or "",
            "size": _num("size") or 0,
            "timestamp": _str("timestamp") or "",
            "thumbnail": _str("thumbnail") or "",
            "cdnEndpoint": _str("cdnEndpoint") or "",
        })

    return items


def _media_type_from_bunkr_entry(entry: dict) -> str:
    mime = (entry.get("type") or "").lower()
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/"):
        return "image"
    ext = (entry.get("extension") or "").lower()
    if ext == "video":
        return "video"
    return "image"


async def _bunkr_resolve_file(
    client: httpx.AsyncClient,
    file_id: str,
    cookies: str | None = None,
    max_retries: int = 3,
) -> tuple[str, dict[str, str]]:
    """Call the Bunkr API to get the real CDN download URL for a file.

    Retries on transient 5xx / network errors with exponential backoff.
    Cookies (if provided) are forwarded to the API host — Bunkr's anti-bot
    front sometimes admits authenticated callers more reliably than fresh
    sessions, which is why videos can fail without the cookies toggle.
    """
    referer = f"{_BUNKR_DL_ROOT}/file/{file_id}"
    headers = {
        "Referer": referer,
        "Origin": _BUNKR_DL_ROOT,
        "Content-Type": "application/json",
    }
    if cookies:
        headers["Cookie"] = cookies

    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            resp = await client.post(
                _BUNKR_API_ENDPOINT,
                headers=headers,
                json={"id": file_id},
            )
            if resp.status_code == 429:
                await asyncio.sleep(min(2 ** (attempt + 1), 15))
                continue
            resp.raise_for_status()
            data = resp.json()

            if data.get("encrypted"):
                key = "SECRET_KEY_" + str(int(data["timestamp"]) // 3600)
                file_url = _decrypt_xor(data["url"], key.encode())
            else:
                file_url = data["url"]

            return file_url, {"Referer": referer}
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt + 1 < max_retries:
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Bunkr API resolve failed without exception")


async def resolve_bunkr_album(
    url: str,
    cookies: str | None = None,
    limit: int = 500,
) -> CrawlerResult:
    if not _is_bunkr_url(url):
        raise ValueError("Bunkr adapter expects a URL on a bunkr domain.")

    warnings: list[str] = []

    parsed = urlparse(url)
    base_root = f"{parsed.scheme}://{parsed.hostname}"
    album_match = re.search(r"/a/([^/?#]+)", parsed.path)
    if not album_match:
        raise ValueError("Bunkr adapter expects an album URL like https://bunkr.si/a/<id>.")
    album_id = album_match.group(1)

    advanced_url = f"{base_root}/a/{album_id}?advanced=1"
    page, fetch_warnings = await _fetch_with_cookies_and_retry(
        advanced_url, cookies=cookies, referer=base_root + "/"
    )
    warnings.extend(fetch_warnings)

    title = _extract_title(page)
    album_files = _parse_bunkr_album_files(page)

    if not album_files:
        warnings.append(
            "Could not parse album file list. The page may require Cloudflare "
            "clearance cookies — enable 'Cookies' in the crawler bar while "
            "viewing the album in your browser."
        )
        return CrawlerResult(
            adapter="bunkr",
            source_url=url,
            title=title,
            items=[],
            warnings=warnings,
        )

    logger.info("Bunkr album %s: found %d files, resolving CDN URLs...", album_id, len(album_files))

    if limit > 0:
        album_files = album_files[:limit]

    failed = 0
    last_failure: str | None = None

    api_headers = _browser_headers(referer=_BUNKR_DL_ROOT)
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0, headers=api_headers
    ) as client:
        sem = asyncio.Semaphore(4)

        async def resolve_one(entry: dict) -> CrawlerMediaItem | None:
            nonlocal failed, last_failure
            async with sem:
                await _rate_limit("apidl.bunkr.ru", 0.35)
                try:
                    file_url, _ = await _bunkr_resolve_file(
                        client, entry["id"], cookies=cookies
                    )
                    filename = (
                        entry.get("original")
                        or entry.get("slug")
                        or entry.get("name")
                        or _filename_for_url(file_url)
                    )
                    media_type = _media_type_from_bunkr_entry(entry) or _media_type_for_url(file_url)
                    return CrawlerMediaItem(
                        url=file_url,
                        media_type=media_type,
                        filename=filename,
                        thumbnail_url=entry.get("thumbnail") or None,
                    )
                except Exception as exc:
                    failed += 1
                    last_failure = f"{exc.__class__.__name__}: {exc}"
                    logger.warning("Bunkr file %s resolve failed: %s", entry.get("id"), exc)
                    return None

        results = await asyncio.gather(*(resolve_one(f) for f in album_files))

    if failed > 0 and not cookies:
        warnings.append(
            f"{failed}/{len(album_files)} files failed to resolve "
            f"(last error: {last_failure}). Try enabling 'Cookies' in the "
            f"crawler bar — Bunkr sometimes blocks unauthenticated callers."
        )
    elif failed > 0:
        warnings.append(
            f"{failed}/{len(album_files)} files failed to resolve "
            f"(last error: {last_failure}). Some Bunkr CDN servers may be in "
            f"maintenance; retry in a minute."
        )

    items = [r for r in results if r is not None]

    if not items:
        warnings.append("No files could be resolved. The album may be deleted or all servers are in maintenance.")

    return CrawlerResult(
        adapter="bunkr",
        source_url=url,
        title=title,
        items=items,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# OnlyFans adapter
# ---------------------------------------------------------------------------

def _is_onlyfans_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "onlyfans.com" or host.endswith(".onlyfans.com")


async def _fetch_with_cookies_and_retry(
    url: str,
    cookies: str | None = None,
    referer: str | None = None,
    max_retries: int = 3,
    timeout: float = 45.0,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    headers = _browser_headers(referer=referer)
    if cookies:
        headers["Cookie"] = cookies

    domain = (urlparse(url).hostname or "unknown").lower()

    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        await _rate_limit(domain)
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=timeout, headers=headers
            ) as client:
                response = await client.get(url)
                if response.status_code == 429:
                    wait = min(2 ** (attempt + 1), 30)
                    warnings.append(f"Rate limited (429), waiting {wait}s before retry.")
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.text, warnings
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code in (403, 401):
                warnings.append(
                    f"HTTP {e.response.status_code} — site may require login cookies. "
                    "Enable 'Use cookies' in the crawler bar."
                )
                raise
            if attempt + 1 < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
        except Exception as e:
            last_exc = e
            if attempt + 1 < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Fetch failed after retries")


async def resolve_onlyfans(
    url: str, cookies: str | None = None, limit: int = 250
) -> CrawlerResult:
    if not _is_onlyfans_url(url):
        raise ValueError("OnlyFans adapter expects a URL on onlyfans.com.")

    if not cookies:
        raise ValueError(
            "OnlyFans requires login cookies. Enable 'Use cookies' in the crawler bar "
            "and make sure you're logged in to OnlyFans in this browser."
        )

    page, warnings = await _fetch_with_cookies_and_retry(
        url, cookies=cookies, referer="https://onlyfans.com/"
    )

    title = _extract_title(page)
    items = _extract_onlyfans_media(page, limit=limit)

    if not items:
        warnings.append(
            "No media found. The page might require a paid subscription, "
            "or the content is behind a paywall not accessible with current cookies."
        )

    return CrawlerResult(
        adapter="onlyfans",
        source_url=url,
        title=title,
        items=items,
        warnings=warnings,
    )


def _extract_onlyfans_media(page: str, limit: int = 250) -> list[CrawlerMediaItem]:
    items: list[CrawlerMediaItem] = []
    seen: set[str] = set()

    of_cdn_re = re.compile(
        r"https?://[^\"'\s<>]+?\.(?:onlyfans\.com|oflk\.com|ofcdn\.com)"
        rf"[^\"'\s<>]*?\.({_MEDIA_EXT_RE})(?:\?[^\"'\s<>]*)?",
        flags=re.I,
    )
    for m in of_cdn_re.finditer(page):
        raw_url = _clean_url(m.group(0))
        if raw_url in seen:
            continue
        seen.add(raw_url)
        items.append(CrawlerMediaItem(
            url=raw_url,
            media_type=_media_type_for_url(raw_url),
            filename=_filename_for_url(raw_url),
        ))
        if len(items) >= limit:
            break

    generic = _extract_generic_media_urls(page)
    for raw_url in generic:
        if raw_url in seen:
            continue
        try:
            host = (urlparse(raw_url).hostname or "").lower()
        except Exception:
            continue
        if "onlyfans" not in host and "oflk" not in host and "ofcdn" not in host:
            continue
        seen.add(raw_url)
        items.append(CrawlerMediaItem(
            url=raw_url,
            media_type=_media_type_for_url(raw_url),
            filename=_filename_for_url(raw_url),
        ))
        if len(items) >= limit:
            break

    return items


def _extract_generic_media_urls(page: str) -> list[str]:
    candidates: list[tuple[int, str]] = []

    attr_re = re.compile(
        rf'\b(?:src|href|data-src|data-url|data-video|data-video-src|poster|content)=["\']([^"\']+\.({_MEDIA_EXT_RE})(?:\?[^"\']*)?)["\']',
        flags=re.I,
    )
    for m in attr_re.finditer(page):
        candidates.append((m.start(1), m.group(1)))

    direct_re = re.compile(
        rf"https?://[^\"'<>\\\s]+?\.({_MEDIA_EXT_RE})(?:\?[^\"'<>\\\s]*)?",
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
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


async def resolve_generic(
    url: str, cookies: str | None = None, limit: int = 250
) -> CrawlerResult:
    referer = url
    try:
        p = urlparse(url)
        referer = f"{p.scheme}://{p.hostname}/"
    except Exception:
        pass

    page, warnings = await _fetch_with_cookies_and_retry(
        url, cookies=cookies, referer=referer
    )

    title = _extract_title(page)
    raw_urls = _extract_generic_media_urls(page)

    if limit > 0:
        raw_urls = raw_urls[:limit]

    items = [
        CrawlerMediaItem(
            url=u,
            media_type=_media_type_for_url(u),
            filename=_filename_for_url(u),
        )
        for u in raw_urls
    ]

    if not items:
        warnings.append("No media URLs found in the page HTML.")

    return CrawlerResult(
        adapter="generic",
        source_url=url,
        title=title,
        items=items,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# made.porn adapter — gallery pages embed /vs/*.mp4 and /is/*.jpg in HTML
# ---------------------------------------------------------------------------

_MADEPORN_MP4_RE = re.compile(
    r"https?://made\.porn/vs/[^\"'<>\s\\]+\.mp4",
    flags=re.I,
)
_MADEPORN_IMG_RE = re.compile(
    r"https?://made\.porn/is/[^\"'<>\s\\]+\.(?:jpe?g|webp)",
    flags=re.I,
)


def _is_madeporn_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "made.porn" or host.endswith(".made.porn")


def _madeporn_variant_rank(url: str) -> int:
    u = url.lower()
    if "_avc." in u:
        return 3
    if "_av1." in u:
        return 2
    return 1


def _madeporn_mp4_group_key(url: str) -> str:
    return re.sub(r"_(?:av1|avc)\.mp4$", ".mp4", url, flags=re.I).split("?")[0].lower()


def _dedupe_madeporn_mp4_urls(urls: list[str]) -> list[str]:
    best: dict[str, str] = {}
    for u in urls:
        key = _madeporn_mp4_group_key(u)
        prev = best.get(key)
        if not prev or _madeporn_variant_rank(u) > _madeporn_variant_rank(prev):
            best[key] = u
    return list(best.values())


def _extract_madeporn_media_urls(page: str) -> tuple[list[str], list[str]]:
    mp4s = _dedupe_madeporn_mp4_urls(list(dict.fromkeys(_MADEPORN_MP4_RE.findall(page))))
    images = list(dict.fromkeys(_MADEPORN_IMG_RE.findall(page)))
    return mp4s, images


async def resolve_madeporn(
    url: str, cookies: str | None = None, limit: int = 500
) -> CrawlerResult:
    if not _is_madeporn_url(url):
        raise ValueError("made.porn crawler expects a made.porn URL.")

    page, warnings = await _fetch_with_cookies_and_retry(
        url, cookies=cookies, referer=url
    )
    title = _extract_title(page)
    mp4s, images = _extract_madeporn_media_urls(page)

    items: list[CrawlerMediaItem] = []
    for u in mp4s:
        items.append(
            CrawlerMediaItem(
                url=u,
                media_type="video",
                filename=_filename_for_url(u),
            )
        )
    for u in images:
        items.append(
            CrawlerMediaItem(
                url=u,
                media_type="image",
                filename=_filename_for_url(u),
            )
        )

    if limit > 0:
        items = items[:limit]

    if not items:
        warnings.append("No made.porn media URLs found in page HTML.")

    return CrawlerResult(
        adapter="madeporn",
        source_url=url,
        title=title,
        items=items,
        warnings=warnings,
    )


def _detect_adapter(url: str) -> CrawlerAdapter:
    if _is_erome_url(url) and _classify_erome_url(url) in ("album", "profile", "search"):
        return "erome"
    if _is_bunkr_url(url):
        return "bunkr"
    if _is_onlyfans_url(url):
        return "onlyfans"
    if _is_madeporn_url(url):
        return "madeporn"
    return "generic"


async def resolve_crawler_url(
    url: str,
    adapter: CrawlerAdapter = "auto",
    limit: int = 500,
    cookies: str | None = None,
) -> dict:
    clean = str(url or "").strip()
    if not clean.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://.")

    selected = adapter if adapter != "auto" else _detect_adapter(clean)

    if selected == "erome":
        if _classify_erome_url(clean) == "album":
            return asdict(await resolve_erome_album(clean, limit=limit))
        return asdict(await resolve_erome_listing(clean, limit=limit))
    if selected == "bunkr":
        return asdict(await resolve_bunkr_album(clean, cookies=cookies, limit=limit))
    if selected == "onlyfans":
        return asdict(await resolve_onlyfans(clean, cookies=cookies, limit=limit))
    if selected == "madeporn":
        return asdict(await resolve_madeporn(clean, cookies=cookies, limit=limit))
    return asdict(await resolve_generic(clean, cookies=cookies, limit=limit))
