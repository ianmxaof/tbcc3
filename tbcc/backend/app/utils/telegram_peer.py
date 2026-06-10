"""Normalize Channel.identifier values for Telethon (get_input_entity / send_file)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


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
    if not isinstance(raw, str):
        # Already a Telethon InputPeer / entity (e.g. poster_worker follow-ups).
        return raw
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


def extract_invite_hash(raw: str | None) -> str | None:
    """
    Parse t.me/+hash, t.me/joinchat/hash, or bare +hash into the invite hash string.
    Returns None when the input is not a private invite link.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    low = s.lower()
    if "t.me/+" in low:
        try:
            h = s.split("+", 1)[1]
            return h.split("?")[0].split("/")[0].strip() or None
        except IndexError:
            return None
    if "joinchat/" in low:
        try:
            h = s.split("joinchat/", 1)[1]
            return h.split("?")[0].split("/")[0].strip() or None
        except IndexError:
            return None
    if s.startswith("+") and not s.startswith("+-") and len(s) > 1:
        return s[1:].split("?")[0].strip() or None
    return None


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


def _dialog_match_ids(normalized: str) -> set[int]:
    """Telegram ids to match when scanning dialogs for a -100… peer."""
    s = normalize_telethon_peer_identifier(normalized)
    ids: set[int] = set()
    if s.startswith("-100") and len(s) > 4 and s[4:].isdigit():
        ids.add(int(s))
        ids.add(int(s[4:]))
    elif s.startswith("-") and s[1:].isdigit():
        ids.add(int(s))
    elif s.isdigit():
        ids.add(int(f"-100{s}"))
        ids.add(int(s))
    return ids


async def find_entity_in_dialogs(client, normalized: str):
    """Last-resort: locate a supergroup/channel the poster account already joined."""
    want = _dialog_match_ids(normalized)
    if not want:
        return None
    async for dialog in client.iter_dialogs():
        ent = dialog.entity
        candidates = {getattr(ent, "id", None), getattr(dialog, "id", None)}
        if want.intersection(x for x in candidates if x is not None):
            return ent
    return None


async def resolve_entity_via_invite(client, invite_url: str, *, join_if_needed: bool = True):
    """
    Resolve a private group/supergroup via t.me/+ or joinchat link.
    Joins with ImportChatInvite when the poster account is not yet a member.
    """
    from telethon.errors import UserAlreadyParticipantError
    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest

    h = extract_invite_hash(invite_url)
    if not h:
        raise ValueError(f"Not a Telegram invite link: {invite_url!r}")

    check = await client(CheckChatInviteRequest(h))
    if getattr(check, "chat", None):
        return check.chat

    if not join_if_needed:
        raise ValueError(
            f"Invite {invite_url!r} is valid but the poster account is not a member yet."
        )

    try:
        updates = await client(ImportChatInviteRequest(h))
    except UserAlreadyParticipantError:
        check = await client(CheckChatInviteRequest(h))
        if getattr(check, "chat", None):
            return check.chat
        raise ValueError(f"Already in group but could not resolve chat for invite {invite_url!r}")

    chats = getattr(updates, "chats", None) or []
    if chats:
        return chats[0]
    raise ValueError(f"Joined via invite but Telegram returned no chat entity for {invite_url!r}")


async def resolve_telethon_entity(client, raw: str | None):
    """
    Resolve a channel/group/user for scraping or posting.
    Handles @username, t.me links, private invites, and -100xxxxxxxxxx numeric ids.
    """
    normalized = normalize_telethon_peer_identifier(raw)
    if not normalized:
        raise ValueError("empty channel identifier")

    invite_hash = extract_invite_hash(normalized)
    if invite_hash:
        return await resolve_entity_via_invite(client, normalized)

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


async def resolve_poster_peer(
    client,
    channel_identifier: str | None,
    *,
    invite_fallback: str | None = None,
):
    """
    Resolve Channel.identifier for the poster Telethon session (admin_poster.session).

    Private supergroups often fail bare -100… lookups until the entity is cached.
    Falls back to channels.invite_link (t.me/+…), dialog scan, and optional auto-join.
    """
    normalized = normalize_telethon_peer_identifier(channel_identifier)
    if not normalized:
        raise ValueError("empty channel identifier")

    fb = (invite_fallback or "").strip()
    attempts: list[str] = []
    for candidate in (normalized, fb):
        if candidate and candidate not in attempts:
            attempts.append(candidate)

    last_err: Exception | None = None
    for raw in attempts:
        try:
            ent = await resolve_telethon_entity(client, raw)
            if raw != normalized:
                logger.info(
                    "Resolved poster peer %r via %r",
                    normalized,
                    raw[:48] + ("…" if len(raw) > 48 else ""),
                )
            return ent
        except Exception as e:
            last_err = e
            logger.debug("resolve_poster_peer attempt %r failed: %s", raw, e)

    ent = await find_entity_in_dialogs(client, normalized)
    if ent is not None:
        logger.info("Resolved poster peer %r via dialog scan", normalized)
        return ent

    if fb and extract_invite_hash(fb):
        try:
            ent = await resolve_entity_via_invite(client, fb, join_if_needed=True)
            logger.info("Resolved poster peer %r via invite join %r", normalized, fb[:48])
            return ent
        except Exception as e:
            last_err = e
            logger.debug("invite join fallback failed for %r: %s", normalized, e)

    detail = str(last_err) if last_err else "unknown"
    raise ValueError(
        f"Cannot resolve Telegram destination {normalized!r}. "
        "The poster Telethon account (admin_poster.session) must be a member of this group: "
        "open it once in Telegram with that account, or set Dashboard → Content pools → "
        "Invite link to the current t.me/+ link. "
        "After a fresh DB setup, restart Celery and set TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 "
        "(or copy admin.session → admin_poster.session). "
        f"Detail: {detail}"
    ) from last_err
