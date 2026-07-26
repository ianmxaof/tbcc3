"""Record and query listening-relay post history for the dashboard."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_main_group_topic_map import AOF_MAIN_GROUP_TOPIC_MAP
from app.data.aof_network import AOF_VIP_IDENT, MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.channel import Channel
from app.models.listening_relay_post_log import ListeningRelayPostLog
from app.services.listening_relay_compose import RelayOutbound
from app.services.listening_relay_send import followups_to_json
from app.services.telegram_html_plain import telegram_html_to_plain

_MAX_ROWS = 200
_PREVIEW_LEN = 600


def _topic_title(thread_id: int | None) -> str | None:
    if not thread_id:
        return None
    for row in AOF_MAIN_GROUP_TOPIC_MAP:
        if int(row.message_thread_id) == int(thread_id):
            return row.topic_title
    return None


def queue_listening_relay_post(
    db: Session,
    *,
    trigger: str,
    channel_id: int,
    message_thread_id: int | None,
    random_lane: bool,
    outbound: RelayOutbound,
    send_silent: bool,
    extra: dict[str, Any] | None = None,
) -> ListeningRelayPostLog:
    """Persist history row and queue Telegram + social fan-out."""
    from app.services.telegram_bot_api import relay_use_bot_api
    from app.workers.listening_relay_worker import (
        listening_relay_social_fanout,
        post_listening_relay_bot_api,
    )
    from app.workers.poster_worker import post_listening_relay_message

    merged_extra = dict(extra or {})
    transport = "bot_api" if relay_use_bot_api() else "telethon"
    merged_extra["transport"] = transport

    log = record_listening_relay_post(
        db,
        trigger=trigger,
        channel_id=channel_id,
        message_thread_id=message_thread_id,
        random_lane=random_lane,
        outbound=outbound,
        send_silent=send_silent,
        extra=merged_extra,
    )
    followups_json = followups_to_json(outbound.copy_followups)
    if transport == "bot_api":
        post_listening_relay_bot_api.delay(
            int(channel_id),
            outbound.main_html,
            message_thread_id,
            bool(send_silent),
            followups_json,
            log.id,
        )
    else:
        post_listening_relay_message.delay(
            int(channel_id),
            outbound.main_html,
            message_thread_id,
            bool(send_silent),
            None,
            followups_json,
            log.id,
        )
    listening_relay_social_fanout.delay(outbound.main_html, followups_json, log.id)
    if outbound.goblin_spawn:
        from app.services.goblin_service import schedule_goblin_drop

        schedule_goblin_drop(
            db,
            channel_id=int(channel_id),
            message_thread_id=message_thread_id,
            relay_log_id=int(log.id),
        )
    return log


def record_listening_relay_post(
    db: Session,
    *,
    trigger: str,
    channel_id: int,
    message_thread_id: int | None,
    random_lane: bool,
    outbound: RelayOutbound,
    send_silent: bool,
    extra: dict[str, Any] | None = None,
) -> ListeningRelayPostLog:
    plain = telegram_html_to_plain((outbound.main_html or "").strip(), max_len=_PREVIEW_LEN)
    row = ListeningRelayPostLog(
        trigger_kind=(trigger or "lastfm")[:16],
        status="queued",
        source=(outbound.source or "")[:64] or None,
        source_label=(outbound.source_label or "")[:64] or None,
        artist=(outbound.artist or "")[:512] or None,
        title=(outbound.title or "")[:512] or None,
        album=(outbound.album or "")[:512] if outbound.album else None,
        url=(outbound.url or "")[:2048] if outbound.url else None,
        channel_id=int(channel_id),
        message_thread_id=int(message_thread_id) if message_thread_id else None,
        random_lane=bool(random_lane),
        template_slot=int(outbound.template_slot) if outbound.template_slot is not None else None,
        template_slots_total=int(outbound.template_slots_total) if outbound.template_slots_total else None,
        ascii_beat=bool(outbound.ascii_beat),
        tryptych=bool(outbound.tryptych),
        copy_followups_count=len(outbound.copy_followups or []),
        send_silent=bool(send_silent),
        main_html_preview=plain or None,
        extra_json=json.dumps(extra, separators=(",", ":"), default=str) if extra else None,
    )
    db.add(row)
    db.flush()
    _prune_old_rows(db)
    return row


def _prune_old_rows(db: Session) -> None:
    count = db.query(ListeningRelayPostLog.id).count()
    if count <= _MAX_ROWS:
        return
    excess = count - _MAX_ROWS
    ids = (
        db.query(ListeningRelayPostLog.id)
        .order_by(ListeningRelayPostLog.id.asc())
        .limit(excess)
        .all()
    )
    if not ids:
        return
    db.query(ListeningRelayPostLog).filter(
        ListeningRelayPostLog.id.in_([r[0] for r in ids])
    ).delete(synchronize_session=False)


def mark_relay_post_sent(db: Session, log_id: int, *, telegram_message_id: int | None) -> None:
    row = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == int(log_id)).first()
    if not row:
        return
    row.status = "sent"
    if telegram_message_id:
        row.telegram_message_id = int(telegram_message_id)


def mark_relay_post_failed(db: Session, log_id: int, error: str) -> None:
    row = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == int(log_id)).first()
    if not row:
        return
    row.status = "failed"
    row.error_message = (error or "send failed")[:4000]


def mark_relay_buffer_sent(db: Session, log_id: int) -> None:
    row = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == int(log_id)).first()
    if not row:
        return
    row.buffer_sent = True


def mark_relay_discord_sent(db: Session, log_id: int) -> None:
    row = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == int(log_id)).first()
    if not row:
        return
    row.discord_sent = True


def _telegram_message_deep_link(channel_identifier: str | None, message_id: int | None) -> str | None:
    if not message_id or not channel_identifier:
        return None
    ident = str(channel_identifier).strip()
    if ident.startswith("@"):
        return f"https://t.me/{ident[1:]}/{int(message_id)}"
    if ident.startswith("-100") and len(ident) > 4:
        return f"https://t.me/c/{ident[4:]}/{int(message_id)}"
    if ident.startswith("http://") or ident.startswith("https://"):
        return None
    if ident.lstrip("-").isdigit():
        digits = ident.lstrip("-")
        if digits.startswith("100") and len(digits) > 3:
            return f"https://t.me/c/{digits[3:]}/{int(message_id)}"
    return None


def _destination_label(
    db: Session,
    *,
    channel_id: int | None,
    message_thread_id: int | None,
    random_lane: bool,
) -> dict[str, Any]:
    if random_lane:
        dest = {"kind": "random", "label": "Random AOF lane"}
    elif message_thread_id:
        topic = _topic_title(message_thread_id)
        dest = {"kind": "topic", "label": topic or f"Topic #{message_thread_id}", "thread_id": message_thread_id}
    else:
        dest = {"kind": "main", "label": "Main chat"}

    if channel_id:
        ch = db.query(Channel).filter(Channel.id == int(channel_id)).first()
        if ch:
            ident = (ch.identifier or "").strip()
            dest["channel_id"] = int(channel_id)
            dest["channel_name"] = ch.name or ident or str(channel_id)
            dest["channel_identifier"] = ident or None
            if ident == AOF_VIP_IDENT:
                dest["lane"] = "vip"
            elif ident == MAIN_GROUP_IDENT:
                dest["lane"] = "loot_room"
    return dest


def list_listening_relay_posts(db: Session, *, limit: int = 30, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    rows = (
        db.query(ListeningRelayPostLog)
        .order_by(ListeningRelayPostLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    ch_ids = {r.channel_id for r in rows if r.channel_id}
    ch_meta: dict[int, dict[str, str | None]] = {}
    if ch_ids:
        for ch in db.query(Channel).filter(Channel.id.in_(ch_ids)).all():
            ch_meta[int(ch.id)] = {
                "name": ch.name or ch.identifier or str(ch.id),
                "identifier": ch.identifier,
            }
    items: list[dict[str, Any]] = []
    for r in rows:
        headline = ""
        if r.artist and r.title:
            headline = f"{r.artist} — {r.title}"
        elif r.title:
            headline = r.title
        elif r.artist:
            headline = r.artist
        extra: dict[str, Any] | None = None
        if r.extra_json:
            try:
                parsed = json.loads(r.extra_json)
                extra = parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, TypeError):
                extra = None
        items.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "trigger": r.trigger_kind,
                "status": r.status,
                "source": r.source,
                "source_label": r.source_label,
                "artist": r.artist,
                "title": r.title,
                "album": r.album,
                "url": r.url,
                "headline": headline,
                "destination": _destination_label(
                    db,
                    channel_id=r.channel_id,
                    message_thread_id=r.message_thread_id,
                    random_lane=bool(r.random_lane),
                ),
                "template_slot": r.template_slot,
                "template_slots_total": r.template_slots_total,
                "ascii_beat": bool(r.ascii_beat),
                "tryptych": bool(r.tryptych),
                "copy_followups_count": int(r.copy_followups_count or 0),
                "send_silent": bool(r.send_silent),
                "main_html_preview": r.main_html_preview,
                "telegram_message_id": r.telegram_message_id,
                "telegram_message_url": _telegram_message_deep_link(
                    (ch_meta.get(int(r.channel_id)) or {}).get("identifier") if r.channel_id else None,
                    r.telegram_message_id,
                ),
                "buffer_sent": bool(r.buffer_sent),
                "discord_sent": bool(r.discord_sent),
                "error_message": r.error_message,
                "extra": extra,
            }
        )
    return {"items": items, "limit": limit, "offset": offset}
