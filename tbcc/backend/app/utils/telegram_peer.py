"""Normalize Channel.identifier values for Telethon (get_input_entity / send_file)."""

from __future__ import annotations

import re


def normalize_telethon_peer_identifier(raw: str | None) -> str:
    """
    Telegram channel / supergroup API ids use -100xxxxxxxxxx.

    Operators often paste only the inner digits (e.g. from /appeal3835807622 or RawDataBot
    fragments) or strip -100 thinking it means "group not channel". Telethon then raises
    ValueError: Cannot find any entity corresponding to "3835807622".

    - @username, t.me/..., +invite hashes: returned unchanged
    - bare digits: prefixed with -100
    - already -100... or other negative ids: unchanged
    """
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return s
    low = s.lower()
    if s.startswith("@"):
        return s
    if "t.me/" in low or low.startswith("http://") or low.startswith("https://"):
        return s
    if low.startswith("joinchat/"):
        return s
    if s.startswith("+") and not s.startswith("+-"):  # +hash invite
        return s
    if s.startswith("-100") and len(s) > 4 and s[4:].isdigit():
        return s
    if s.startswith("-") and s[1:].isdigit():
        return s
    if s.isdigit():
        return f"-100{s}"
    return s


def normalize_telegram_username(raw: str | None) -> str:
    """Accept @name, name, or https://t.me/name/... for Telethon username peers."""
    s = normalize_telethon_peer_identifier(raw)
    if not s:
        return s
    if "t.me/" in s.lower():
        try:
            part = s.split("t.me/", 1)[1].split("/")[0].split("?")[0]
            s = part
        except IndexError:
            pass
    if s.startswith("@"):
        s = s[1:]
    return s


def _numeric_peer_candidates(normalized: str) -> list[int | object]:
    """Build Telethon get_entity candidates for -100… / bare digit channel ids."""
    from telethon.tl.types import PeerChannel

    s = normalized.strip()
    out: list[int | object] = []
    if s.startswith("-100") and len(s) > 4 and s[4:].isdigit():
        channel_id = int(s[4:])
        out.extend([int(s), PeerChannel(channel_id), channel_id])
    elif s.startswith("-") and s[1:].isdigit():
        out.append(int(s))
    elif s.isdigit():
        full = f"-100{s}"
        channel_id = int(s)
        out.extend([int(full), PeerChannel(channel_id), channel_id])
    return out


async def resolve_telethon_entity(client, raw: str | None):
    """
    Resolve a channel/group/user for scraping or posting.
    Handles @username, t.me links, and -100xxxxxxxxxx numeric ids.
    """
    normalized = normalize_telethon_peer_identifier(raw)
    if not normalized:
        raise ValueError("empty channel identifier")

    low = normalized.lower()
    if normalized.startswith("@") or "t.me/" in low or low.startswith("http://") or low.startswith("https://"):
        username = normalize_telegram_username(normalized)
        if username and re.fullmatch(r"[A-Za-z0-9_]{4,}", username):
            return await client.get_entity(username)
        return await client.get_entity(normalized)

    candidates = _numeric_peer_candidates(normalized)
    if candidates:
        errors: list[str] = []
        for candidate in candidates:
            try:
                return await client.get_entity(candidate)
            except Exception as e:
                errors.append(str(e))
        hint = (
            "Numeric channel id could not be resolved. Open/join this channel with the scraper "
            "Telegram account (scraper.session), or set the source identifier to @username / t.me link."
        )
        raise ValueError(f"{hint} Last error: {errors[-1] if errors else 'unknown'}")

    return await client.get_entity(normalized)
