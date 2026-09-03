"""Upload one local lane media file into its Storage Hub forum topic."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.local_lane_hub_ledger import is_path_uploaded, is_uploaded, record_upload
from app.services.local_lane_hub_map import LaneWatchTarget, resolve_lane_for_path

logger = logging.getLogger(__name__)

_INCOMPLETE_SUFFIXES = (
    ".crdownload",
    ".part",
    ".tmp",
    ".temp",
    ".download",
    ".filepart",
)


def local_lane_hub_enabled() -> bool:
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_lane_hub_max_bytes() -> int:
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_MAX_BYTES") or "524288000").strip()
    try:
        return max(1024, int(raw))
    except ValueError:
        return 524288000


def local_lane_hub_skip_watermark() -> bool:
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_SKIP_WATERMARK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_lane_hub_signal_auto_pipe() -> bool:
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_SIGNAL_AUTO_PIPE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_lane_hub_direct_post() -> bool:
    """Post each file directly to Storage Hub (skip album Redis buffer). Default on for local firehose."""
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_DIRECT_POST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_lane_hub_batch_size() -> int:
    """Files uploaded per persistent Telethon session (amortizes connect/disconnect)."""
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_BATCH_SIZE") or "10").strip()
    try:
        return max(1, min(100, int(raw)))
    except ValueError:
        return 10


def local_lane_hub_batch_max_bytes() -> int:
    """Cap total raw bytes held in memory per batch (default 200MB)."""
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_BATCH_MAX_BYTES") or "209715200").strip()
    try:
        return max(1_048_576, int(raw))
    except ValueError:
        return 209715200


def local_lane_hub_log_path() -> Path | None:
    raw = (os.environ.get("TBCC_LOCAL_LANE_HUB_LOG") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    from app.data.operator_aof_paths import aof_network_root

    return (aof_network_root() / "Google Drive Daemon" / "local_lane_hub_log.jsonl").resolve()


def _looks_incomplete(path: Path) -> bool:
    n = path.name.lower()
    if any(n.endswith(suf) for suf in _INCOMPLETE_SUFFIXES):
        return True
    if ".!qb" in n:
        return True
    return False


def _should_skip_path(path: Path) -> str | None:
    name = path.name.lower()
    if name.endswith(".tbcc-meta.json"):
        return "sidecar"
    if _looks_incomplete(path):
        return "incomplete"
    from app.services.local_media_watermark import is_media_path

    if not is_media_path(path):
        return "non_media"
    return None


def _file_stable(path: Path, stable_wait_s: float) -> tuple[bool, str]:
    if stable_wait_s <= 0:
        return True, ""
    try:
        s1 = path.stat()
        time.sleep(stable_wait_s)
        s2 = path.stat()
        if s1.st_size != s2.st_size or int(s1.st_mtime) != int(s2.st_mtime):
            return False, "file still changing"
    except OSError as e:
        return False, str(e)
    return True, ""


def _append_log(record: dict[str, Any]) -> None:
    log_path = local_lane_hub_log_path()
    if not log_path:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            from app.services.aof_pipeline_counters import bump_hub

            bump_hub(
                str(record.get("action") or ""),
                error=str(record.get("error") or "") or None,
            )
        except Exception:
            pass
    except OSError as e:
        logger.warning("local lane hub log write failed: %s", e)


async def _do_upload(
    storage: Any,
    *,
    raw: bytes,
    media_type: str,
    target: LaneWatchTarget,
) -> dict[str, Any]:
    """Upload one file through an already-connected ``storage`` session."""
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
    from app.services.storage_hub_album_intake import (
        enqueue_storage_hub_media,
        storage_hub_album_intake_enabled,
    )
    from app.services.tbcc_caption_stamp import hub_intake_caption

    mt = "video" if (media_type or "").strip().lower() == "video" else "photo"
    cap = hub_intake_caption(target.network_key, "")
    skip_wm = local_lane_hub_skip_watermark()
    tid = int(target.message_thread_id)

    use_direct = local_lane_hub_direct_post() or not storage_hub_album_intake_enabled()
    if use_direct:
        result = await storage.post_bytes_to_channel(
            STORAGE_HUB_IDENT,
            [(raw, mt)],
            tid,
            caption=cap or None,
            send_silent=False,
            skip_watermark=skip_wm,
        )
    else:
        result = enqueue_storage_hub_media(raw=raw, media_type=mt, message_thread_id=tid)
        if isinstance(result, dict) and not result.get("buffered") and result.get("error"):
            result = await storage.post_bytes_to_channel(
                STORAGE_HUB_IDENT,
                [(raw, mt)],
                tid,
                caption=cap or None,
                send_silent=False,
                skip_watermark=skip_wm,
            )

    if isinstance(result, dict) and result.get("ok"):
        msg_ids = [int(x) for x in (result.get("message_ids") or []) if int(x) > 0]
        if msg_ids:
            try:
                from app.services.aof_library_forum_mirror import mirror_hub_message_to_library_topic

                result["library_mirror"] = await mirror_hub_message_to_library_topic(
                    storage,
                    source_message_id=msg_ids[0],
                    lane_key=target.network_key,
                )
            except Exception as e:
                logger.warning(
                    "local lane hub library mirror failed lane=%s msg=%s: %s",
                    target.network_key,
                    msg_ids[0],
                    e,
                )
                result["library_mirror"] = {"ok": False, "error": str(e)[:200]}
    return result


async def _upload_bytes_to_topic(
    *,
    raw: bytes,
    media_type: str,
    target: LaneWatchTarget,
) -> dict[str, Any]:
    """Single-file convenience wrapper — opens/closes its own Telethon session."""
    from app.services.telegram_admin import run_telegram_import_io

    async def _job(storage: Any):
        return await _do_upload(storage, raw=raw, media_type=media_type, target=target)

    return await run_telegram_import_io(_job)


async def _upload_pending_batch(pending: list[dict[str, Any]]) -> list[Any]:
    """Upload every pending item through ONE persistent Telethon session (I4 fix)."""
    from app.services.telegram_admin import run_telegram_import_io

    async def _job(storage: Any) -> list[Any]:
        out: list[Any] = []
        for item in pending:
            try:
                res = await _do_upload(storage, raw=item["raw"], media_type=item["media_type"], target=item["target"])
            except Exception as e:
                logger.warning("local lane hub batch item failed %s: %s", item["path"].name, e, exc_info=True)
                res = {"ok": False, "error": str(e)[:500]}
            out.append(res)
        return out

    return await run_telegram_import_io(_job)


def _prepare_deposit(
    path: Path,
    *,
    stable_wait_s: float,
    dry_run: bool,
    target: LaneWatchTarget | None,
) -> dict[str, Any]:
    """
    Local-disk-only prep for one file: stability check, dedupe, single read + hash.
    Returns either a resolved outcome (``resolved`` True, nothing left to do) or a
    pending upload job (``resolved`` False) carrying the bytes already read from disk.
    """
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "src": str(path),
    }

    def _done(ok: bool, msg: str) -> dict[str, Any]:
        return {"resolved": True, "ok": ok, "msg": msg, "record": record}

    if not path.is_file():
        return {"resolved": True, "ok": False, "msg": "not a file", "record": None}

    skip = _should_skip_path(path)
    if skip:
        record["action"] = "skip"
        record["reason"] = skip
        _append_log(record)
        return _done(False, skip)

    lane_target = target or resolve_lane_for_path(path)
    if not lane_target:
        record["action"] = "skip"
        record["reason"] = "unmapped_lane"
        _append_log(record)
        return _done(False, "unmapped lane folder")

    record["network_key"] = lane_target.network_key
    record["message_thread_id"] = lane_target.message_thread_id
    record["topic_title"] = lane_target.topic_title

    stable_ok, stable_msg = _file_stable(path, stable_wait_s)
    if not stable_ok:
        record["action"] = "skip"
        record["reason"] = stable_msg
        _append_log(record)
        return _done(False, stable_msg)

    try:
        stat = path.stat()
        size = stat.st_size
        mtime = float(stat.st_mtime)
    except OSError as e:
        record["action"] = "error"
        record["error"] = str(e)
        _append_log(record)
        return _done(False, str(e))

    if size <= 0:
        record["action"] = "skip"
        record["reason"] = "empty"
        _append_log(record)
        return _done(False, "empty file")

    max_bytes = local_lane_hub_max_bytes()
    if size > max_bytes:
        record["action"] = "skip"
        record["reason"] = "too_large"
        record["file_size"] = size
        record["max_bytes"] = max_bytes
        _append_log(record)
        return _done(False, f"file too large ({size} > {max_bytes})")

    record["file_size"] = size
    record["file_mtime"] = mtime

    # Path+mtime+size ledger skip — zero-read fast path (I5).
    if is_path_uploaded(path, file_size=size, file_mtime=mtime):
        record["action"] = "skip"
        record["reason"] = "already_uploaded"
        _append_log(record)
        return _done(False, "already uploaded")

    if dry_run:
        from app.services.local_media_watermark import media_type_hint

        record["action"] = "dry_run"
        record["media_type"] = media_type_hint(path)
        _append_log(record)
        return {"resolved": True, "ok": True, "msg": f"would upload -> topic {lane_target.message_thread_id}", "record": record}

    # Single read: hash the bytes we already have in memory (was a separate sha256
    # pass + a second path.read_bytes() — two full-file reads per upload).
    try:
        raw = path.read_bytes()
    except OSError as e:
        record["action"] = "error"
        record["error"] = str(e)
        _append_log(record)
        return _done(False, str(e))

    digest = hashlib.sha256(raw).hexdigest()
    record["content_sha256"] = digest

    if is_uploaded(digest):
        record["action"] = "skip"
        record["reason"] = "already_uploaded"
        record_upload(
            content_sha256=digest,
            network_key=lane_target.network_key,
            message_thread_id=lane_target.message_thread_id,
            source_path=path,
            file_size=size,
            file_mtime=mtime,
        )
        _append_log(record)
        return _done(False, "already uploaded")

    from app.services.local_media_watermark import media_type_hint

    mt = media_type_hint(path)
    return {
        "resolved": False,
        "path": path,
        "raw": raw,
        "media_type": mt,
        "target": lane_target,
        "digest": digest,
        "size": size,
        "mtime": mtime,
        "record": record,
    }


def _finalize_upload_result(item: dict[str, Any], result: Any) -> tuple[bool, str, dict[str, Any] | None]:
    record = item["record"]
    lane_target: LaneWatchTarget = item["target"]

    ok = False
    if isinstance(result, dict):
        ok = bool(result.get("ok")) or bool(result.get("buffered"))
    record["action"] = "upload" if ok else "error"
    record["result"] = result if isinstance(result, dict) else {"raw": str(result)}

    if ok:
        record_upload(
            content_sha256=item["digest"],
            network_key=lane_target.network_key,
            message_thread_id=lane_target.message_thread_id,
            source_path=item["path"],
            file_size=item["size"],
            file_mtime=item["mtime"],
        )
        if local_lane_hub_signal_auto_pipe():
            try:
                from app.services.storage_auto_pipe import signal_lane_auto_pipe

                pipe = signal_lane_auto_pipe(lane_target.network_key, lane_target.message_thread_id)
                record["auto_pipe"] = pipe
            except Exception:
                logger.debug("local lane hub auto-pipe signal failed", exc_info=True)
        _append_log(record)
        return True, f"uploaded -> {lane_target.topic_title}", record

    record["error"] = (result or {}).get("error") if isinstance(result, dict) else "upload failed"
    _append_log(record)
    return False, str(record.get("error") or "upload failed"), record


def deposit_local_file(
    path: Path,
    *,
    stable_wait_s: float = 2.0,
    dry_run: bool = False,
    target: LaneWatchTarget | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Upload ``path`` to the Storage Hub topic for its lane folder.
    Returns (ok, message, record). Opens/closes its own Telethon session — prefer
    ``deposit_local_files_batch`` when uploading more than one file in a pass.
    """
    item = _prepare_deposit(path, stable_wait_s=stable_wait_s, dry_run=dry_run, target=target)
    if item["resolved"]:
        return item["ok"], item["msg"], item["record"]

    try:
        result = asyncio.run(
            _upload_bytes_to_topic(raw=item["raw"], media_type=item["media_type"], target=item["target"])
        )
    except Exception as e:
        logger.warning("local lane hub upload failed %s: %s", path.name, e, exc_info=True)
        record = item["record"]
        record["action"] = "error"
        record["error"] = str(e)[:500]
        _append_log(record)
        return False, str(e), record

    return _finalize_upload_result(item, result)


def deposit_local_files_batch(
    paths: list[Path],
    *,
    stable_wait_s: float = 2.0,
    dry_run: bool = False,
    target: LaneWatchTarget | None = None,
) -> list[tuple[bool, str, dict[str, Any] | None]]:
    """
    Upload many files under ONE persistent Telethon session (I4/I1 fix).
    Local prep (stability, dedupe, read+hash) still runs per file, but the
    Telegram connect/disconnect happens once for the whole batch instead of
    once per file. Order of results matches ``paths``.
    """
    items = [_prepare_deposit(p, stable_wait_s=stable_wait_s, dry_run=dry_run, target=target) for p in paths]
    results: list[tuple[bool, str, dict[str, Any] | None] | None] = [None] * len(items)

    pending_idx = [i for i, it in enumerate(items) if not it["resolved"]]
    for i, it in enumerate(items):
        if it["resolved"]:
            results[i] = (it["ok"], it["msg"], it["record"])

    if pending_idx:
        pending_items = [items[i] for i in pending_idx]
        try:
            upload_results = asyncio.run(_upload_pending_batch(pending_items))
        except Exception as e:
            logger.warning("local lane hub batch upload failed: %s", e, exc_info=True)
            for i in pending_idx:
                record = items[i]["record"]
                record["action"] = "error"
                record["error"] = str(e)[:500]
                _append_log(record)
                results[i] = (False, str(e), record)
        else:
            for i, upload_result in zip(pending_idx, upload_results):
                results[i] = _finalize_upload_result(items[i], upload_result)

    return results  # type: ignore[return-value]


def _chunk_paths_for_batch(paths: list[Path]) -> list[list[Path]]:
    """Group files into Telethon-session-sized batches, capped by count and total bytes."""
    max_count = local_lane_hub_batch_size()
    max_bytes = local_lane_hub_batch_max_bytes()
    chunks: list[list[Path]] = []
    current: list[Path] = []
    current_bytes = 0
    for p in paths:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        if current and (len(current) >= max_count or current_bytes + size > max_bytes):
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(p)
        current_bytes += size
    if current:
        chunks.append(current)
    return chunks


def scan_lane_folders_once(
    *,
    stable_wait_s: float = 2.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan all watched lane folders for media not yet in the ledger."""
    from app.services.local_lane_hub_map import lane_watch_targets

    uploaded = 0
    skipped = 0
    errors = 0
    details: list[dict[str, Any]] = []

    targets = lane_watch_targets()
    targets = sorted(targets, key=lambda t: (0 if t.network_key == "inbox" else 1, t.network_key))

    for target in targets:
        folder = target.folder_path
        if not folder.is_dir():
            continue
        entries = [e for e in sorted(folder.rglob("*")) if e.is_file()]
        for chunk in _chunk_paths_for_batch(entries):
            chunk_results = deposit_local_files_batch(
                chunk,
                stable_wait_s=stable_wait_s,
                dry_run=dry_run,
                target=target,
            )
            for entry, (ok, msg, rec) in zip(chunk, chunk_results):
                if not rec:
                    continue
                details.append(rec)
                if ok:
                    uploaded += 1
                    logger.info("%s: %s", entry.name, msg)
                elif rec.get("reason") in ("already_uploaded", "sidecar", "non_media", "incomplete"):
                    skipped += 1
                else:
                    if rec.get("action") == "error":
                        errors += 1
                    else:
                        skipped += 1

    return {
        "ok": errors == 0,
        "uploaded": uploaded,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "lanes": [t.network_key for t in lane_watch_targets()],
    }
