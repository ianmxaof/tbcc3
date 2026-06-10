"""Reject garbage username handles in master archive (code-page noise vs cam/fan handles)."""
from __future__ import annotations

import re

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")

_RESERVED = frozenset(
    {
        "a", "an", "the", "and", "or", "to", "of", "in", "on", "at", "by", "for", "from", "with",
        "application", "install", "enhanced", "hyperrealistic", "below", "endpoint", "obfuscation",
        "powershell", "prepend", "replace", "script", "undress", "name", "make", "image", "https",
        "http", "here", "nvidia", "gravatar", "gorillamail", "linkvertise", "sharklasers", "proton",
        "bot", "message", "handler", "function", "return", "const", "class", "import", "export",
        "undefined", "null", "true", "false", "var", "let", "async", "await", "static", "public",
        "private", "void", "int", "string", "object", "array", "type", "interface", "username",
        "user", "users", "profile", "profiles", "search", "models", "model", "video", "videos",
        "photo", "photos", "media", "login", "signup", "register", "settings", "admin", "www", "en",
        "hii", "rthi", "seaside", "cloud", "data", "index", "home", "about", "html", "body", "head",
    }
)


def normalize_archive_username(raw: str) -> str | None:
    if not raw:
        return None
    v = str(raw).strip().lstrip("@")
    if not v or not _USERNAME_RE.match(v):
        return None
    low = v.lower()
    if low in _RESERVED:
        return None
    if v.isdigit():
        return None
    if not any(c.isalpha() for c in v):
        return None
    if len(v) <= 2 and not re.search(r"[a-zA-Z]{2,}", v):
        return None
    if re.match(r"^(user|u|id|uid|name|test|demo|null|none|admin|root|guest)\d*$", low):
        return None
    return v
