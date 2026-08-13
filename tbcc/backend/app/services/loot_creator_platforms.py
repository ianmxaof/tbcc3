"""Creator profile URL normalization for Loot God /model submissions."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.services.buffer_x_link_order import first_url

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")
_TELEGRAM_HANDLE_RE = re.compile(r"^[a-zA-Z0-9_]{4,32}$")

# Gate / shortener / redirect hosts — never accept as creator landing pages.
_BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
    "is.gd",
    "cutt.ly",
    "rebrand.ly",
    "shorturl.at",
    "linkvertise.com",
    "linkvertise.net",
    "link-center.net",
    "link-to.net",
    "direct-link.net",
    "link-hub.net",
    "link-target.net",
    "up-to-down.net",
    "work.ink",
    "boost.ink",
    "loot-link.com",
    "lootlinks.com",
    "sub2unlock.com",
    "sub2get.com",
    "admaven.com",
    "paster.so",
    "localhost",
)

_BLOCKED_SCHEMES = frozenset({"javascript", "data", "file", "vbscript"})


@dataclass(frozen=True)
class CreatorPlatform:
    key: str
    label_prefix: str
    host_suffixes: tuple[str, ...]
    # first_segment | snap_add | privacy_profile | telegram_username | kik_username
    path_mode: str = "first_segment"
    canonical_host: str | None = None


_CREATOR_PLATFORMS: tuple[CreatorPlatform, ...] = (
    CreatorPlatform("onlyfans", "OF", ("onlyfans.com", "www.onlyfans.com"), canonical_host="onlyfans.com"),
    CreatorPlatform("fansly", "Fansly", ("fansly.com", "www.fansly.com"), canonical_host="fansly.com"),
    CreatorPlatform("manyvids", "MV", ("manyvids.com", "www.manyvids.com"), canonical_host="manyvids.com"),
    CreatorPlatform("fanvue", "Fanvue", ("fanvue.com", "www.fanvue.com"), canonical_host="fanvue.com"),
    CreatorPlatform("loyalfans", "LoyalFans", ("loyalfans.com", "www.loyalfans.com"), canonical_host="loyalfans.com"),
    CreatorPlatform("fancentro", "FanCentro", ("fancentro.com", "www.fancentro.com"), canonical_host="fancentro.com"),
    CreatorPlatform("admireme", "AdmireMe", ("admireme.vip", "www.admireme.vip"), canonical_host="admireme.vip"),
    CreatorPlatform("linktree", "Link", ("linktr.ee", "www.linktr.ee"), canonical_host="linktr.ee"),
    CreatorPlatform("linktree_alt", "Link", ("linktree.com", "www.linktree.com"), canonical_host="linktree.com"),
    CreatorPlatform("allmylinks", "Links", ("allmylinks.com", "www.allmylinks.com"), canonical_host="allmylinks.com"),
    CreatorPlatform("beacons", "Beacons", ("beacons.ai", "www.beacons.ai"), canonical_host="beacons.ai"),
    CreatorPlatform("hoo", "Hoo", ("hoo.be", "www.hoo.be"), canonical_host="hoo.be"),
    CreatorPlatform("boosty", "Boosty", ("boosty.to", "www.boosty.to"), canonical_host="boosty.to"),
    CreatorPlatform(
        "privacy",
        "Privacy",
        ("privacy.com.br", "www.privacy.com.br"),
        path_mode="privacy_profile",
        canonical_host="privacy.com.br",
    ),
    CreatorPlatform(
        "sextingpanther",
        "SextPanther",
        ("sextingpanther.com", "www.sextingpanther.com", "sextpanther.com", "www.sextpanther.com"),
        canonical_host="sextingpanther.com",
    ),
    CreatorPlatform(
        "sextingfinder",
        "SextFinder",
        ("sextingfinder.com", "www.sextingfinder.com"),
        canonical_host="sextingfinder.com",
    ),
    CreatorPlatform(
        "telegram",
        "Telegram",
        ("t.me", "telegram.me", "www.telegram.me"),
        path_mode="telegram_username",
        canonical_host="t.me",
    ),
    CreatorPlatform(
        "snapchat",
        "Snap",
        ("snapchat.com", "www.snapchat.com"),
        path_mode="snap_add",
        canonical_host="snapchat.com",
    ),
    CreatorPlatform("kik", "Kik", ("kik.me", "www.kik.me"), canonical_host="kik.me"),
    CreatorPlatform("kik_alt", "Kik", ("kik.com", "www.kik.com"), path_mode="kik_username", canonical_host="kik.com"),
    CreatorPlatform("patreon", "Patreon", ("patreon.com", "www.patreon.com"), canonical_host="patreon.com"),
    CreatorPlatform("chaturbate", "CB", ("chaturbate.com", "www.chaturbate.com"), canonical_host="chaturbate.com"),
    CreatorPlatform("stripchat", "Stripchat", ("stripchat.com", "www.stripchat.com"), canonical_host="stripchat.com"),
    CreatorPlatform("justfor", "JFF", ("justfor.fans", "www.justfor.fans"), canonical_host="justfor.fans"),
)

_HOST_TO_PLATFORM: dict[str, CreatorPlatform] = {}
for _plat in _CREATOR_PLATFORMS:
    for _host in _plat.host_suffixes:
        _HOST_TO_PLATFORM[_host] = _plat

SUPPORTED_PLATFORM_LABELS = (
    "OnlyFans · Fansly · ManyVids · Fanvue · LoyalFans · FanCentro · AdmireMe · "
    "Linktree · allmylinks · Beacons · Boosty · Privacy · SextPanther · SextingFinder · "
    "Telegram · Snapchat · Kik · Patreon · Chaturbate · Stripchat · JustForFans"
)


def _host_blocked(host: str) -> bool:
    h = (host or "").lower().strip(".")
    if not h:
        return True
    if h in _BLOCKED_SCHEMES:
        return True
    try:
        ipaddress.ip_address(h.strip("[]"))
        return True
    except ValueError:
        pass
    for suffix in _BLOCKED_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def _match_platform(host: str) -> CreatorPlatform | None:
    h = (host or "").lower().strip(".")
    if _host_blocked(h):
        return None
    if h in _HOST_TO_PLATFORM:
        return _HOST_TO_PLATFORM[h]
    for plat in _CREATOR_PLATFORMS:
        for suffix in plat.host_suffixes:
            if h == suffix or h.endswith("." + suffix):
                return plat
    return None


def _path_segments(path: str) -> list[str]:
    return [s for s in (path or "").strip("/").split("/") if s]


def _extract_handle(plat: CreatorPlatform, path: str) -> str | None:
    segs = _path_segments(path)
    if not segs:
        return None
    mode = plat.path_mode
    if mode == "first_segment":
        handle = segs[0]
        return handle if _HANDLE_RE.match(handle) else None
    if mode == "privacy_profile":
        if segs[0].lower() == "profile" and len(segs) > 1:
            handle = segs[1]
            return handle if _HANDLE_RE.match(handle) else None
        handle = segs[0]
        return handle if _HANDLE_RE.match(handle) else None
    if mode == "telegram_username":
        handle = segs[0]
        if handle.lower() in {"joinchat", "c", "addstickers", "share", "proxy", "socks", "iv"}:
            return None
        return handle if _TELEGRAM_HANDLE_RE.match(handle) else None
    if mode == "snap_add":
        if segs[0].lower() == "add" and len(segs) > 1:
            handle = segs[1]
            return handle if _HANDLE_RE.match(handle) else None
        return None
    if mode == "kik_username":
        if segs[0].lower() in {"u", "user"} and len(segs) > 1:
            handle = segs[1]
            return handle if _HANDLE_RE.match(handle) else None
        handle = segs[0]
        return handle if _HANDLE_RE.match(handle) else None
    return None


def _blocked_path(path: str) -> bool:
    low = (path or "").lower()
    for needle in ("/login", "/checkout", "/signin", "/signup", "/auth", "/admin", "/api/"):
        if needle in low:
            return True
    return False


def extract_submission_url(raw: str) -> str | None:
    """Pull the first http(s) URL from free text, or treat a bare domain/path as URL."""
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text.split()[0].rstrip(").,;]")
    found = first_url(text)
    if found:
        return found.rstrip(").,;]")
    # Bare profile URLs: onlyfans.com/handle, fanvue.com/user, t.me/channel
    bare = text.split()[0].rstrip(").,;]")
    if "." in bare and "/" in bare and " " not in bare:
        return bare
    return None


def normalize_creator_url(raw: str) -> tuple[str, str, str, str] | None:
    """
    Return (normalized_url, platform_key, platform_prefix, handle) or None if invalid.
    """
    candidate = extract_submission_url(raw)
    if not candidate:
        return None
    s = candidate.strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s.lstrip("/")
    try:
        p = urlparse(s)
    except Exception:
        return None
    if (p.scheme or "").lower() in _BLOCKED_SCHEMES:
        return None
    host = (p.hostname or "").lower()
    plat = _match_platform(host)
    if not plat:
        return None
    if _blocked_path(p.path or ""):
        return None
    handle = _extract_handle(plat, p.path or "")
    if not handle:
        return None
    canon = plat.canonical_host or host
    if plat.path_mode == "privacy_profile":
        normalized = f"https://{canon}/profile/{handle}"
    elif plat.path_mode == "snap_add":
        normalized = f"https://{canon}/add/{handle}"
    elif plat.path_mode == "telegram_username":
        normalized = f"https://{canon}/{handle}"
    elif plat.path_mode == "kik_username" and _path_segments(p.path or "")[0].lower() in {"u", "user"}:
        normalized = f"https://{canon}/u/{handle}"
    else:
        normalized = f"https://{canon}/{handle}"
    return normalized, plat.key, plat.label_prefix, handle


def label_from_creator_url(prefix: str, handle: str, handle_hint: str | None = None) -> str:
    h = (handle_hint or handle or "").strip()
    if h and len(h) <= 48:
        return f"{prefix} · {h[:48]}"
    return "Creator promo"


def unsupported_url_message(*, html: bool = True) -> str:
    body = (
        "Send a public profile link from a supported platform.\n\n"
        f"Supported: {SUPPORTED_PLATFORM_LABELS}\n\n"
        "Example: https://onlyfans.com/yourhandle\n"
        "Paste the link alone, or one URL per message."
    )
    if not html:
        return body
    return (
        "Send a public profile link from a supported platform.\n\n"
        f"<b>Supported:</b> {SUPPORTED_PLATFORM_LABELS}\n\n"
        "<i>Example:</i> <code>https://onlyfans.com/yourhandle</code>\n"
        "Paste the link alone, or one URL per message."
    )
