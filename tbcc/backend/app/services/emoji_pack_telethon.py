"""
Upload VP9 WebM tiles from emoji-factory manifest as a Telegram custom emoji set.

Uses the TBCC admin Telethon session (your user account owns the pack).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from telethon import TelegramClient, utils
from telethon.tl.functions.messages import UploadMediaRequest
from telethon.tl.functions.stickers import AddStickerToSetRequest, CreateStickerSetRequest
from telethon.tl.types import (
    DocumentAttributeVideo,
    InputDocument,
    InputMediaUploadedDocument,
    InputStickerSetItem,
    InputStickerSetShortName,
)

from app.services.telegram_custom_emoji import telethon_message_kwargs
from app.services.telegram_custom_emoji_catalog import fetch_custom_emoji_pack

logger = logging.getLogger(__name__)

# Telegram CreateStickerSetRequest rejects video stickers above this size.
TELEGRAM_MAX_VIDEO_STICKER_BYTES = 256 * 1024


def slug_short_name_base(raw: str) -> str:
    """Telegram-safe base (before ``_by_<user_id>``): starts with a letter, no ``__``."""
    s = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "pack"
    if not s[0].isalpha():
        s = f"pack_{s}"
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40] or "pack"


def normalize_short_name(raw: str, *, user_id: int) -> str:
    """
    Telegram custom emoji set short name rules:
    - begins with a letter
    - lowercase letters, digits, single underscores only
    - ends with ``_by_<user_id>`` for user-owned sets
    """
    s = slug_short_name_base(raw)
    suffix = f"_by_{user_id}"
    max_base = max(1, 64 - len(suffix))
    if len(s) > max_base:
        s = s[:max_base].rstrip("_")
    if not s or not s[0].isalpha():
        s = "pack"
    full = f"{s}{suffix}"
    full = re.sub(r"_+", "_", full)
    if "__" in full:
        raise ValueError("short_name cannot contain consecutive underscores")
    if not full.endswith(suffix):
        raise ValueError(f"short_name must end with {suffix}")
    if not re.match(r"^[a-z][a-z0-9_]*$", full):
        raise ValueError(
            f"short_name invalid after normalization: {full!r}. "
            "Must start with a letter; use only a-z, 0-9, and single underscores."
        )
    return full


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "tiles" not in data:
        raise ValueError("invalid manifest: missing tiles")
    return data


async def _upload_tile_input_document(
    client: TelegramClient,
    tile_path: Path,
    *,
    duration_sec: float,
) -> InputDocument:
    """Upload tile bytes for sticker set API — does not post a document to Saved Messages."""
    uploaded = await client.upload_file(str(tile_path))
    media = InputMediaUploadedDocument(
        file=uploaded,
        mime_type="video/webm",
        attributes=[
            DocumentAttributeVideo(
                duration=max(0.5, float(duration_sec)),
                w=100,
                h=100,
                supports_streaming=True,
            ),
        ],
        nosound_video=True,
    )
    peer = await client.get_input_entity("me")
    result = await client(UploadMediaRequest(peer=peer, media=media))
    doc = getattr(result, "document", None)
    if doc is None:
        raise RuntimeError(f"UploadMedia did not return a document for {tile_path.name}")
    inp = utils.get_input_document(doc)
    if not isinstance(inp, InputDocument):
        inp = InputDocument(
            id=doc.id,
            access_hash=doc.access_hash,
            file_reference=doc.file_reference,
        )
    return inp


def _build_grid_preview_html(*, title: str, short_name: str, tags: list[str], cols: int, rows: int) -> str:
    """One message: clickable pack-name header + emoji grid (row-major) using <tg-emoji> tags."""
    lines: list[str] = []
    for r in range(rows):
        row_tags = tags[r * cols : (r + 1) * cols]
        if row_tags:
            lines.append("".join(row_tags))
    grid = "\n".join(lines)
    safe_title = (title or "Emoji pack").replace("<", "").replace(">", "")[:64]
    install_url = f"https://t.me/addemoji/{short_name}"
    return (
        f'<a href="{install_url}">{safe_title}</a>\n'
        "Tap the pack name above or any emoji below, then choose <b>Add emoji</b> to install.\n\n"
        f"{grid}"
    )


async def _send_pack_preview_to_saved(
    client: TelegramClient,
    *,
    short_name: str,
    title: str,
    manifest: dict,
) -> int | None:
    """Post one Saved Messages message with the full grid as custom emojis (installable pack)."""
    pack = await fetch_custom_emoji_pack(client, short_name=short_name)
    emojis = pack.get("emojis") or []
    if not emojis:
        return None
    cols = int(manifest.get("cols") or 0) or 4
    rows = int(manifest.get("rows") or 0) or max(1, len(emojis) // cols)
    tags = [str(e.get("tag") or "") for e in emojis[: cols * rows]]
    tags = [t for t in tags if t]
    if not tags:
        return None
    html = _build_grid_preview_html(title=title, short_name=short_name, tags=tags, cols=cols, rows=rows)
    msg = await client.send_message("me", **telethon_message_kwargs(html))
    return int(msg.id) if msg else None


async def post_pack_preview_to_saved(
    client: TelegramClient,
    *,
    short_name: str,
    title: str,
    manifest_path: Path,
) -> int | None:
    """Post the live emoji grid to Saved Messages (optional; pack must already exist)."""
    manifest = load_manifest(manifest_path.resolve())
    return await _send_pack_preview_to_saved(
        client,
        short_name=short_name,
        title=title[:64],
        manifest=manifest,
    )


async def upload_custom_emoji_pack_from_manifest(
    client: TelegramClient,
    *,
    manifest_path: Path,
    title: str,
    short_name: str,
    dry_run: bool = False,
    post_saved_preview: bool = False,
) -> dict:
    """
    Create a custom emoji sticker set from manifest.json produced by emoji-factory.
    Optionally posts a live emoji grid to Saved Messages (post_saved_preview=True).
    """
    manifest_path = manifest_path.resolve()
    base_dir = manifest_path.parent
    manifest = load_manifest(manifest_path)
    tiles = manifest.get("tiles") or []
    if not tiles:
        raise ValueError("manifest has no tiles")

    params = manifest.get("params") or {}
    duration_sec = float(params.get("loop_sec") or 3.0)

    me = await client.get_me()
    if me is None:
        raise RuntimeError("Telegram client not authorized")
    user_id = await client.get_input_entity(me)
    short_name = normalize_short_name(short_name, user_id=me.id)

    paths = [base_dir / t["file"] for t in tiles]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"missing tiles: {missing[0]}")
    too_big = [(p.name, p.stat().st_size) for p in paths if p.stat().st_size > TELEGRAM_MAX_VIDEO_STICKER_BYTES]
    if too_big:
        sample = ", ".join(f"{n} ({s // 1024} KB)" for n, s in too_big[:4])
        extra = f" (+{len(too_big) - 4} more)" if len(too_big) > 4 else ""
        raise ValueError(
            f"{len(too_big)} tile(s) exceed Telegram's 256 KB limit: {sample}{extra}. "
            "Re-run split (TBCC auto-compresses) or raise CRF / shorten loop in Advanced."
        )

    # Telegram custom emoji require exactly 100×100 px tiles.
    wrong_px = [
        (t.get("file", "?"), int(t.get("tile_px_used") or 0))
        for t in tiles
        if int(t.get("tile_px_used") or 0) not in (0, 100)
    ]
    if wrong_px:
        sample_name, sample_px = wrong_px[0]
        raise ValueError(
            f"Tile '{sample_name}' is {sample_px}×{sample_px} px — Telegram custom emoji require exactly "
            f"100×100 px. Re-run split with tile_px=100 (dashboard default) or run "
            f"scripts/recompress-emoji-pack.py on the pack-out folder."
        )

    if dry_run:
        return {
            "dry_run": True,
            "title": title,
            "short_name": short_name,
            "tile_count": len(tiles),
            "total_bytes": sum(p.stat().st_size for p in paths),
            "note": "Publish creates the pack and sends one grid preview to Saved Messages (no loose .webm files).",
        }

    sticker_items: list[InputStickerSetItem] = []
    for tile in tiles:
        rel = tile.get("file") or ""
        tile_path = base_dir / rel
        if not tile_path.is_file():
            raise FileNotFoundError(tile_path)
        emoji = (tile.get("emoji") or "🎬").strip() or "🎬"
        inp = await _upload_tile_input_document(client, tile_path, duration_sec=duration_sec)
        sticker_items.append(InputStickerSetItem(document=inp, emoji=emoji))

    first, *rest = sticker_items
    await client(
        CreateStickerSetRequest(
            user_id=user_id,
            title=title[:64],
            short_name=short_name,
            stickers=[first],
            emojis=True,
        )
    )
    stickerset = InputStickerSetShortName(short_name=short_name)
    for item in rest:
        await client(AddStickerToSetRequest(stickerset=stickerset, sticker=item))

    preview_msg_id: int | None = None
    if post_saved_preview:
        preview_msg_id = await _send_pack_preview_to_saved(
            client,
            short_name=short_name,
            title=title[:64],
            manifest=manifest,
        )

    install_url = f"https://t.me/addemoji/{short_name}"
    if post_saved_preview:
        install_hint = (
            "Live emoji grid copied to Saved Messages — tap any tile → Add emoji."
        )
    else:
        install_hint = "Tap View Emoji to install the pack."

    return {
        "dry_run": False,
        "title": title,
        "short_name": short_name,
        "tile_count": len(sticker_items),
        "install_url": install_url,
        "saved_messages_preview_id": preview_msg_id,
        "install_hint": install_hint,
    }
