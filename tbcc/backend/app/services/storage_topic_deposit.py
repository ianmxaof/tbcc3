"""Queue Storage Hub forum-topic → AOF pool imports (newest-first, deduped)."""

from __future__ import annotations

import asyncio
import html as html_module
import logging
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import network_channel_by_key
from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    STORAGE_HUB_IDENT,
    network_key_for_storage_topic,
    storage_map_by_key,
    topic_deep_link,
)
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.services.aof_growth_hub import _ensure_channel_row, _ensure_pool_row, storage_pool_seed_batch_size

logger = logging.getLogger(__name__)

_DEPOSIT_CMD = re.compile(
    r"^/deposit(?:@\w+)?(?:\s+(\d+))?(?:\s+(both|photos|videos))?\s*$",
    re.I,
)


def parse_deposit_command(text: str | None) -> tuple[int | None, str | None] | None:
    """
    Parse /deposit, /deposit 15, /deposit 15 videos.
    Returns (limit_or_none, media_types_or_none) or None if not a deposit command.
    """
    raw = (text or "").strip()
    if not raw.lower().startswith("/deposit"):
        return None
    m = _DEPOSIT_CMD.match(raw.split("\n", 1)[0].strip())
    if not m:
        return None
    limit: int | None = None
    if m.group(1):
        try:
            limit = min(max(int(m.group(1)), 1), 200)
        except ValueError:
            limit = storage_pool_seed_batch_size()
    media = (m.group(2) or "").strip().lower() or None
    if media and media not in ("both", "photos", "videos"):
        media = None
    return limit, media


def default_deposit_media_types() -> str:
    raw = (os.getenv("TBCC_STORAGE_DEPOSIT_MEDIA_TYPES") or "videos").strip().lower()
    if raw in ("both", "photos", "videos"):
        return raw
    return "videos"


def storage_deposit_index_only_enabled() -> bool:
    """Index Storage Hub messages into pools without downloading full video bytes (lazy fetch on preview)."""
    return (os.getenv("TBCC_STORAGE_DEPOSIT_INDEX_ONLY") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_deposit_limit(limit: int | None) -> int:
    if limit is None:
        return storage_pool_seed_batch_size()
    return min(max(int(limit), 1), 200)


def _deposit_job_id(report: dict[str, Any]) -> str:
    return str(report.get("job_id") or report.get("id") or "?")


def _esc(text: str | None, *, html: bool) -> str:
    raw = str(text or "?")
    return html_module.escape(raw) if html else raw


def _lbl(text: str, *, html: bool, markdown: bool) -> str:
    if html:
        return f"<b>{html_module.escape(text)}</b>"
    if markdown:
        return f"**{text}**"
    return text


def _mono(text: str, *, html: bool, markdown: bool) -> str:
    if html:
        return f"<code>{html_module.escape(text)}</code>"
    if markdown:
        return f"`{text}`"
    return text


def format_deposit_progress_text(
    report: dict[str, Any],
    *,
    html: bool = False,
    markdown: bool | None = None,
) -> str:
    """Immediate in-topic ack while Celery imports media."""
    if markdown is None:
        markdown = not html
    pool = _esc(report.get("pool_name"), html=html)
    topic = _esc(report.get("topic_title"), html=html)
    lim = report.get("limit")
    mt = _esc(report.get("media_types") or "videos", html=html)
    job_id = _esc(_deposit_job_id(report), html=html)
    if html:
        return (
            "📥 <b>Uploading media…</b>\n\n"
            f"<b>Topic:</b> {topic}\n"
            f"<b>Pool:</b> {pool}\n"
            f"<b>Target:</b> up to {lim} new <code>{mt}</code>\n"
            f"<b>Job:</b> <code>{job_id}</code>\n\n"
            "This message updates when import finishes (or if the worker is offline)."
        )
    return (
        f"📥 {_lbl('Uploading media…', html=False, markdown=markdown)}\n\n"
        f"{_lbl('Topic', html=False, markdown=markdown)}: {topic}\n"
        f"{_lbl('Pool', html=False, markdown=markdown)}: {pool}\n"
        f"{_lbl('Target', html=False, markdown=markdown)}: up to {lim} new {_mono(mt, html=False, markdown=markdown)}\n"
        f"{_lbl('Job', html=False, markdown=markdown)}: {_mono(_deposit_job_id(report), html=False, markdown=markdown)}\n\n"
        "This message updates when import finishes (or if the worker is offline)."
    )


def format_deposit_success_text(
    report: dict[str, Any],
    *,
    html: bool = False,
    markdown: bool | None = None,
) -> str:
    """Human reply for queued storage deposit (import still running)."""
    if markdown is None:
        markdown = not html
    pool = report.get("pool_name") or "?"
    topic = report.get("topic_title") or "?"
    lim = report.get("limit")
    mt = report.get("media_types") or "videos"
    job_id = _deposit_job_id(report)
    if html:
        return (
            "📥 <b>Storage deposit queued</b>\n\n"
            f"<b>Topic:</b> {topic}\n"
            f"<b>Pool:</b> {pool}\n"
            f"<b>Count:</b> {lim} new <code>{mt}</code> (newest-first, deduped)\n"
            f"<b>Job:</b> <code>{job_id}</code>\n\n"
            "CLIP auto-approve runs when tags land (if enabled)."
        )
    return (
        f"📥 {_lbl('Storage deposit queued', html=False, markdown=markdown)}\n\n"
        f"{_lbl('Topic', html=False, markdown=markdown)}: {topic}\n"
        f"{_lbl('Pool', html=False, markdown=markdown)}: {pool}\n"
        f"{_lbl('Count', html=False, markdown=markdown)}: {lim} new {_mono(mt, html=False, markdown=markdown)} (newest-first, deduped)\n"
        f"{_lbl('Job', html=False, markdown=markdown)}: {_mono(job_id, html=False, markdown=markdown)}\n\n"
        "CLIP auto-approve runs when tags land (if enabled)."
    )


def format_deposit_complete_text(
    report: dict[str, Any],
    job_body: dict[str, Any] | None,
    *,
    html: bool = False,
    markdown: bool | None = None,
) -> str:
    """Reply after the import job finishes — includes duplicate warnings."""
    if markdown is None:
        markdown = not html
    pool = report.get("pool_name") or "?"
    topic = report.get("topic_title") or "?"
    lim = report.get("limit")
    mt = report.get("media_types") or "videos"
    job_id = _deposit_job_id(report)

    if not job_body:
        tail = (
            "Import did not finish in time — check TBCC Celery worker (telegram queue) "
            f"or poll <code>/import/jobs/{_esc(job_id, html=html)}</code>."
            if html
            else (
                f"Import did not finish in time — check TBCC Celery worker (telegram queue) "
                f"or poll job {_mono(job_id, html=False, markdown=markdown)}."
            )
        )
        base = format_deposit_success_text(report, html=html, markdown=markdown)
        return f"{base}\n\n{tail}"

    status = str(job_body.get("status") or "").strip().lower()
    if status == "failed":
        err = job_body.get("error") or "unknown"
        if html:
            return (
                "❌ <b>Storage deposit failed</b>\n\n"
                f"<b>Topic:</b> {topic}\n"
                f"<b>Pool:</b> {pool}\n"
                f"<b>Job:</b> <code>{job_id}</code>\n"
                f"<b>Error:</b> {err}"
            )
        return (
            f"❌ {_lbl('Storage deposit failed', html=False, markdown=markdown)}\n\n"
            f"{_lbl('Topic', html=False, markdown=markdown)}: {topic}\n"
            f"{_lbl('Pool', html=False, markdown=markdown)}: {pool}\n"
            f"{_lbl('Job', html=False, markdown=markdown)}: {_mono(job_id, html=False, markdown=markdown)}\n"
            f"{_lbl('Error', html=False, markdown=markdown)}: {err}"
        )

    result = job_body.get("result") if isinstance(job_body.get("result"), dict) else {}
    stored = int(result.get("stored") or 0)
    skipped_dup = int(result.get("skipped_duplicate") or 0)
    target = int(result.get("target_stored") or lim or 0)
    scanned = int(result.get("messages_scanned") or 0)

    if stored == 0 and skipped_dup > 0:
        outcome = (
            "⚠️ <b>All scanned media is already in this pool.</b> Upload newer content, then run /deposit again."
            if html
            else (
                f"⚠️ {_lbl('All scanned media is already in this pool.', html=False, markdown=markdown)} "
                "Upload newer content, then run /deposit again."
            )
        )
    elif stored == 0:
        outcome = (
            "⚠️ <b>No new media imported.</b> Nothing with photo/video was found in the newest messages."
            if html
            else (
                f"⚠️ {_lbl('No new media imported.', html=False, markdown=markdown)} "
                "Nothing with photo/video was found in the newest messages."
            )
        )
    elif stored < target and skipped_dup > 0:
        outcome = (
            f"Imported <b>{stored}</b> of {target} requested ({skipped_dup} duplicate(s) skipped)."
            if html
            else f"Imported {_lbl(str(stored), html=False, markdown=markdown)} of {target} requested ({skipped_dup} duplicate(s) skipped)."
        )
    else:
        outcome = (
            f"Imported <b>{stored}</b> new item(s) into Media Library (pending)."
            if html
            else f"Imported {_lbl(str(stored), html=False, markdown=markdown)} new item(s) into Media Library (pending)."
        )

    mirror = report.get("topic_mirror")
    mirror_line = ""
    if isinstance(mirror, dict) and not mirror.get("skipped"):
        mirror_line = "\n\nMain group mirror runs after pool import (silent albums)."

    clip = (
        "\nApproved items are ready for schedulers (Storage Hub auto-approve)."
        if stored > 0
        else ""
    )

    cache_line = ""
    cache_body = result.get("sent_cache") if isinstance(result.get("sent_cache"), dict) else None
    if cache_body and int(cache_body.get("moved") or 0) > 0:
        cap = cache_body.get("caption") or "✅"
        cache_line = f"\n\nMoved {cache_body.get('moved')} item(s) to SENT CACHE ({cap})."
    composer_body = result.get("cache_composer") if isinstance(result.get("cache_composer"), dict) else None
    composer_line = ""
    if composer_body and int(composer_body.get("albums_built") or 0) > 0:
        composer_line = (
            f"\n\n📦 Cache composer: {composer_body.get('albums_built')} album(s) "
            f"× {composer_body.get('album_size', 5)} — check topic for Erome links."
        )

    headline = "Media finished uploading" if stored > 0 else "Storage deposit complete"
    if html:
        return (
            f"{'✅' if stored > 0 else '📥'} <b>{headline}</b>\n\n"
            f"<b>Topic:</b> {topic}\n"
            f"<b>Pool:</b> {pool}\n"
            f"<b>Media:</b> <code>{mt}</code> · scanned {scanned}\n"
            f"<b>Job:</b> <code>{job_id}</code>\n\n"
            f"{outcome}{mirror_line}{cache_line}{composer_line}{clip}"
        )
    return (
        f"{'✅' if stored > 0 else '📥'} {_lbl(headline, html=False, markdown=markdown)}\n\n"
        f"{_lbl('Topic', html=False, markdown=markdown)}: {topic}\n"
        f"{_lbl('Pool', html=False, markdown=markdown)}: {pool}\n"
        f"{_lbl('Media', html=False, markdown=markdown)}: {_mono(mt, html=False, markdown=markdown)} · scanned {scanned}\n"
        f"{_lbl('Job', html=False, markdown=markdown)}: {_mono(job_id, html=False, markdown=markdown)}\n\n"
        f"{outcome}{mirror_line}{cache_line}{composer_line}{clip}"
    )


async def await_deposit_import_job(
    job_id: str,
    *,
    limit: int | None = None,
    media_types: str | None = None,
    index_only: bool = False,
    sent_cache: bool = False,
    timeout_s: float | None = None,
    poll_s: float = 2.0,
    on_wait: Callable[[float, str], Awaitable[None]] | None = None,
) -> dict[str, Any] | None:
    """Poll until a channel import job reaches a terminal state (or timeout)."""
    from app.database.session import SessionLocal
    from app.models.import_job import ImportJob
    from app.services.channel_import_runner import channel_import_timeout_s
    from app.services.import_pipeline import TERMINAL_STATUSES, job_to_public_dict

    if not job_id or job_id == "?":
        return None
    if timeout_s is None:
        timeout_s = float(
            channel_import_timeout_s(
                int(limit or 50),
                media_types=media_types,
                index_only=index_only,
                sent_cache=sent_cache,
            )
        )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(30.0, timeout_s)
    queued_since: float | None = None
    last_heartbeat = loop.time()
    while loop.time() < deadline:
        db = SessionLocal()
        stage = "unknown"
        try:
            job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
            if job and job.status in TERMINAL_STATUSES:
                return job_to_public_dict(job)
            if job and job.status == "queued":
                if queued_since is None:
                    queued_since = loop.time()
                elif loop.time() - queued_since >= 90.0:
                    return {
                        "job_id": job_id,
                        "status": "failed",
                        "error": (
                            "import_never_started — TBCC Celery worker may be offline "
                            "(telegram queue). Restart TBCC worker and retry /deposit."
                        ),
                    }
            else:
                queued_since = None
            if job:
                stage = (job.stage or job.status or "unknown").strip()
        finally:
            db.close()

        if on_wait and loop.time() - last_heartbeat >= 30.0:
            last_heartbeat = loop.time()
            try:
                await on_wait(loop.time(), str(stage))
            except Exception:
                logger.debug("deposit heartbeat callback failed", exc_info=True)

        await asyncio.sleep(poll_s)

    return None


def deposit_mirror_countdown_s(limit: int) -> int:
    """Defer main-group mirror until pool import finishes and SQLite sessions unlock."""
    lim = max(1, int(limit))
    return max(120, min(lim * 8, 300))


def _mirror_task_ids(report: dict[str, Any]) -> list[str]:
    mirror = report.get("topic_mirror")
    if not isinstance(mirror, dict):
        return []
    out: list[str] = []
    for row in mirror.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "") != "queued":
            continue
        task_id = row.get("task_id")
        if task_id:
            out.append(str(task_id))
    return out


async def await_celery_task_async(
    task_id: str,
    *,
    timeout_s: float = 900,
    poll_s: float = 2.0,
) -> dict[str, Any] | None:
    if not task_id:
        return None
    from app.workers.celery_app import celery

    deadline = asyncio.get_running_loop().time() + max(30.0, timeout_s)
    result = celery.AsyncResult(task_id)
    while asyncio.get_running_loop().time() < deadline:
        if result.ready():
            try:
                payload = result.result
                if isinstance(payload, dict):
                    return payload
                return {"ok": True, "result": payload}
            except Exception as e:
                return {"ok": False, "error": str(e)[:300]}
        await asyncio.sleep(poll_s)
    return None


def _format_mirror_finished_line(mirror_body: dict[str, Any] | None, *, html: bool) -> str:
    if not mirror_body or mirror_body.get("skipped"):
        return ""
    if not mirror_body.get("ok", True):
        err = mirror_body.get("error") or "mirror failed"
        return f"\n\n⚠️ Main group mirror failed: {err}"
    forwarded = int(mirror_body.get("forwarded") or 0)
    uploaded = int(mirror_body.get("uploaded") or 0)
    total = forwarded + uploaded
    if total <= 0:
        return "\n\nMain group mirror finished (nothing new to forward)."
    albums = int(mirror_body.get("albums_sent") or 0)
    album_note = f", {albums} silent album(s)" if albums else ", silent"
    return f"\n\n✅ Main group mirror complete — {total} item(s){album_note}."


async def run_deposit_subtopic_followup(
    report: dict[str, Any],
    *,
    job_id: str,
    limit: int,
    html: bool,
    markdown: bool | None = None,
    set_message_text: Callable[[str], Awaitable[None]],
    wait_for_mirror: bool = True,
) -> None:
    """Poll import (+ optional mirror) and edit the in-topic progress message."""
    if markdown is None:
        markdown = not html
    started = asyncio.get_running_loop().time()
    index_only = bool(report.get("index_only"))

    async def _heartbeat(_now: float, stage: str) -> None:
        elapsed = int(_now - started)
        mins = max(1, elapsed // 60)
        topic = _esc(report.get("topic_title"), html=html)
        pool = _esc(report.get("pool_name"), html=html)
        if html:
            text = (
                f"📥 <b>Still importing…</b> ({mins}m)\n\n"
                f"<b>Topic:</b> {topic}\n"
                f"<b>Pool:</b> {pool}\n"
                f"<b>Stage:</b> <code>{html_module.escape(stage)}</code>"
            )
        else:
            text = (
                f"📥 {_lbl('Still importing…', html=False, markdown=markdown)} ({mins}m)\n\n"
                f"{_lbl('Topic', html=False, markdown=markdown)}: {topic}\n"
                f"{_lbl('Pool', html=False, markdown=markdown)}: {pool}\n"
                f"{_lbl('Stage', html=False, markdown=markdown)}: {_mono(stage, html=False, markdown=markdown)}"
            )
        await set_message_text(text)

    try:
        job_body = await await_deposit_import_job(
            job_id,
            limit=limit,
            media_types=str(report.get("media_types") or ""),
            index_only=index_only,
            sent_cache=bool(report.get("sent_cache")),
            on_wait=_heartbeat,
        )
        text = format_deposit_complete_text(report, job_body, html=html, markdown=markdown)
        result = job_body.get("result") if isinstance(job_body, dict) else None
        stored = int((result or {}).get("stored") or 0) if isinstance(result, dict) else 0

        mirror_ids = _mirror_task_ids(report) if wait_for_mirror and stored > 0 else []
        if mirror_ids:
            text = f"{text}\n\n⏳ Mirroring to main group (silent albums)…"
            await set_message_text(text)

            mirror_delay = 0
            mirror_meta = report.get("topic_mirror")
            if isinstance(mirror_meta, dict):
                try:
                    mirror_delay = int(mirror_meta.get("mirror_delay_s") or 0)
                except (TypeError, ValueError):
                    mirror_delay = 0
            mirror_timeout = max(1200.0, float(mirror_delay) + 900.0)

            mirror_body: dict[str, Any] | None = None
            for task_id in mirror_ids:
                mirror_body = await await_celery_task_async(task_id, timeout_s=mirror_timeout)
            text = (
                f"{format_deposit_complete_text(report, job_body, html=html, markdown=markdown)}"
                f"{_format_mirror_finished_line(mirror_body, html=html)}"
            )

        await set_message_text(text)
    except Exception as e:
        logger.warning("deposit subtopic followup failed job=%s: %s", job_id, e, exc_info=True)
        err = str(e)[:200]
        fail = (
            f"❌ <b>Deposit follow-up failed</b>\n\n<code>{err}</code>"
            if html
            else f"❌ {_lbl('Deposit follow-up failed', html=False, markdown=markdown)}\n\n{_mono(err, html=False, markdown=markdown)}"
        )
        try:
            await set_message_text(fail)
        except Exception:
            logger.debug("deposit followup could not edit progress message", exc_info=True)


def format_deposit_error_text(report: dict[str, Any]) -> str:
    err = report.get("error", "unknown")
    return (
        f"❌ Deposit failed (`{err}`).\n"
        "Unmapped topic? Check `aof_storage_hub_map.py` or run `sync_storage_hub_map.py --list`."
    )


def storage_hub_chat_id_int() -> int:
    return int(STORAGE_HUB_IDENT)


def forum_message_thread_id_from_telethon(message) -> int | None:
    """Bot API message_thread_id from a Telethon Message in a forum supergroup."""
    top = getattr(message, "reply_to_top_id", None)
    if top:
        return int(top)
    r = getattr(message, "reply_to", None)
    if not r:
        return None
    top = getattr(r, "reply_to_top_id", None)
    if top:
        return int(top)
    if getattr(r, "forum_topic", False):
        mid = getattr(r, "reply_to_msg_id", None)
        if mid:
            return int(mid)
    return None


def resolve_storage_topic_row(message_thread_id: int, topic_title: str = ""):
    """Return StorageTopicMap row for thread id, or fuzzy title match."""
    tid = int(message_thread_id)
    for row in AOF_STORAGE_TOPIC_MAP:
        if int(row.message_thread_id) == tid:
            return row
    key = network_key_for_storage_topic(tid, topic_title)
    if not key:
        return None
    return storage_map_by_key().get(key)


def queue_storage_topic_deposit(
    db: Session,
    *,
    message_thread_id: int,
    limit: int | None = None,
    topic_title: str = "",
    media_types: str | None = None,
    include_topic_mirror: bool = True,
    apply_watermark: bool = False,
    commit: bool = True,
    countdown: int = 0,
    message_ids: list[int] | None = None,
) -> dict[str, Any]:
    """
    Import up to `limit` NEW deduped items from one Storage Hub forum topic into its pool.
    Scans newest-first (same rules as import/from-channel).
    """
    from app.services.import_pipeline import (
        create_channel_import_job,
        enqueue_channel_import_job,
        job_to_public_dict,
        update_job,
    )

    tid = int(message_thread_id)
    row = resolve_storage_topic_row(tid, topic_title)
    if not row or not row.network_key:
        return {
            "ok": False,
            "error": "unmapped_topic",
            "message_thread_id": tid,
            "hint": "Add topic to app/data/aof_storage_hub_map.py or rename to match AOF STORAGE pattern.",
        }

    net = network_channel_by_key(row.network_key)
    if not net:
        return {
            "ok": False,
            "error": "network_channel_missing",
            "network_key": row.network_key,
            "message_thread_id": tid,
        }

    ch = db.query(Channel).filter(Channel.identifier == net.identifier).first()
    if not ch:
        ch = _ensure_channel_row(db, net)
    if not ch:
        return {
            "ok": False,
            "error": "channel_row_missing",
            "network_key": row.network_key,
            "receive_channel": net.identifier,
        }

    pool = db.query(ContentPool).filter(ContentPool.name == net.pool_name).first()
    if not pool:
        pool = _ensure_pool_row(db, net, int(ch.id))
        db.flush()
    if not pool:
        return {
            "ok": False,
            "error": "pool_missing",
            "pool_name": net.pool_name,
            "network_key": row.network_key,
        }

    mt = (media_types or default_deposit_media_types()).strip().lower()
    if mt not in ("both", "photos", "videos"):
        mt = "videos"
    lim = resolve_deposit_limit(limit)
    if message_ids:
        lim = min(max(len([int(x) for x in message_ids if int(x) > 0]), 1), 200)
    source = f"telegram:{STORAGE_HUB_IDENT}#topic:{tid}"
    index_only = storage_deposit_index_only_enabled() and not apply_watermark
    from app.services.storage_sent_cache import storage_sent_cache_enabled

    sent_cache = storage_sent_cache_enabled() and bool(row.network_key)

    job = create_channel_import_job(
        db,
        channel=STORAGE_HUB_IDENT,
        pool_id=int(pool.id),
        limit=lim,
        media_types=mt,
        message_thread_id=tid,
        source_label=source,
        topic_title=row.topic_title or topic_title or None,
        apply_watermark=apply_watermark,
        index_only=index_only,
        network_key=row.network_key,
        sent_cache=sent_cache,
        message_ids=message_ids,
    )

    mirror_limit = int(lim)
    mirror_report: dict[str, Any] | None = None
    task_id: str | None = None
    mirror_task_id: str | None = None

    if include_topic_mirror:
        try:
            from app.data.aof_main_group_topic_map import main_topic_for_network_key
            from app.services.aof_topic_mirror import deposit_topic_mirror_enabled, topic_mirror_enabled
            from app.services.import_pipeline import enqueue_deposit_import_with_mirror

            mirror_on = deposit_topic_mirror_enabled()
            main_row = main_topic_for_network_key(row.network_key) if mirror_on else None
            if main_row:
                from app.services.import_pipeline import (
                    enqueue_channel_import_job,
                    enqueue_deposit_mirror_after_import,
                )

                task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))
                mirror_task_id = enqueue_deposit_mirror_after_import(
                    job.id,
                    tid,
                    int(main_row.message_thread_id),
                    mirror_limit=mirror_limit,
                    media_types=mt,
                    delay_s=deposit_mirror_countdown_s(lim),
                )
                mirror_report = {
                    "ok": True,
                    "chained": False,
                    "deferred": True,
                    "limit_per_pair": mirror_limit,
                    "mirror_delay_s": deposit_mirror_countdown_s(lim),
                    "jobs": [
                        {
                            "network_key": row.network_key,
                            "storage_topic": row.topic_title,
                            "storage_thread_id": tid,
                            "main_topic": main_row.topic_title,
                            "main_thread_id": main_row.message_thread_id,
                            "task_id": mirror_task_id,
                            "import_task_id": task_id,
                            "import_job_id": job.id,
                            "status": "queued",
                        }
                    ],
                }
            elif mirror_on:
                task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))
                mirror_report = {
                    "ok": True,
                    "skipped": True,
                    "reason": "no_main_topic",
                    "network_key": row.network_key,
                }
            else:
                task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))
                mirror_report = {
                    "ok": True,
                    "skipped": True,
                    "reason": "deposit_mirror_disabled",
                    "network_key": row.network_key,
                }
        except Exception as e:
            mirror_report = {"ok": False, "error": str(e)[:200]}
            task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))
    else:
        task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))

    if task_id or mirror_task_id:
        update_job(db, job, celery_task_id=task_id or mirror_task_id)

    if commit:
        db.commit()

    body = job_to_public_dict(job)
    body.update(
        {
            "ok": True,
            "network_key": row.network_key,
            "pool_name": net.pool_name,
            "pool_id": int(pool.id),
            "topic_title": row.topic_title,
            "message_thread_id": tid,
            "topic_deep_link": topic_deep_link(tid),
            "receive_channel": net.identifier,
            "limit": lim,
            "media_types": mt,
            "index_only": index_only,
            "sent_cache": sent_cache,
            "staged": bool(message_ids),
            "topic_mirror": mirror_report,
        }
    )
    return body


def queue_storage_topic_deposit_staged(
    db: Session,
    *,
    message_thread_id: int,
    message_ids: list[int],
    topic_title: str = "",
    media_types: str | None = None,
    include_topic_mirror: bool = True,
    apply_watermark: bool = False,
    commit: bool = True,
    countdown: int = 0,
) -> dict[str, Any]:
    """Deposit explicit in-topic message ids (Album Composer staged workshop items)."""
    ids = [int(x) for x in message_ids if int(x) > 0][:200]
    if not ids:
        return {"ok": False, "error": "no_message_ids", "message_thread_id": int(message_thread_id)}
    return queue_storage_topic_deposit(
        db,
        message_thread_id=message_thread_id,
        limit=len(ids),
        topic_title=topic_title,
        media_types=media_types,
        include_topic_mirror=include_topic_mirror,
        apply_watermark=apply_watermark,
        commit=commit,
        countdown=countdown,
        message_ids=ids,
    )


def queue_inbox_channel_deposit(
    db: Session,
    *,
    limit: int | None = None,
    media_types: str | None = None,
    commit: bool = True,
    countdown: int = 0,
) -> dict[str, Any]:
    """Import newest media from AOF INBOX #CHANNEL shortcut into inbox pool."""
    from app.data.aof_network import network_channel_by_key
    from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT
    from app.services.import_pipeline import (
        create_channel_import_job,
        enqueue_channel_import_job,
        job_to_public_dict,
        update_job,
    )

    net = network_channel_by_key("inbox")
    if not net:
        return {"ok": False, "error": "network_channel_missing", "network_key": "inbox"}

    ch = db.query(Channel).filter(Channel.identifier == net.identifier).first()
    if not ch:
        ch = _ensure_channel_row(db, net)
    if not ch:
        return {
            "ok": False,
            "error": "channel_row_missing",
            "network_key": "inbox",
            "receive_channel": net.identifier,
        }

    pool = db.query(ContentPool).filter(ContentPool.name == net.pool_name).first()
    if not pool:
        pool = _ensure_pool_row(db, net, int(ch.id))
        db.flush()
    if not pool:
        return {"ok": False, "error": "pool_missing", "pool_name": net.pool_name}

    mt = (media_types or default_deposit_media_types()).strip().lower()
    if mt not in ("both", "photos", "videos"):
        mt = "videos"
    lim = resolve_deposit_limit(limit)
    source = f"telegram:{INBOX_CHANNEL_IDENT}"
    index_only = storage_deposit_index_only_enabled()

    job = create_channel_import_job(
        db,
        channel=INBOX_CHANNEL_IDENT,
        pool_id=int(pool.id),
        limit=lim,
        media_types=mt,
        message_thread_id=None,
        source_label=source,
        topic_title="AOF INBOX #CHANNEL",
        apply_watermark=False,
        index_only=index_only,
        network_key="inbox",
        sent_cache=False,
        message_ids=None,
    )
    task_id = enqueue_channel_import_job(job.id, countdown=max(0, int(countdown)))
    update_job(db, job, celery_task_id=task_id)
    if commit:
        db.commit()

    body = job_to_public_dict(job)
    body.update(
        {
            "ok": True,
            "network_key": "inbox",
            "channel": INBOX_CHANNEL_IDENT,
            "limit": lim,
            "media_types": mt,
            "job_id": job.id,
            "task_id": task_id,
        }
    )
    return body
