"""Fit Buffer mirror text for X / Twitter (280 chars) with optional overflow link."""

from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost

DEFAULT_X_MAX = 280


def buffer_x_max_chars() -> int:
    raw = (os.environ.get("TBCC_BUFFER_X_MAX_CHARS") or "").strip()
    try:
        n = int(raw)
        return max(50, min(500, n))
    except ValueError:
        return DEFAULT_X_MAX


def buffer_x_overflow_suffix(url: str) -> str:
    """Trailing CTA when caption is truncated (counts toward max_chars)."""
    u = (url or "").strip()
    label = (os.environ.get("TBCC_BUFFER_X_OVERFLOW_LABEL") or "AOF").strip() or "AOF"
    tmpl = (os.environ.get("TBCC_BUFFER_X_OVERFLOW_SUFFIX") or "").strip()
    if tmpl and "{url}" in tmpl:
        return tmpl.format(url=u, label=label)
    return f" read the rest at {label}: {u}"


def resolve_overflow_url(*, post: ScheduledTextPost | None = None, db: Session | None = None) -> str:
    from app.services.aof_social_links import x_linkvertise_enabled, x_outbound_url
    from app.services.buffer_x_outbound_guard import buffer_x_require_gate_wrap, wrap_url_for_x_outbound

    if buffer_x_require_gate_wrap() or x_linkvertise_enabled():
        from app.data.aof_manual_gate_links import manual_gate_url

        gated = (manual_gate_url("mainhub") or manual_gate_url("main") or "").strip()
        if gated:
            return gated

    if not x_linkvertise_enabled():
        direct = x_outbound_url()
        if direct:
            return wrap_url_for_x_outbound(direct, gate_key="mainhub")
    env = (os.environ.get("TBCC_BUFFER_X_OVERFLOW_URL") or "").strip()
    if env:
        return wrap_url_for_x_outbound(env, gate_key="mainhub")
    if post is not None and db is not None:
        ch = db.query(Channel).filter(Channel.id == post.channel_id).first()
        if ch:
            link = (getattr(ch, "invite_link", None) or "").strip()
            if link:
                return wrap_url_for_x_outbound(link, gate_key="mainhub")
    return ""


def should_fit_for_x() -> bool:
    """Apply X length limit when mirroring (X-only or explicit env)."""
    if (os.environ.get("TBCC_BUFFER_X_ONLY") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return (os.environ.get("TBCC_BUFFER_X_FIT_CAPTION") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def fit_plaintext_for_x(
    plain: str,
    *,
    overflow_url: str | None = None,
    max_chars: int | None = None,
) -> str:
    """
    Keep the start of the caption; if over max_chars, end with an AOF Telegram invite CTA.
    """
    text = re.sub(r"\n{3,}", "\n\n", (plain or "").strip())
    if not text:
        return text
    limit = max_chars if max_chars is not None else buffer_x_max_chars()
    url = (overflow_url or "").strip()

    if len(text) <= limit:
        return text

    if not url:
        if len(text) <= limit:
            return text
        cut = text[: limit - 1].rstrip()
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0].rstrip()
        return cut + "…"

    suffix = buffer_x_overflow_suffix(url)
    if len(suffix) >= limit:
        return suffix[:limit]

    budget = limit - len(suffix) - 1
    if budget < 1:
        return suffix[:limit]

    head = text[:budget].rstrip()
    if " " in head and len(head) > 40:
        head = head.rsplit(" ", 1)[0].rstrip()
    return f"{head}…{suffix}"


def fit_buffer_mirror_plaintext(
    plain: str,
    *,
    post: ScheduledTextPost | None = None,
    db: Session | None = None,
) -> str:
    if not should_fit_for_x():
        return plain
    url = resolve_overflow_url(post=post, db=db)
    return fit_plaintext_for_x(plain, overflow_url=url or None)


def finalize_buffer_x_caption(
    plain: str,
    *,
    db: Session | None = None,
    overflow_url: str | None = None,
    advance_link_cycle: bool = False,
    network_key: str | None = None,
    strict: bool = False,
) -> str:
    """Apply link-order cycling then X length limit; wrap bare Telegram URLs."""
    from app.services.buffer_x_link_order import apply_buffer_x_link_cycle
    from app.services.buffer_x_outbound_guard import enforce_buffer_x_caption_urls

    body = apply_buffer_x_link_cycle(plain, db=db, advance=advance_link_cycle)
    body, errors = enforce_buffer_x_caption_urls(body, network_key=network_key, strict=strict)
    if strict and errors:
        raise ValueError(errors[0])
    overflow = overflow_url
    if overflow:
        from app.services.buffer_x_outbound_guard import wrap_url_for_x_outbound

        overflow = wrap_url_for_x_outbound(overflow, gate_key=network_key or "mainhub")
    return fit_plaintext_for_x(body, overflow_url=overflow)
