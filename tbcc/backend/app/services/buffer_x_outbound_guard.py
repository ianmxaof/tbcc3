"""Enforce gated outbound URLs on Buffer/X mirrors — no bare t.me leaks."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from app.services.buffer_x_link_order import classify_url
from app.services.link_gate_provider import is_gate_host, wrap_gate_url

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"'\)]+", re.I)
_TELEGRAM_HOST_RE = re.compile(r"(?:^|//)(?:www\.)?(?:t\.me|telegram\.me)(?:/|$)", re.I)

# Network keys that must pass strict wrap validation before Buffer mirror send.
_DEFAULT_STRICT_KEYS = frozenset({"bop", "taboo"})


def buffer_x_require_gate_wrap() -> bool:
    return (os.getenv("TBCC_BUFFER_X_REQUIRE_GATE_WRAP") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def strict_mirror_network_keys() -> frozenset[str]:
    raw = (os.getenv("TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS") or "bop,taboo").strip()
    if not raw:
        return _DEFAULT_STRICT_KEYS
    return frozenset(k.strip().lower() for k in raw.split(",") if k.strip())


def is_bare_telegram_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or is_gate_host(u):
        return False
    return bool(_TELEGRAM_HOST_RE.search(u))


def _gate_key_for_url(url: str) -> str:
    cat = classify_url(url)
    if cat == "telegram":
        return "mainhub"
    if cat == "erome":
        return "mainhub"
    return "mainhub"


def wrap_url_for_x_outbound(url: str, *, gate_key: str | None = None) -> str:
    """Return gated URL when bare Telegram (or when wrap required); pass-through if already gated."""
    from app.services.aof_social_links import x_linkvertise_enabled

    u = (url or "").strip().rstrip(".,;)")
    if not u or is_gate_host(u):
        return u
    # Bare t.me + affiliate-first previews: keep direct Telegram/hub URLs on X unless LV explicitly enabled.
    if is_bare_telegram_url(u) and not x_linkvertise_enabled():
        return u
    if not is_bare_telegram_url(u) and not buffer_x_require_gate_wrap():
        return u

    from app.data.aof_manual_gate_links import manual_gate_url

    key = gate_key or _gate_key_for_url(u)
    manual = (manual_gate_url(key) or manual_gate_url("mainhub") or "").strip()
    if manual:
        return manual

    if is_bare_telegram_url(u):
        try:
            decision = wrap_gate_url(u)
            if decision.wrapped:
                return decision.wrapped
        except Exception as e:
            logger.warning("wrap_gate_url failed for X outbound %s: %s", u[:80], e)
    return u


def _extract_urls(text: str) -> list[str]:
    return [m.group(0).rstrip(".,;)") for m in _URL_RE.finditer(text or "")]


def enforce_buffer_x_caption_urls(
    text: str,
    *,
    network_key: str | None = None,
    strict: bool = False,
) -> tuple[str, list[str]]:
    """
    Replace bare Telegram URLs with gated equivalents.
    Returns (new_text, errors). errors non-empty => caller should block send when strict.
    """
    body = text or ""
    errors: list[str] = []
    out = body
    for url in _extract_urls(body):
        if is_gate_host(url):
            continue
        cat = classify_url(url)
        if cat in ("affiliate", "gumroad_vip", "promo_viewer"):
            continue
        if is_bare_telegram_url(url) or (buffer_x_require_gate_wrap() and cat == "telegram"):
            wrapped = wrap_url_for_x_outbound(url, gate_key=network_key or "mainhub")
            if wrapped != url and is_gate_host(wrapped):
                out = out.replace(url, wrapped)
            elif is_bare_telegram_url(url):
                msg = f"bare Telegram URL blocked for X: {url[:60]}"
                errors.append(msg)
                logger.warning(msg)
    if strict and errors:
        return out, errors
    return out, []


def network_key_for_telegram_identifier(identifier: str | None, db: Session | None) -> str | None:
    if not identifier or db is None:
        return None
    from app.models.channel import Channel
    from app.data.aof_network import AOF_NETWORK_CHANNELS, MAINHUB_CHANNEL_IDENT

    ident = str(identifier).strip()
    if ident == MAINHUB_CHANNEL_IDENT:
        return "mainhub"
    ch = db.query(Channel).filter(Channel.identifier == ident).first()
    if not ch:
        return None
    for net in AOF_NETWORK_CHANNELS:
        if net.identifier == ident:
            return net.key
    return None
