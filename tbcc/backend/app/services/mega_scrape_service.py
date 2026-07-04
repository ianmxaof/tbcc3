"""Telegram channel link scrape → mega pipeline → loot_modifiers (direct/paste hosts first)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.data.mega_scrape_channel_sources import MEGA_SCRAPE_CHANNEL_SOURCES
from app.models.loot import LootModifier
from app.services.mega_link_extract import (
    classify_url_host,
    extract_urls_from_text,
    parse_size_gb_hint,
)
from app.services.mega_link_pipeline import build_modifier_payload, resolve_to_file_host
from app.utils.telegram_peer import normalize_telethon_peer_identifier, resolve_telethon_entity

logger = logging.getLogger(__name__)

# Scrape these without bypass.vip (paste, file host, sophon).
DIRECT_SCRAPE_HOST_KINDS = frozenset({"file_host", "paste", "sophon"})


@dataclass
class MegaScrapeStats:
    channels_scanned: int = 0
    messages_scanned: int = 0
    urls_seen: int = 0
    urls_eligible: int = 0
    resolved: int = 0
    modifiers_created: int = 0
    skipped_duplicate: int = 0
    skipped_obfuscated: int = 0
    pipeline_failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)


def _message_text_and_urls(message) -> tuple[str, list[str]]:
    parts: list[str] = []
    urls: list[str] = []
    if getattr(message, "message", None):
        parts.append(str(message.message))
    if getattr(message, "text", None) and message.text not in parts:
        parts.append(str(message.text))
    for ent in getattr(message, "entities", None) or []:
        cls = ent.__class__.__name__
        if cls == "MessageEntityTextUrl" and getattr(message, "message", None):
            try:
                off = int(ent.offset)
                ln = int(ent.length)
                snippet = message.message[off : off + ln]
                if ent.url:
                    urls.append(str(ent.url).strip())
                parts.append(snippet)
            except Exception:
                pass
        elif cls == "MessageEntityUrl" and getattr(message, "message", None):
            try:
                off = int(ent.offset)
                ln = int(ent.length)
                urls.append(message.message[off : off + ln].strip())
            except Exception:
                pass
    blob = "\n".join(parts)
    for item in extract_urls_from_text(blob):
        urls.append(item.url)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = u.rstrip(".,;)]")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return blob, out


def _url_eligible(url: str, *, include_obfuscated: bool) -> bool:
    kind = classify_url_host(url)
    if kind == "affiliate":
        return False
    if kind == "obfuscated":
        return include_obfuscated
    return kind in DIRECT_SCRAPE_HOST_KINDS


def _modifier_exists(db: Session, destination: str, lv_wrapped: str) -> bool:
    dest = (destination or "").strip()
    lv = (lv_wrapped or "").strip()
    if not dest and not lv:
        return False
    q = db.query(LootModifier.id)
    if lv:
        row = q.filter(LootModifier.target_url == lv).first()
        if row:
            return True
    if dest:
        row = (
            db.query(LootModifier.id)
            .filter(LootModifier.source_note.isnot(None))
            .filter(LootModifier.source_note.contains(dest[:180]))
            .first()
        )
        if row:
            return True
    return False


def _create_modifier(db: Session, payload: dict[str, Any], *, execute: bool) -> bool:
    dest = ""
    note = str(payload.get("source_note") or "")
    if "|dest=" in note:
        dest = note.split("|dest=", 1)[1]
    lv = str(payload.get("target_url") or "")
    if _modifier_exists(db, dest, lv):
        return False
    if not execute:
        return True
    m = LootModifier(
        kind=str(payload.get("kind") or "mega_pack"),
        label=str(payload.get("label") or "Pack")[:256],
        target_url=lv,
        weight_base=float(payload.get("weight_base") or 1.0),
        rarity_focus=float(payload.get("rarity_focus") or 5.0),
        min_rarity_tier=int(payload.get("min_rarity_tier") or 3),
        bypass_vip=bool(payload.get("bypass_vip")),
        active=bool(payload.get("active", True)),
        source_note=str(payload.get("source_note") or "mega_scrape")[:2000],
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    try:
        from app.services.k2s_mirror_service import maybe_enqueue_k2s_mirror

        maybe_enqueue_k2s_mirror(
            int(m.id),
            label=str(payload.get("label") or m.label),
            source_note=str(payload.get("source_note") or m.source_note),
        )
    except Exception:
        pass
    return True


def filter_channel_sources(
    *,
    kinds: set[str] | None = None,
    chat_ids: list[int] | None = None,
) -> list[dict]:
    out: list[dict] = []
    for row in MEGA_SCRAPE_CHANNEL_SOURCES:
        if kinds and row.get("kind") not in kinds:
            continue
        if chat_ids and int(row["chat_id"]) not in chat_ids:
            continue
        out.append(row)
    return out


async def scrape_channels(
    client,
    db: Session,
    sources: list[dict],
    *,
    messages_per_channel: int = 40,
    include_obfuscated: bool = False,
    execute: bool = False,
    sleep_s: float = 1.5,
) -> MegaScrapeStats:
    stats = MegaScrapeStats()
    limit = max(1, min(int(messages_per_channel), 200))

    for src in sources:
        chat_id = int(src["chat_id"])
        label = str(src.get("label") or chat_id)
        ident = normalize_telethon_peer_identifier(str(chat_id))
        stats.channels_scanned += 1
        try:
            entity = await resolve_telethon_entity(client, ident)
        except Exception as e:
            logger.warning("mega scrape resolve failed %s: %s", label, e)
            stats.errors.append({"channel": label, "code": "resolve_failed", "detail": str(e)[:300]})
            continue

        msg_count = 0
        try:
            async for message in client.iter_messages(entity, limit=limit):
                msg_count += 1
                stats.messages_scanned += 1
                blob, urls = _message_text_and_urls(message)
                if not urls:
                    continue
                for url in urls:
                    stats.urls_seen += 1
                    kind = classify_url_host(url)
                    if kind == "obfuscated":
                        stats.skipped_obfuscated += 1
                        if not include_obfuscated:
                            continue
                    if not _url_eligible(url, include_obfuscated=include_obfuscated):
                        continue
                    stats.urls_eligible += 1
                    hint = parse_size_gb_hint(blob, near_url=url) if blob else None
                    try:
                        pipeline = resolve_to_file_host(url)
                    except Exception as e:
                        stats.pipeline_failed += 1
                        stats.errors.append({"channel": label, "url": url[:120], "error": str(e)[:200]})
                        await asyncio.sleep(sleep_s)
                        continue
                    if not pipeline.ok:
                        stats.pipeline_failed += 1
                        continue
                    if hint and not pipeline.size_gb_hint:
                        pipeline.size_gb_hint = hint
                    try:
                        payload = build_modifier_payload(
                            pipeline,
                            label=f"{label} — {pipeline.destination_url or url}"[:256],
                            source_note=f"mega_scrape:{label}|msg={message.id}",
                        )
                    except ValueError:
                        stats.pipeline_failed += 1
                        continue
                    stats.resolved += 1
                    created = _create_modifier(db, payload, execute=execute)
                    if created:
                        stats.modifiers_created += 1
                    else:
                        stats.skipped_duplicate += 1
                    await asyncio.sleep(sleep_s)
        except Exception as e:
            logger.exception("mega scrape iter failed %s", label)
            stats.errors.append({"channel": label, "code": "iter_failed", "detail": str(e)[:300]})

        logger.info(
            "mega scrape channel %s: msgs=%s eligible_urls so far=%s",
            label,
            msg_count,
            stats.urls_eligible,
        )
    return stats


def _default_session_stem() -> str:
    from app.services.scraper_telethon_auth import scraper_session_stem

    return scraper_session_stem()


async def run_mega_scrape(
    api_id: str,
    api_hash: str,
    *,
    session_stem: str | None = None,
    kinds: set[str] | None = None,
    chat_ids: list[int] | None = None,
    messages_per_channel: int = 40,
    include_obfuscated: bool = False,
    execute: bool = False,
) -> dict[str, Any]:
    from telethon import TelegramClient

    from app.database.session import SessionLocal

    sources = filter_channel_sources(kinds=kinds, chat_ids=chat_ids)
    if not sources:
        return {"ok": False, "error": "no_sources", "stats": {}}

    stem = session_stem or _default_session_stem()
    client = TelegramClient(stem, int(api_id), api_hash)
    await client.start()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {
            "ok": False,
            "error": "session_not_authorized",
            "detail": f"Log in: python scripts/login_telethon_sessions.py or setup-scraper-session.ps1 ({stem}.session)",
        }
    db = SessionLocal()
    try:
        stats = await scrape_channels(
            client,
            db,
            sources,
            messages_per_channel=messages_per_channel,
            include_obfuscated=include_obfuscated,
            execute=execute,
        )
        return {
            "ok": True,
            "execute": execute,
            "sources": len(sources),
            "stats": stats.__dict__,
        }
    finally:
        db.close()
        await client.disconnect()
