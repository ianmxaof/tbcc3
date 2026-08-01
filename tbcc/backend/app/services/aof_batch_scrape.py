"""Batch inbound Telegram channel scrapes → AOF content pools."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import network_channel_by_key
from app.data.aof_scrape_inbound_map import (
    DEFAULT_INBOUND_SOURCES,
    FIRST_BATCH_POOL_KEYS,
    SKIP_INBOUND_CHAT_IDS,
    match_folder_title_to_pool_key,
)
from app.models.content_pool import ContentPool
from app.models.source import Source
from app.services.scrape_run_service import create_scrape_run
from app.services.telegram_folder_peers import list_telegram_folders

logger = logging.getLogger(__name__)


def scrape_hub_first_enabled() -> bool:
    """
    When true (default), batch scrapes into AOF pools are blocked — use SCRP micro-pull
  → Storage Hub → gatekeeper → pool instead.
    """
    raw = (os.getenv("TBCC_SCRAPE_HUB_FIRST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _peer_scrape_eligible(peer: dict[str, Any]) -> bool:
    cid = int(peer.get("chat_id") or 0)
    if cid in SKIP_INBOUND_CHAT_IDS:
        return False
    # Skip user/bot DM peers (positive ids) — folders sometimes include bots.
    if cid > 0:
        return False
    title = (peer.get("title") or "").lower()
    if title.endswith("_bot") or " bot" in title:
        return False
    if "storage" in title and "hangar" in title:
        return False
    if title.startswith("aof ") or title == "aof packs" or title == "aof link hub":
        return False
    return True


def _pool_for_key(db: Session, pool_key: str) -> ContentPool | None:
    ch = network_channel_by_key(pool_key)
    if not ch:
        return None
    return db.query(ContentPool).filter(ContentPool.name == ch.pool_name).first()


def ensure_scrape_source(
    db: Session,
    *,
    pool_id: int,
    chat_id: int,
    label: str,
    limit: int = 80,
    folder_label: str | None = None,
) -> tuple[Source, bool]:
    ident = str(int(chat_id))
    if folder_label:
        name = f"SCRP [{folder_label}]: {label}"
    else:
        name = f"SCRP: {label}"
    row = (
        db.query(Source)
        .filter(
            Source.source_type == "telegram_channel",
            Source.identifier == ident,
            Source.pool_id == pool_id,
        )
        .first()
    )
    if row:
        row.active = True
        row.name = name
        row.max_messages_per_run = max(int(row.max_messages_per_run or 50), int(limit))
        return row, False
    row = Source(
        name=name,
        source_type="telegram_channel",
        identifier=ident,
        pool_id=pool_id,
        active=True,
        max_messages_per_run=max(1, min(int(limit), 500)),
        media_types="both",
        schedule_enabled=False,
    )
    db.add(row)
    db.flush()
    return row, True


def _inbound_specs_for_pool(
    pool_key: str,
    folder_index: dict[str, list[dict[str, Any]]],
    *,
    use_folder: bool,
    use_defaults: bool,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[int] = set()

    if use_folder:
        for folder_title, peers in folder_index.items():
            if match_folder_title_to_pool_key(folder_title) != pool_key:
                continue
            for p in peers:
                if not _peer_scrape_eligible(p):
                    continue
                cid = int(p["chat_id"])
                if cid in seen:
                    continue
                seen.add(cid)
                specs.append({"chat_id": cid, "label": p.get("title") or str(cid), "from_folder": folder_title})

    if use_defaults:
        for item in DEFAULT_INBOUND_SOURCES.get(pool_key) or []:
            cid = int(item["chat_id"])
            if cid in seen:
                continue
            seen.add(cid)
            specs.append(
                {
                    "chat_id": cid,
                    "label": item.get("label") or str(cid),
                    "from_folder": None,
                    "seed": True,
                }
            )
    return specs


async def discover_folder_index(client) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for folder in await list_telegram_folders(client):
        title = str(folder.get("title") or "").strip()
        if title:
            index[title] = list(folder.get("peers") or [])
    return index


def plan_batch_scrape(
    db: Session,
    pool_keys: list[str],
    *,
    folder_index: dict[str, list[dict[str, Any]]] | None = None,
    limit: int = 80,
    use_folder: bool = True,
    use_defaults: bool = True,
) -> dict[str, Any]:
    folder_index = folder_index or {}
    plan: list[dict[str, Any]] = []
    missing_pools: list[str] = []

    for key in pool_keys:
        pool = _pool_for_key(db, key)
        if not pool:
            missing_pools.append(key)
            continue
        specs = _inbound_specs_for_pool(
            key,
            folder_index,
            use_folder=use_folder,
            use_defaults=use_defaults,
        )
        sources: list[dict[str, Any]] = []
        for spec in specs:
            src, created = ensure_scrape_source(
                db,
                pool_id=int(pool.id),
                chat_id=int(spec["chat_id"]),
                label=str(spec["label"]),
                limit=limit,
                folder_label=spec.get("from_folder"),
            )
            sources.append(
                {
                    "source_id": src.id,
                    "created": created,
                    "chat_id": spec["chat_id"],
                    "label": spec["label"],
                    "from_folder": spec.get("from_folder"),
                    "seed": spec.get("seed", False),
                }
            )
        plan.append(
            {
                "pool_key": key,
                "pool_id": pool.id,
                "pool_name": pool.name,
                "sources": sources,
                "source_count": len(sources),
            }
        )

    return {
        "pool_keys": pool_keys,
        "plan": plan,
        "missing_pools": missing_pools,
        "folder_count": len(folder_index),
    }


def filter_scrape_eligible_source_ids(
    db: Session,
    source_ids: list[int],
) -> tuple[list[int], list[dict[str, Any]]]:
    """Drop forward-disabled channels and infra chat ids before queueing."""
    from app.models.scrape_channel_profile import ScrapeChannelProfile

    eligible: list[int] = []
    skipped: list[dict[str, Any]] = []
    for sid in source_ids:
        src = db.query(Source).filter(Source.id == sid).first()
        if not src or not src.active:
            skipped.append({"source_id": sid, "reason": "inactive_or_missing"})
            continue
        try:
            chat_id = int(str(src.identifier).strip())
        except (TypeError, ValueError):
            eligible.append(sid)
            continue
        if chat_id in SKIP_INBOUND_CHAT_IDS:
            src.active = False
            skipped.append({"source_id": sid, "chat_id": chat_id, "reason": "infra_skip_list"})
            continue
        prof = (
            db.query(ScrapeChannelProfile)
            .filter(ScrapeChannelProfile.chat_id == chat_id)
            .first()
        )
        if prof and prof.forward_enabled is False:
            src.active = False
            skipped.append(
                {
                    "source_id": sid,
                    "chat_id": chat_id,
                    "reason": "forward_disabled",
                    "skip_reason": prof.skip_reason,
                }
            )
            continue
        eligible.append(sid)
    if skipped:
        db.commit()
    return eligible, skipped


def queue_batch_scrapes(db: Session, source_ids: list[int]) -> dict[str, Any]:
    from app.workers.scraper_worker import run_scrape

    if scrape_hub_first_enabled():
        return {
            "queued": [],
            "skipped": [{"source_id": sid, "reason": "hub_first_blocked"} for sid in source_ids],
            "queued_count": 0,
            "skipped_count": len(source_ids),
            "hub_first": True,
            "hint": "Use SCRP micro-pull → Storage Hub (TBCC_SCRAPE_MICRO_PULL_ENABLED=1) or set TBCC_SCRAPE_HUB_FIRST=0 to allow direct pool scrape.",
        }

    eligible, skipped = filter_scrape_eligible_source_ids(db, source_ids)
    queued: list[dict[str, Any]] = []
    for sid in eligible:
        src = db.query(Source).filter(Source.id == sid).first()
        if not src or not src.active:
            continue
        run = create_scrape_run(db, src, trigger="batch")
        async_result = run_scrape.delay(int(sid), "batch", run.id)
        run.celery_task_id = async_result.id
        queued.append({"source_id": sid, "run_id": run.id, "celery_task_id": async_result.id})
    db.commit()
    return {"queued": queued, "skipped": skipped, "queued_count": len(queued), "skipped_count": len(skipped)}


async def run_batch_scrapes_sync(
    api_id: str,
    api_hash: str,
    source_ids: list[int],
    *,
    session_stem: str = "scraper",
) -> list[dict[str, Any]]:
    from telethon import TelegramClient

    from bots.scraper_bot import run_scraper

    results: list[dict[str, Any]] = []
    for sid in source_ids:
        stats = await run_scraper(api_id=api_id, api_hash=api_hash, source_id=sid, session_name=session_stem)
        results.append({"source_id": sid, "stats": stats})
    return results


async def load_folder_index_from_session(
    api_id: str,
    api_hash: str,
    *,
    session_stem: str = "scraper",
) -> dict[str, list[dict[str, Any]]]:
    from telethon import TelegramClient

    client = TelegramClient(session_stem, int(api_id), api_hash)
    await client.start()
    try:
        if not await client.is_user_authorized():
            return {}
        return await discover_folder_index(client)
    finally:
        await client.disconnect()


def default_session_stem() -> str:
    return (os.getenv("TBCC_SCRAPER_TELEGRAM_SESSION") or "scraper").strip() or "scraper"
