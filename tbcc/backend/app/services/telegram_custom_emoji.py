"""Telegram custom emoji in HTML captions (Telethon poster path).

Telethon 1.34+ parses Bot-API-style tags in HTML mode::

    <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>

The placeholder inside the tag must be exactly one character (Telegram rule).
Third-party packs (PlatinumBlueAlphabet, etc.) work when the poster account can use them.
"""

from __future__ import annotations

import re
from typing import Any

from telethon.extensions import html as telethon_html
from telethon.helpers import add_surrogate, del_surrogate
from telethon.tl.types import MessageEntityCustomEmoji, TypeMessageEntity

_TG_EMOJI_TAG_RE = re.compile(
    r"<tg-emoji\s+emoji-id=(['\"])(\d+)\1\s*>(.*?)</tg-emoji>",
    re.IGNORECASE | re.DOTALL,
)


def build_tg_emoji_tag(document_id: int | str, placeholder: str = "⭐") -> str:
    """One custom emoji as Telegram HTML (placeholder must be a single character)."""
    ph = (placeholder or "⭐").strip()
    if len(ph) != 1:
        ph = ph[0] if ph else "⭐"
    return f'<tg-emoji emoji-id="{int(document_id)}">{ph}</tg-emoji>'


def join_tg_emoji_tags(tags: list[str], separator: str = "") -> str:
    return separator.join(tags)


def count_custom_emoji_entities(entities: list[TypeMessageEntity] | None) -> int:
    if not entities:
        return 0
    return sum(1 for e in entities if isinstance(e, MessageEntityCustomEmoji))


def parse_telethon_html(html: str) -> tuple[str, list[TypeMessageEntity]]:
    """Parse Telegram HTML to (plain text, entities) for formatting_entities=."""
    raw = (html or "").strip()
    if not raw:
        return "", []
    return telethon_html.parse(raw)


def validate_telethon_html(html: str) -> dict[str, Any]:
    """Dry-run parse; report custom emoji count and placeholder issues."""
    raw = (html or "").strip()
    if not raw:
        return {"ok": True, "custom_emoji_count": 0, "issues": [], "plain_length": 0}
    issues: list[str] = []
    for m in _TG_EMOJI_TAG_RE.finditer(raw):
        inner = m.group(3) or ""
        if len(inner) != 1:
            issues.append(
                f"emoji-id {m.group(2)}: inner text must be exactly one character (got {len(inner)})"
            )
    try:
        text, entities = parse_telethon_html(raw)
    except Exception as e:
        return {"ok": False, "error": str(e), "issues": issues}
    return {
        "ok": True,
        "plain_length": len(text),
        "custom_emoji_count": count_custom_emoji_entities(entities),
        "entity_types": [type(e).__name__ for e in entities],
        "issues": issues,
    }


def telethon_message_kwargs(html: str | None, *, empty_fallback: str = "") -> dict[str, Any]:
    """
    Kwargs for send_message / send_file caption: uses formatting_entities when needed
    so custom emoji are not stripped.
    """
    raw = (html or "").strip()
    if not raw:
        fb = empty_fallback or ""
        return {"message": fb} if fb else {}
    text, entities = parse_telethon_html(raw)
    if entities:
        return {"message": text, "formatting_entities": entities}
    return {"message": text, "parse_mode": "html"}


def entity_text_at_offset(text: str, offset: int, length: int) -> str:
    """Slice using Telegram UTF-16 code unit offsets (required for entity placeholder chars)."""
    sur = add_surrogate(text or "")
    chunk = sur[int(offset) : int(offset) + int(length)]
    out = del_surrogate(chunk)
    if not out:
        return "⭐"
    return out[0] if len(out) > 1 else out


def _banner_only_html(text: str, custom: list[MessageEntityCustomEmoji], *, preserve_newlines: bool) -> str:
    """Only ``<tg-emoji>`` tags — no caption body; optional ``\\n`` between banner rows."""
    if not custom:
        return ""
    sur = add_surrogate(text or "")
    parts: list[str] = []
    for i, e in enumerate(custom):
        ph = entity_text_at_offset(text, e.offset, e.length)
        parts.append(build_tg_emoji_tag(e.document_id, ph))
        if preserve_newlines and i + 1 < len(custom):
            gap_start = int(e.offset) + int(e.length)
            gap_end = int(custom[i + 1].offset)
            if gap_end > gap_start:
                gap = del_surrogate(sur[gap_start:gap_end])
                if "\n" in gap:
                    parts.append("\n")
    return "".join(parts)


def custom_emoji_html_from_message(
    text: str,
    entities: list[TypeMessageEntity] | None,
    *,
    layout: str = "banner_only",
) -> str:
    """
    Build HTML for custom emoji in a Telegram message.

    layout:
      - ``banner_only`` (default): only ``<tg-emoji>`` tags; keeps ``\\n`` between rows;
        omits plain caption body (for reusable banners).
      - ``tags_only``: same without row breaks (single-line concatenation).
      - ``unparse``: Telethon html.unparse on custom entities only (includes plain text
        between emoji and any non-emoji caption — rarely wanted for presets).
    """
    if not text or not entities:
        return ""
    custom = sorted(
        [e for e in entities if isinstance(e, MessageEntityCustomEmoji)],
        key=lambda x: x.offset,
    )
    if not custom:
        return ""

    if layout == "tags_only":
        return _banner_only_html(text, custom, preserve_newlines=False)
    if layout == "banner_only":
        return _banner_only_html(text, custom, preserve_newlines=True)

    return telethon_html.unparse(text, custom)


def prepend_html(prefix: str, body: str) -> str:
    p = (prefix or "").strip()
    b = (body or "").strip()
    if not p:
        return b
    if not b:
        return p
    return f"{p}\n\n{b}"
