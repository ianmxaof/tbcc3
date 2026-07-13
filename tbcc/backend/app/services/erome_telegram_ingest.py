"""Storage Hub forum topic → download, watermark, Erome album upload."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.media_sniff import sniff_media_kind
from app.services.erome_upload_provision import (
    UploadResult,
    load_flow_config,
    scan_staging_folder,
    selectors_ready,
    upload_local_folder,
)
from app.services.mega_erome_staging import apply_aof_watermarks_to_files, erome_staging_dir

logger = logging.getLogger(__name__)

_EROME_TOPIC_ENV = "TBCC_EROME_STORAGE_TOPIC_ID"
_EROME_AUTO_ENV = "TBCC_EROME_AUTO_UPLOAD"
_EROME_MAX_FILES_ENV = "TBCC_EROME_MAX_FILES_PER_ALBUM"
_EROME_GROUP_WAIT_ENV = "TBCC_EROME_GROUPED_WAIT_SEC"


def erome_auto_upload_enabled() -> bool:
    raw = (os.getenv(_EROME_AUTO_ENV) or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def erome_max_files_per_album() -> int:
    raw = (os.getenv(_EROME_MAX_FILES_ENV) or "50").strip()
    try:
        return max(1, min(100, int(raw)))
    except ValueError:
        return 50


def erome_upload_job_key(message) -> int:
    """Dedup key for in-flight uploads — albums share grouped_id."""
    gid = getattr(message, "grouped_id", None)
    if gid:
        return int(gid)
    return int(message.id)


def erome_grouped_wait_sec() -> float:
    raw = (os.getenv(_EROME_GROUP_WAIT_ENV) or "2.5").strip()
    try:
        return max(0.5, min(10.0, float(raw)))
    except ValueError:
        return 2.5


def erome_storage_topic_id() -> int | None:
    """Forum message_thread_id for the dedicated Erome upload lane."""
    raw = (os.getenv(_EROME_TOPIC_ENV) or "").strip()
    if raw:
        try:
            tid = int(raw)
            return tid if tid > 0 else None
        except ValueError:
            return None
    try:
        from app.data.aof_storage_hub_map import EROME_STORAGE_TOPIC_MAP

        if EROME_STORAGE_TOPIC_MAP.message_thread_id > 0:
            return int(EROME_STORAGE_TOPIC_MAP.message_thread_id)
    except Exception:
        pass
    return None


def is_erome_storage_topic(message_thread_id: int | None) -> bool:
    tid = erome_storage_topic_id()
    if not tid or message_thread_id is None:
        return False
    return int(message_thread_id) == int(tid)


def is_storage_hub_chat(chat_id: int | str) -> bool:
    return str(chat_id) == str(STORAGE_HUB_IDENT)


def album_title_from_messages(messages: list) -> str:
    for msg in messages:
        text = (getattr(msg, "message", None) or getattr(msg, "text", None) or "").strip()
        if text and not text.startswith("/"):
            first = text.split("\n", 1)[0].strip()
            if first:
                return first[:120]
    cfg = load_flow_config()
    return (cfg.album_title_default or "AOF Network").strip() or "AOF Network"


def _staging_folder_for_batch(chat_id: int, thread_id: int, anchor_id: int) -> Path:
    slug = f"tg_{abs(int(chat_id))}_{thread_id}_{anchor_id}"
    root = erome_staging_dir() / "telegram" / slug
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ext_for_message(data: bytes, message) -> str:
    kind, ext = sniff_media_kind(data)
    media = getattr(message, "media", None)
    if isinstance(media, MessageMediaDocument):
        for attr in getattr(media.document, "attributes", []) or []:
            name = type(attr).__name__
            if name == "DocumentAttributeFilename":
                fn = getattr(attr, "file_name", None) or ""
                if "." in fn:
                    return fn.rsplit(".", 1)[-1].lower()[:8]
    if kind == "gif":
        return "gif"
    return ext or "bin"


async def collect_album_messages(client, chat_id: int, thread_id: int, anchor) -> list:
    """Single message or full Telegram album (grouped_id)."""
    if not getattr(anchor, "media", None):
        return []
    gid = getattr(anchor, "grouped_id", None)
    if not gid:
        return [anchor]
    await asyncio.sleep(erome_grouped_wait_sec())
    collected: list = []
    async for msg in client.iter_messages(int(chat_id), limit=40, reply_to=int(thread_id)):
        if getattr(msg, "grouped_id", None) == gid and getattr(msg, "media", None):
            collected.append(msg)
    collected.sort(key=lambda m: int(m.id))
    return collected or [anchor]


async def download_messages_to_staging(
    client,
    messages: list,
    folder: Path,
) -> list[Path]:
    saved: list[Path] = []
    for idx, msg in enumerate(messages):
        try:
            data = await client.download_media(msg, bytes)
        except Exception as e:
            logger.warning("erome ingest download failed msg=%s: %s", getattr(msg, "id", "?"), e)
            continue
        if not data or len(data) < 200:
            logger.warning("erome ingest empty download msg=%s", getattr(msg, "id", "?"))
            continue
        kind, ext = sniff_media_kind(data)
        if kind == "document" and ext == "bin":
            logger.warning("erome ingest unsupported media msg=%s", getattr(msg, "id", "?"))
            continue
        ext = _ext_for_message(data, msg)
        path = folder / f"{idx:03d}_{int(msg.id)}.{ext}"
        path.write_bytes(data)
        saved.append(path)
    return saved


def filter_valid_staged_files(files: list[Path]) -> tuple[list[Path], list[str]]:
    """Drop corrupt/unknown files before watermark + Erome upload."""
    ok: list[Path] = []
    skipped: list[str] = []
    for path in files:
        try:
            raw = path.read_bytes()
        except Exception as e:
            skipped.append(f"{path.name}:read_failed:{e}")
            continue
        if len(raw) < 200:
            skipped.append(f"{path.name}:too_small")
            continue
        kind, ext = sniff_media_kind(raw)
        if kind == "document" and ext == "bin":
            skipped.append(f"{path.name}:unknown_format")
            continue
        ok.append(path)
    return ok, skipped


def watermark_staged_files(files: list[Path]) -> int:
    return apply_aof_watermarks_to_files(files)


def upload_staged_folder(
    folder: Path,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    max_files: int | None = None,
    skip_watermark: bool = False,
    source: str = "staging",
    network_key: str | None = None,
    watermark: dict | None = None,
    crop: dict | None = None,
    content_notes: str | None = None,
    force_policy: bool = False,
    headed: bool = False,
    keep_open: bool = False,
    visibility: str | None = None,
    db=None,
) -> UploadResult:
    from app.services.erome_upload_analytics import (
        EromeUploadParams,
        collect_staging_metadata,
        merge_sidecar_params,
        record_erome_upload,
    )
    from app.services.erome_upload_governance import default_upload_visibility
    from app.services.erome_upload_policy import check_upload_policy, policy_block_message

    if not selectors_ready(load_flow_config()):
        return UploadResult(ok=False, staging_path=str(folder), error="erome_flow_not_configured")
    cfg = load_flow_config()
    lim = max_files if max_files is not None else erome_max_files_per_album()
    scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=lim)
    if not scan.ok:
        return UploadResult(ok=False, staging_path=str(folder), error="no_media_files")

    valid, skipped = filter_valid_staged_files(scan.files)
    if skipped:
        logger.warning("erome staging skipped invalid files: %s", skipped[:5])
    if not valid:
        return UploadResult(
            ok=False,
            staging_path=str(folder),
            error="invalid_media_files",
        )
    scan.files = valid

    params = merge_sidecar_params(
        folder,
        EromeUploadParams(
            title=title,
            description=description,
            tags=list(tags or []),
            source=source,
            network_key=network_key,
            staging_path=str(folder),
            watermark=watermark,
            crop=crop,
            content_notes=content_notes,
            file_count=len(scan.files),
            force_policy=force_policy,
            visibility=visibility,
        ),
    )
    if not params.visibility:
        params.visibility = default_upload_visibility()

    # Sidecar / intel-week: videos only + single-file albums
    side = {}
    try:
        from app.services.erome_upload_analytics import read_erome_sidecar

        side = read_erome_sidecar(folder)
    except Exception:
        side = {}
    if side.get("videos_only"):
        video_exts = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
        before = len(scan.files)
        scan.files = [p for p in scan.files if p.suffix.lower() in video_exts]
        if before and not scan.files:
            return UploadResult(
                ok=False,
                staging_path=str(folder),
                title=params.title,
                visibility=params.visibility or default_upload_visibility(),
                error="videos_only_no_videos",
            )
    side_max = side.get("max_files")
    if side_max is not None:
        try:
            lim = min(lim, max(1, int(side_max)))
        except (TypeError, ValueError):
            pass
        scan.files = scan.files[:lim]
        params.file_count = len(scan.files)

    verdict = check_upload_policy(
        title=params.title,
        description=params.description,
        file_count=len(scan.files),
        tags=params.tags,
        source=source,
        force=force_policy,
    )
    if not verdict.allowed:
        return UploadResult(
            ok=False,
            staging_path=str(folder),
            title=params.title,
            visibility=params.visibility or default_upload_visibility(),
            error=f"policy_blocked:{policy_block_message(verdict)}",
        )

    if not skip_watermark:
        watermark_staged_files(scan.files)

    staging_meta = collect_staging_metadata(scan.files)
    result = upload_local_folder(
        folder,
        title=params.title,
        description=params.description,
        tags=params.tags,
        max_files=lim,
        headed=headed,
        keep_open=keep_open,
        visibility=params.visibility,
    )

    record_erome_upload(
        params,
        result.to_dict(),
        staging_meta=staging_meta,
        policy=verdict.to_dict(),
        db=db,
    )
    if result.ok:
        # Producer signal for the idle governor: a fresh Erome album means
        # erome_view_sync has new work to poll for. Covers every producer that
        # funnels through here (Telegram ingest, CLI, album composer bytes).
        try:
            from app.services.idle_service_governor import touch_service_activity

            touch_service_activity("erome_view_sync")
        except Exception:
            logger.debug("erome governor signal skipped", exc_info=True)
    return result


async def ingest_telegram_messages_to_erome(
    client,
    *,
    chat_id: int,
    thread_id: int,
    anchor_message,
    title: str | None = None,
) -> dict[str, Any]:
    messages = await collect_album_messages(client, chat_id, thread_id, anchor_message)
    if not messages:
        return {"ok": False, "error": "no_media"}
    folder = _staging_folder_for_batch(chat_id, thread_id, int(anchor_message.id))
    files = await download_messages_to_staging(client, messages, folder)
    if not files:
        return {"ok": False, "error": "download_failed", "staging_path": str(folder)}
    valid, skipped = filter_valid_staged_files(files)
    if skipped:
        logger.warning("erome ingest skipped invalid files: %s", skipped[:5])
    files = valid
    if not files:
        return {
            "ok": False,
            "error": "invalid_media_files",
            "staging_path": str(folder),
            "skipped": skipped[:10],
        }
    album_title = (title or "").strip() or album_title_from_messages(messages)
    result = await asyncio.to_thread(
        upload_staged_folder,
        folder,
        title=album_title,
        source="telegram",
        force_policy=False,
    )
    body = result.to_dict()
    body["ok"] = bool(result.ok)
    body["message_ids"] = [int(m.id) for m in messages]
    body["file_count"] = len(files)
    body["title"] = album_title
    return body


def stage_processed_bytes_for_erome(
    items: list[tuple[bytes, str]],
    *,
    batch_key: str,
) -> tuple[Path, list[Path]]:
    """Write pre-processed (crop/watermark) bytes into an Erome staging folder."""
    from app.services.media_sniff import sniff_media_kind

    folder = erome_staging_dir() / "composer" / batch_key
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for idx, (data, hint) in enumerate(items):
        _kind, ext = sniff_media_kind(data)
        if not ext or ext == "bin":
            ext = "mp4" if hint == "video" else "jpg"
        path = folder / f"{idx:03d}.{ext}"
        path.write_bytes(data)
        paths.append(path)
    return folder, paths


async def upload_processed_bytes_to_erome(
    items: list[tuple[bytes, str]],
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    max_files: int | None = None,
    skip_watermark: bool = True,
    source: str = "composer",
    watermark: dict | None = None,
    crop: dict | None = None,
    content_notes: str | None = None,
    force_policy: bool = False,
    visibility: str | None = None,
    db=None,
) -> dict[str, Any]:
    """Album Composer / API path — bytes already cropped/watermarked."""
    import time

    if not items:
        return {"ok": False, "error": "no_media"}
    batch_key = f"cmp_{int(time.time())}_{len(items)}"
    folder, paths = stage_processed_bytes_for_erome(items, batch_key=batch_key)
    cfg = load_flow_config()
    album_title = (title or "").strip() or cfg.album_title_default or "AOF Network"
    result = await asyncio.to_thread(
        upload_staged_folder,
        folder,
        title=album_title,
        description=description,
        tags=tags,
        max_files=max_files,
        skip_watermark=skip_watermark,
        source=source,
        watermark=watermark,
        crop=crop,
        content_notes=content_notes,
        force_policy=force_policy,
        visibility=visibility,
        db=db,
    )
    body = result.to_dict()
    body["ok"] = bool(result.ok)
    body["file_count"] = len(paths)
    body["title"] = album_title
    if result.error and result.error.startswith("policy_blocked:"):
        body["policy_blocked"] = True
        body["error"] = result.error.split(":", 1)[-1]
    return body


def format_erome_upload_reply(report: dict[str, Any], *, html: bool = False) -> str:
    if not report.get("ok"):
        err = report.get("error") or "unknown"
        if err == "invalid_media_files":
            err = "downloaded files were empty or unsupported format"
        if html:
            return f"❌ <b>Erome upload failed</b>\n<code>{err}</code>"
        return f"❌ Erome upload failed: `{err}`"
    url = report.get("album_url") or ""
    title = report.get("title") or "Album"
    n = report.get("file_count") or 0
    vis = str(report.get("visibility") or "public")
    if vis == "private":
        if html:
            return (
                f"🔒 <b>Erome album staged private</b> — governance pass needed\n\n"
                f"<b>{title}</b> — {n} file(s)\n"
                f'<a href="{url}">{url}</a>\n'
                f"Fix title/tags on Erome, then mark approved in TBCC."
            )
        return (
            f"🔒 **Erome album staged private** — governance pass needed\n\n"
            f"**{title}** — {n} file(s)\n{url}\n"
            f"Fix title/tags on Erome, then mark approved in TBCC."
        )
    if html:
        return (
            f"✅ <b>Erome album published</b>\n\n"
            f"<b>{title}</b> — {n} file(s)\n"
            f'<a href="{url}">{url}</a>'
        )
    return f"✅ **Erome album published**\n\n**{title}** — {n} file(s)\n{url}"


def erome_topic_setup_hint() -> str:
    tid = erome_storage_topic_id()
    if tid:
        return f"Erome lane: topic id `{tid}` (TBCC_EROME_STORAGE_TOPIC_ID)."
    return (
        "Erome lane not configured. Use **Remote Upload Links** subtopic in Storage Hub, "
        "then set `TBCC_EROME_STORAGE_TOPIC_ID=<topic_id>` in tbcc/.env "
        "(run `py scripts/sync_storage_hub_map.py --list` for ids)."
    )
