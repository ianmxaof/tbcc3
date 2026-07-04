"""Async emoji-factory jobs (Celery) + post-split follow-up (dividers, sketchbook preset)."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.emoji_factory_job_status import (
    TERMINAL_STATUSES,
    job_dir_for,
    public_job_status,
    read_job_request,
    read_job_status,
    write_job_request,
    write_job_status,
)
from app.services.emoji_factory_jobs import (
    ALLOWED_SUFFIXES,
    MAX_UPLOAD_BYTES,
    emoji_factory_jobs_dir,
    run_create_from_upload,
    slug_short_name_base,
)
from app.services.emoji_pack_telethon import (
    _build_grid_preview_html,
    load_manifest,
    normalize_short_name,
    upload_custom_emoji_pack_from_manifest,
)
from app.services.telegram_admin import friendly_telegram_error, get_telegram_client, import_lock
from app.services.telegram_custom_emoji import validate_telethon_html
from app.services.telegram_custom_emoji_catalog import fetch_custom_emoji_pack

logger = logging.getLogger(__name__)


def _new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def enqueue_emoji_factory_job(
    *,
    uploaded_path: Path,
    original_filename: str,
    cols: int = 4,
    rows: int = 4,
    tile_px: int = 100,
    margin_pct: float = 8.0,
    loop_sec: float = 3.0,
    crf: int = 44,
    static: bool = False,
    title: str = "TBCC emoji pack",
    short_name: str = "",
    upload_telegram: bool = False,
    dry_run: bool = False,
    import_dividers: bool = False,
    save_sketchbook_preset: bool = False,
    source: str = "api",
) -> dict[str, Any]:
    suf = Path(original_filename).suffix.lower()
    if suf not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type {suf}. Use PNG/JPG/WebP or MP4/MOV/WebM/GIF.")
    size = uploaded_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large ({size // (1024 * 1024)} MB). Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    job_id = _new_job_id()
    job_dir = emoji_factory_jobs_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    staged = job_dir / f"upload{suf}"
    shutil.copy2(uploaded_path, staged)

    sn = (short_name or slug_short_name_base(original_filename)).strip()
    request = {
        "original_filename": original_filename,
        "cols": cols,
        "rows": rows,
        "tile_px": tile_px,
        "margin_pct": margin_pct,
        "loop_sec": loop_sec,
        "crf": crf,
        "static": static,
        "title": title,
        "short_name": sn,
        "upload_telegram": upload_telegram,
        "dry_run": dry_run,
        "import_dividers": import_dividers,
        "save_sketchbook_preset": save_sketchbook_preset,
        "source": source,
        "staged_path": str(staged),
    }
    write_job_request(job_dir, request)
    write_job_status(
        job_dir,
        job_id=job_id,
        status="queued",
        stage="queued",
        source=source,
    )

    from app.workers.emoji_factory_worker import process_emoji_factory_job

    async_result = process_emoji_factory_job.delay(job_id)
    write_job_status(job_dir, celery_task_id=async_result.id)
    body = public_job_status(job_id)
    body["queued"] = True
    return body


def execute_emoji_factory_job(job_id: str) -> dict[str, Any]:
    job_dir = job_dir_for(job_id)
    request = read_job_request(job_dir)
    if not request:
        write_job_status(job_dir, status="failed", stage="failed", error="missing request.json")
        return {"ok": False, "job_id": job_id, "error": "missing request.json"}

    staged = Path(str(request.get("staged_path") or ""))
    if not staged.is_file():
        write_job_status(job_dir, status="failed", stage="failed", error=f"staged upload missing: {staged}")
        return {"ok": False, "job_id": job_id, "error": "staged upload missing"}

    write_job_status(job_dir, status="running", stage="splitting")
    try:
        split = run_create_from_upload(
            uploaded_path=staged,
            original_filename=str(request.get("original_filename") or staged.name),
            cols=int(request.get("cols") or 4),
            rows=int(request.get("rows") or 4),
            tile_px=int(request.get("tile_px") or 100),
            margin_pct=float(request.get("margin_pct") or 8.0),
            loop_sec=float(request.get("loop_sec") or 3.0),
            crf=int(request.get("crf") or 44),
            static=bool(request.get("static")),
            job_dir=job_dir,
        )
    except Exception as e:
        logger.exception("emoji factory split failed job_id=%s", job_id)
        write_job_status(job_dir, status="failed", stage="failed", error=str(e)[:500])
        return {"ok": False, "job_id": job_id, "error": str(e)}

    upload_result: dict[str, Any] | None = None
    if request.get("upload_telegram"):
        write_job_status(job_dir, status="running", stage="uploading", split=split)
        try:
            import asyncio

            upload_result = asyncio.run(
                _upload_manifest_async(
                    manifest_path=Path(split["manifest_path"]),
                    title=str(request.get("title") or "TBCC emoji pack"),
                    short_name=str(request.get("short_name") or split.get("suggested_short_name") or ""),
                    dry_run=bool(request.get("dry_run")),
                )
            )
        except Exception as e:
            logger.exception("emoji factory upload failed job_id=%s", job_id)
            write_job_status(
                job_dir,
                status="failed",
                stage="upload_failed",
                split=split,
                error=friendly_telegram_error(e),
            )
            return {"ok": False, "job_id": job_id, "error": str(e), "split": split}

    followup: dict[str, Any] | None = None
    if request.get("import_dividers") or request.get("save_sketchbook_preset"):
        write_job_status(
            job_dir,
            status="running",
            stage="followup",
            split=split,
            upload=upload_result,
        )
        from app.database.session import SessionLocal

        db = SessionLocal()
        try:
            followup = run_emoji_factory_followup(
                db,
                job_id=job_id,
                import_dividers=bool(request.get("import_dividers")),
                save_sketchbook_preset=bool(request.get("save_sketchbook_preset")),
                title=str(request.get("title") or "TBCC emoji pack"),
                short_name=(upload_result or {}).get("short_name") or str(request.get("short_name") or ""),
            )
        finally:
            db.close()

    write_job_status(
        job_dir,
        status="done",
        stage="done",
        split=split,
        upload=upload_result,
        followup=followup,
    )
    return public_job_status(job_id)


async def _upload_manifest_async(
    *,
    manifest_path: Path,
    title: str,
    short_name: str,
    dry_run: bool,
) -> dict[str, Any]:
    load_manifest(manifest_path)
    async with import_lock():
        client = await get_telegram_client()
        me = await client.get_me()
        if me is None:
            raise RuntimeError("Telegram session not authorized")
        normalize_short_name(short_name, user_id=me.id)
        return await upload_custom_emoji_pack_from_manifest(
            client,
            manifest_path=manifest_path,
            title=title.strip() or "TBCC emoji pack",
            short_name=short_name.strip(),
            dry_run=dry_run,
        )


async def build_pack_sketchbook_html(*, short_name: str, title: str, cols: int, rows: int) -> str:
    async with import_lock():
        client = await get_telegram_client()
        pack = await fetch_custom_emoji_pack(client, short_name=short_name)
    emojis = pack.get("emojis") or []
    tags = [str(e.get("tag") or "") for e in emojis[: cols * rows]]
    tags = [t for t in tags if t]
    if not tags:
        raise RuntimeError(f"pack {short_name} has no emoji tags")
    return _build_grid_preview_html(title=title, short_name=short_name, tags=tags, cols=cols, rows=rows)


def run_emoji_factory_followup(
    db: Session,
    *,
    job_id: str,
    import_dividers: bool = False,
    save_sketchbook_preset: bool = False,
    title: str = "TBCC emoji pack",
    short_name: str = "",
    preset_title: str = "",
) -> dict[str, Any]:
    from app.models.custom_emoji_preset import CustomEmojiPreset
    from app.services.emoji_factory_divider_sources import import_emoji_factory_row_as_divider

    status = read_job_status(job_dir_for(job_id)) or {}
    split = status.get("split") if isinstance(status.get("split"), dict) else {}
    rows = int(split.get("rows") or 0)
    if rows < 1:
        manifest_path = Path(str(split.get("manifest_path") or ""))
        if manifest_path.is_file():
            manifest = load_manifest(manifest_path)
            rows = int(manifest.get("rows") or 0)
            cols = int(manifest.get("cols") or 4)
        else:
            cols = 4
    else:
        cols = int(split.get("cols") or 4)
        manifest_path = Path(str(split.get("manifest_path") or ""))
        if manifest_path.is_file():
            manifest = load_manifest(manifest_path)
            cols = int(manifest.get("cols") or cols)
        else:
            manifest = {"cols": cols, "rows": rows}

    out: dict[str, Any] = {"ok": True}
    imported_rows: list[dict[str, Any]] = []
    if import_dividers and rows > 0:
        for row in range(rows):
            try:
                imported_rows.append(import_emoji_factory_row_as_divider(db, job_id=job_id, row=row))
            except Exception as e:
                imported_rows.append({"ok": False, "row": row, "error": str(e)[:200]})
        out["imported_dividers"] = imported_rows

    if save_sketchbook_preset:
        sn = (short_name or "").strip()
        if not sn:
            out["sketchbook_preset"] = {"ok": False, "error": "short_name required (upload pack first)"}
        else:
            import asyncio

            try:
                html = asyncio.run(
                    build_pack_sketchbook_html(short_name=sn, title=title, cols=cols, rows=rows)
                )
                v = validate_telethon_html(html)
                if not v.get("ok"):
                    raise ValueError(v.get("error") or "invalid HTML")
                preset = CustomEmojiPreset(
                    title=(preset_title or title or f"Pack {sn}")[:256],
                    html_fragment=html,
                    source_note=f"emoji_factory_job:{job_id}",
                )
                db.add(preset)
                db.commit()
                db.refresh(preset)
                out["sketchbook_preset"] = {"ok": True, "id": preset.id, "title": preset.title}
            except Exception as e:
                out["sketchbook_preset"] = {"ok": False, "error": str(e)[:300]}

    return out


def is_terminal_job(job_id: str) -> bool:
    status = read_job_status(job_dir_for(job_id))
    if not status:
        return False
    return str(status.get("status") or "") in TERMINAL_STATUSES
