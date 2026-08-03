"""Buffer Storage Hub intake so topics receive albums only (no lone media messages)."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT, INBOX_TOPIC_ID, STORAGE_HUB_IDENT
from app.services.intake_scheduler import get_album_size

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:album:buf"
MIN_ALBUM_POST = 2
ITEM_TTL_SECONDS = 86400 * 3

_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BUFFER_ROOT = _TBCC_ROOT / ".tbcc-run" / "storage-album-buffer"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def storage_hub_album_intake_enabled() -> bool:
    return (os.getenv("TBCC_STORAGE_HUB_ALBUM_INTAKE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def dest_key_for_topic(message_thread_id: int) -> str:
    return f"topic:{int(message_thread_id)}"


def dest_key_for_inbox_channel() -> str:
    return f"channel:{INBOX_CHANNEL_IDENT.lstrip('-')}"


def resolve_dest_key(*, message_thread_id: int | None = None, channel_ident: str | None = None) -> str:
    if channel_ident and str(channel_ident).lstrip("-") == INBOX_CHANNEL_IDENT.lstrip("-"):
        return dest_key_for_inbox_channel()
    if message_thread_id:
        return dest_key_for_topic(int(message_thread_id))
    raise ValueError("message_thread_id or inbox channel required")


def _pending_key(dest_key: str) -> str:
    return f"{REDIS_PREFIX}:{dest_key}"


def _buffer_dir(dest_key: str) -> Path:
    safe = dest_key.replace(":", "_")
    return BUFFER_ROOT / safe


def _save_staged_bytes(dest_key: str, raw: bytes, media_type: str) -> Path:
    bucket = "video" if (media_type or "").strip().lower() == "video" else "photo"
    dest_dir = _buffer_dir(dest_key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time())}_{secrets.token_hex(4)}_{bucket}.bin"
    path = dest_dir / name
    path.write_bytes(raw)
    return path


def _load_item(entry: dict[str, Any]) -> tuple[bytes, str] | None:
    path = Path(str(entry.get("path") or ""))
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    mt = str(entry.get("media_type") or "photo").strip().lower()
    if mt not in ("photo", "video"):
        mt = "photo"
    return data, mt


def _delete_item_files(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        path = Path(str(entry.get("path") or ""))
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
        except OSError:
            logger.debug("storage album buffer unlink failed path=%s", path, exc_info=True)


def _list_pending(dest_key: str) -> list[dict[str, Any]]:
    try:
        raw_items = _redis().lrange(_pending_key(dest_key), 0, -1) or []
    except Exception:
        logger.debug("storage album buffer read failed dest=%s", dest_key, exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            row = json.loads(raw)
            if isinstance(row, dict) and row.get("path"):
                out.append(row)
        except (TypeError, json.JSONDecodeError):
            continue
    return out


def pending_count(dest_key: str) -> int:
    return len(_list_pending(dest_key))


def enqueue_storage_hub_media(
    *,
    raw: bytes,
    media_type: str,
    message_thread_id: int | None = None,
    channel_ident: str | None = None,
) -> dict[str, Any]:
    """
    Stage one media item; flush full albums when the buffer reaches album_size.
    Never posts a single-item message — leftovers wait for the next item.
    """
    if not storage_hub_album_intake_enabled():
        return {"buffered": False, "reason": "disabled"}
    if not raw:
        return {"buffered": False, "reason": "empty"}

    dest_key = resolve_dest_key(message_thread_id=message_thread_id, channel_ident=channel_ident)
    path = _save_staged_bytes(dest_key, raw, media_type)
    entry = {
        "path": str(path),
        "media_type": "video" if (media_type or "").strip().lower() == "video" else "photo",
        "ts": time.time(),
    }
    try:
        r = _redis()
        r.rpush(_pending_key(dest_key), json.dumps(entry))
        r.expire(_pending_key(dest_key), ITEM_TTL_SECONDS)
    except Exception as e:
        _delete_item_files([entry])
        return {"buffered": False, "error": str(e)[:200]}

    flushed = flush_storage_hub_album_buffer(dest_key, force=False)
    pending = pending_count(dest_key)
    return {
        "buffered": True,
        "dest_key": dest_key,
        "pending": pending,
        "flushed": flushed,
        "album_size": get_album_size(),
    }


def flush_storage_hub_album_buffer(dest_key: str, *, force: bool = False) -> list[dict[str, Any]]:
    """Post buffered items as Telegram albums (≥2 items per album)."""
    album_size = min(max(get_album_size(), MIN_ALBUM_POST), 10)
    reports: list[dict[str, Any]] = []

    while True:
        pending = _list_pending(dest_key)
        if len(pending) < album_size and not (force and len(pending) >= MIN_ALBUM_POST):
            break
        take = album_size if len(pending) >= album_size else len(pending)
        if take < MIN_ALBUM_POST:
            break
        batch = pending[:take]
        remaining = pending[take:]
        items: list[tuple[bytes, str]] = []
        valid_batch: list[dict[str, Any]] = []
        for entry in batch:
            loaded = _load_item(entry)
            if loaded:
                items.append(loaded)
                valid_batch.append(entry)
        if len(items) < MIN_ALBUM_POST:
            break

        thread_id: int | None = None
        channel_ident: str | None = None
        if dest_key.startswith("topic:"):
            thread_id = int(dest_key.split(":", 1)[1])
            channel_ident = STORAGE_HUB_IDENT
        elif dest_key.startswith("channel:"):
            channel_ident = f"-{dest_key.split(':', 1)[1]}"

        report = _post_album_items(
            items,
            message_thread_id=thread_id,
            channel_ident=channel_ident or STORAGE_HUB_IDENT,
            count=len(items),
        )
        reports.append(report)

        if not report.get("ok"):
            break

        try:
            pipe = _redis().pipeline()
            pipe.delete(_pending_key(dest_key))
            for entry in remaining:
                pipe.rpush(_pending_key(dest_key), json.dumps(entry))
            pipe.expire(_pending_key(dest_key), ITEM_TTL_SECONDS)
            pipe.execute()
        except Exception:
            logger.debug("storage album buffer rewrite failed dest=%s", dest_key, exc_info=True)
            break
        _delete_item_files(valid_batch)

        if len(remaining) < album_size:
            break

    return reports


def flush_all_storage_hub_album_buffers(*, force: bool = False) -> dict[str, Any]:
    """Flush every known destination buffer (operator force)."""
    from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP

    keys = [dest_key_for_inbox_channel(), dest_key_for_topic(INBOX_TOPIC_ID)]
    keys.extend(dest_key_for_topic(m.message_thread_id) for m in AOF_STORAGE_TOPIC_MAP)
    keys = list(dict.fromkeys(keys))
    out: dict[str, Any] = {"destinations": [], "flushed_albums": 0}
    for key in keys:
        if pending_count(key) < MIN_ALBUM_POST and not force:
            continue
        reports = flush_storage_hub_album_buffer(key, force=force)
        if reports:
            out["destinations"].append({"dest_key": key, "reports": reports})
            out["flushed_albums"] += sum(1 for r in reports if r.get("ok"))
    return out


def _post_album_items(
    items: list[tuple[bytes, str]],
    *,
    message_thread_id: int | None,
    channel_ident: str,
    count: int,
) -> dict[str, Any]:
    from app.services.telegram_admin import run_telegram_import_io
    from app.services.telegram_storage import TelegramStorage

    async def _job(storage: TelegramStorage):
        return await storage.post_bytes_to_channel(
            channel_ident,
            items,
            message_thread_id,
            caption=None,
            send_silent=False,
            skip_watermark=False,
        )

    try:
        result = run_telegram_import_io_sync(_job)
    except Exception as e:
        logger.warning(
            "storage hub album flush failed topic=%s count=%s: %s",
            message_thread_id,
            count,
            e,
            exc_info=True,
        )
        return {"ok": False, "error": str(e)[:200], "count": count}

    ok = bool(result.get("ok")) if isinstance(result, dict) else False
    if ok and message_thread_id:
        try:
            from app.data.aof_storage_hub_map import network_key_for_storage_topic
            from app.services.storage_auto_pipe import signal_lane_auto_pipe

            lane = network_key_for_storage_topic(int(message_thread_id))
            if lane:
                signal_lane_auto_pipe(lane, int(message_thread_id))
        except Exception:
            logger.debug("album intake auto-pipe signal failed", exc_info=True)
    return {
        "ok": ok,
        "count": count,
        "message_thread_id": message_thread_id,
        "channel_ident": channel_ident,
        "result": result if isinstance(result, dict) else {},
    }


def run_telegram_import_io_sync(coro_factory):
    """Sync wrapper — import at call site avoids circular import at module load."""
    import asyncio

    from app.services.telegram_admin import run_telegram_import_io

    async def _wrap():
        return await run_telegram_import_io(coro_factory)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_wrap())
    if loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_wrap())).result()
    return loop.run_until_complete(_wrap())


from app.data.aof_storage_hub_map import INBOX_TOPIC_ID
