"""
Enrich human-readable tags for extension Saved Messages sends (no Media row required).

Uses the same sidecars as import-time enrich: Lustpress page metadata, NSFW classifier
on a small sample of media URLs, plus host/creator heuristics (OnlyFans, Erome, etc.).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.services.lustpress_metadata import fetch_metadata_for_url, lustpress_enabled, metadata_to_tag_slugs
from app.services.nsfw_classifier import classify_image_url, nsfw_classifier_enabled

logger = logging.getLogger(__name__)

_HEXISH = re.compile(r"^[0-9a-f]+$", re.I)
_SHORT_OK = frozenset(
    {
        "mp4",
        "webm",
        "mov",
        "nsfw",
        "sfw",
        "hd",
        "4k",
        "pic",
        "vid",
        "of",
        "user",
        "data",
    }
)

_HOST_RULES: list[tuple[str, str]] = [
    ("erome.com", "erome"),
    ("onlyfans.com", "onlyfans"),
    ("coomer.", "coomer"),
    ("kemono.", "kemono"),
    ("motherless.", "motherless"),
    ("redgifs.", "redgifs"),
    ("reddit.com", "reddit"),
    ("x.com", "x-twitter"),
    ("twitter.com", "x-twitter"),
    ("pornhub.com", "pornhub"),
    ("xvideos.com", "xvideos"),
    ("xhamster.com", "xhamster"),
]


_TECH_STOP = frozenset(
    {
        "thumb",
        "thumbs",
        "thumbnail",
        "profilepage",
        "profile page",
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "large",
        "small",
        "original",
        "files",
        "cdn",
        "static",
        "content",
    }
)


def _looks_like_random_cdn_slug(s: str) -> bool:
    t = re.sub(r"[\s_\-]+", "", (s or "").strip())
    if len(t) < 5 or len(t) > 14:
        return False
    if not re.fullmatch(r"[A-Za-z0-9]+", t):
        return False
    low = t.lower()
    if low in _SHORT_OK:
        return False
    digits = len(re.findall(r"\d", t))
    has_upper = bool(re.search(r"[A-Z]", t))
    has_lower = bool(re.search(r"[a-z]", t))
    letters_only = re.sub(r"\d", "", t)
    if re.fullmatch(r"[a-z][a-z0-9_.]{2,31}", t) and re.search(r"[aeiou]", t, re.I) and digits <= 2:
        return False
    if 6 <= len(t) <= 12 and digits >= 1 and has_upper and has_lower:
        return True
    if 7 <= len(t) <= 11 and has_upper and has_lower and not re.search(r"[aeiou]", letters_only, re.I):
        return True
    if 6 <= len(t) <= 12 and digits >= 2 and has_upper and has_lower:
        return True
    return False


def is_junk_label(raw: str) -> bool:
    """CDN hashes, path crumbs, and technical file tokens — not crypto addresses."""
    s = (raw or "").strip().lstrip("#")
    if not s or len(s) < 2:
        return True
    low = s.lower()
    if low in _SHORT_OK:
        return False
    if low in _TECH_STOP:
        return True
    if _looks_like_random_cdn_slug(s):
        return True
    compact = re.sub(r"[\s_\-]+", "", s)
    if compact.startswith("0x") and _HEXISH.match(compact[2:]):
        return True
    if len(compact) <= 2 and _HEXISH.match(compact):
        return True
    if len(compact) >= 8 and _HEXISH.match(compact):
        return True
    alnum = re.sub(r"[^a-z0-9]", "", s, flags=re.I)
    if len(alnum) >= 12:
        hex_n = len(_HEXISH.findall(alnum))
        if hex_n / max(len(alnum), 1) >= 0.82:
            return True
        if not re.search(r"[aeiou]", alnum, re.I):
            return True
    if len(alnum) >= 10 and re.fullmatch(r"[0-9]+", alnum):
        return True
    if re.fullmatch(r"[A-Z][a-z]+[A-Z][a-z]+", s) and low.endswith("page"):
        return True
    return False


def _add_label(out: list[str], seen: set[str], label: str) -> None:
    s = (label or "").strip()
    if not s or is_junk_label(s):
        return
    key = s.lower()
    if key in seen:
        return
    seen.add(key)
    out.append(s[:128])


def _rule_label_for_host(host: str) -> str | None:
    h = (host or "").lower()
    for needle, label in _HOST_RULES:
        if needle in h:
            return label
    return None


def _is_trace_source_label(label: str) -> bool:
    """Scrape-site / platform tokens — admin metadata only, not Telegram #hashtags."""
    s = (label or "").strip().lower().lstrip("#")
    if not s:
        return False
    if s.startswith("src-"):
        return True
    for needle, site in _HOST_RULES:
        if s == site or needle.rstrip(".") in s:
            return True
    cam_markers = (
        "bestcam",
        "cumcams",
        "chaturbate",
        "stripchat",
        "bongacams",
        "cam4",
        "livejasmin",
        "myfreecams",
        "camsoda",
        "camwhores",
        "recurbate",
    )
    return any(m in s for m in cam_markers)


_CAM_PERFORMER_TITLE_RE = re.compile(
    r"(?:newest|latest|best|free|private|premium|hot|top)?\s*"
    r"([A-Za-z][A-Za-z0-9_.-]{3,28})\s+cam\b",
    re.I,
)


def _performer_hints_from_title(title: str) -> list[str]:
    """Model/creator tokens from cam-site page titles (e.g. 'Newest Michellesexxy Cam videos')."""
    t = (title or "").strip()
    if not t:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _CAM_PERFORMER_TITLE_RE.finditer(t):
        name = (m.group(1) or "").strip()
        if not name or is_junk_label(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _page_context_tags(page_url: str) -> list[str]:
    """Creator / site tokens from gallery page URL (OnlyFans, etc.)."""
    tags: list[str] = []
    try:
        u = urlparse(page_url.strip().split("#")[0])
        host = (u.hostname or "").lower()
        path = (u.path or "").strip("/")
        rl = _rule_label_for_host(host)
        if rl:
            tags.append(rl)
        if "onlyfans.com" in host and path:
            for pat in (
                r"^u/([A-Za-z0-9_.-]+)",
                r"^c/([0-9]+)/([A-Za-z0-9_.-]+)",
                r"^([A-Za-z0-9_.-]+)/posts",
                r"^([A-Za-z0-9_.-]+)$",
            ):
                m = re.match(pat, path, re.I)
                if m:
                    creator = m.group(m.lastindex or 1)
                    if creator and not creator.isdigit() and len(creator) >= 3 and not is_junk_label(creator):
                        tags.append(creator)
                        if "/posts" not in path.lower():
                            tags.append("profile")
                        break
        if "erome.com" in host:
            tags.append("erome")
    except Exception:
        pass
    return tags


def _skip_lustpress_for_page(page_url: str) -> bool:
    """Sites Lustpress does not enrich — avoid long client timeouts on Saved send."""
    try:
        host = (urlparse(page_url).hostname or "").lower()
    except Exception:
        return False
    return any(
        x in host
        for x in (
            "onlyfans.com",
            "fansly.com",
            "patreon.com",
        )
    )


def _lustpress_labels(page_url: str, *, timeout: float = 25.0) -> tuple[list[str], str | None]:
    if not lustpress_enabled() or _skip_lustpress_for_page(page_url):
        return [], None
    meta = fetch_metadata_for_url(page_url, timeout=timeout)
    if not meta:
        return [], None
    labels: list[str] = []
    if meta.title and not is_junk_label(meta.title):
        labels.append(meta.title[:128])
    for row in metadata_to_tag_slugs(meta):
        _slug, name, cat = row
        if cat == "source" or _is_trace_source_label(name or ""):
            continue
        if name and not is_junk_label(name):
            labels.append(name)
    for perf in meta.performer_names or []:
        if perf and not is_junk_label(str(perf)):
            labels.append(str(perf).strip()[:128])
    title = (meta.title or "").strip() or None
    return labels, title


def _nsfw_tier_labels(
    media_urls: list[str],
    max_samples: int = 3,
    *,
    timeout: float = 45.0,
) -> tuple[list[str], str | None]:
    if not nsfw_classifier_enabled():
        return [], None
    tier_seen: set[str] = set()
    labels: list[str] = []
    sampled = 0
    for raw in media_urls:
        if sampled >= max_samples:
            break
        url = (raw or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        low = url.lower().split("?", 1)[0]
        if not any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            continue
        try:
            res = classify_image_url(url, timeout=timeout)
        except Exception as e:
            logger.debug("nsfw sample failed: %s", e)
            continue
        sampled += 1
        if not res or res.nsfw_tier in tier_seen:
            continue
        tier_seen.add(res.nsfw_tier)
        tier = res.nsfw_tier
        if tier in ("explicit", "suggestive", "sfw"):
            labels.append(tier)
        elif tier == "unknown":
            labels.append("nsfw-unknown")
    top_tier = next(iter(tier_seen), None)
    return labels, top_tier


def enrich_send_batch(
    items: list[dict[str, Any]],
    *,
    manual_tags: list[str] | None = None,
    max_lustpress_pages: int = 4,
    max_nsfw_samples: int = 3,
    fast: bool = False,
) -> dict[str, Any]:
    """
    items: [{ source_page_url, media_url, page_host? }, ...]
    Returns labels for #hashtag line + optional caption_line prefix.

    fast=True: tight budgets for extension Saved send (page heuristics + optional 1 LP/NSFW).
    """
    if fast:
        max_lustpress_pages = min(max_lustpress_pages, 1)
        max_nsfw_samples = min(max_nsfw_samples, 1)
    lp_timeout = 6.0 if fast else 25.0
    nsfw_timeout = 10.0 if fast else 45.0

    labels: list[str] = []
    seen: set[str] = set()
    sources: list[str] = []
    caption_parts: list[str] = []

    for t in manual_tags or []:
        _add_label(labels, seen, str(t))

    page_urls: list[str] = []
    media_urls: list[str] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        sp = (it.get("source_page_url") or it.get("page_url") or "").strip()
        if sp.startswith(("http://", "https://")) and sp not in page_urls:
            page_urls.append(sp)
        mu = (it.get("media_url") or it.get("url") or "").strip()
        if mu.startswith(("http://", "https://")):
            media_urls.append(mu)
        # page_host is stored in TBCC admin capture meta — not a public Telegram hashtag.

    for page in page_urls[: max(1, max_lustpress_pages)]:
        for lbl in _page_context_tags(page):
            if _is_trace_source_label(lbl):
                continue
            _add_label(labels, seen, lbl)
            if "page-heuristic" not in sources:
                sources.append("page-heuristic")

    lustpress_pages = 0
    for page in page_urls:
        if lustpress_pages >= max_lustpress_pages:
            break
        lp_labels, title = _lustpress_labels(page, timeout=lp_timeout)
        if lp_labels or title:
            lustpress_pages += 1
            if "lustpress" not in sources:
                sources.append("lustpress")
        for lbl in lp_labels:
            if _is_trace_source_label(lbl):
                continue
            _add_label(labels, seen, lbl)
        if title:
            for perf in _performer_hints_from_title(title):
                _add_label(labels, seen, perf)
            if title not in caption_parts:
                caption_parts.append(title)

    nsfw_labels, top_tier = _nsfw_tier_labels(
        media_urls, max_samples=max_nsfw_samples, timeout=nsfw_timeout
    )
    if nsfw_labels and "nsfw" not in sources:
        sources.append("nsfw")
    for lbl in nsfw_labels:
        _add_label(labels, seen, lbl)

    caption_line = ""
    if caption_parts:
        caption_line = caption_parts[0]
        if len(caption_parts) > 1:
            caption_line = caption_parts[0] + " · " + caption_parts[1][:80]

    return {
        "ok": True,
        "labels": labels[:40],
        "caption_line": caption_line[:512] if caption_line else "",
        "sources": sources,
        "lustpress_pages": lustpress_pages,
        "nsfw_tier": top_tier,
        "lustpress_enabled": lustpress_enabled(),
        "nsfw_enabled": nsfw_classifier_enabled(),
    }
