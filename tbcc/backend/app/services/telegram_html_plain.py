"""Convert Telegram HTML captions to plain text for Buffer / Discord (no new deps)."""

from __future__ import annotations

import html
import re


def telegram_html_to_plain(text: str, *, max_len: int = 2500) -> str:
    """Strip tags; unwrap <a href>. Normalize whitespace. Cap length for X-like limits."""
    raw = (text or "").strip()
    if not raw:
        return ""

    def _a_sub(m: re.Match[str]) -> str:
        href = (m.group(1) or "").strip()
        inner = re.sub(r"<[^>]+>", "", m.group(2) or "")
        inner = html.unescape(inner).strip()
        if inner and href:
            return f"{inner} {href}"
        return href or inner

    t = re.sub(
        r'<a\s+href=(["\'])([^"\']+)\1[^>]*>(.*?)</a>',
        _a_sub,
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\f\v]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if max_len > 0 and len(t) > max_len:
        t = t[: max_len - 1].rstrip() + "…"
    return t
