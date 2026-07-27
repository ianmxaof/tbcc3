"""
Phase 6 promo apply — Loot Room goblin bulletin, network teaser sync, milestone burst.

  cd tbcc/backend
  py -3.13 scripts/apply_goblin_milestone_promo.py              # preview
  py -3.13 scripts/apply_goblin_milestone_promo.py --execute
  py -3.13 scripts/apply_goblin_milestone_promo.py --execute --fire-milestone
  py -3.13 scripts/apply_goblin_milestone_promo.py --execute --sync-network
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import MAIN_GROUP_IDENT, MAINHUB_CHANNEL_IDENT
from app.database.session import SessionLocal
from app.services.aof_growth_hub import sync_network_schedulers
from app.services.aof_loot_goblin_promo import (
    MILESTONE_LOOT_ROOM_SCHED_NAME,
    MILESTONE_MAINHUB_SCHED_NAME,
    MILESTONE_X_TEMPLATE,
    channel_id_for_ident,
    upsert_loot_room_goblin_bulletin,
    upsert_milestone_burst_posts,
)
from app.services.aof_social_links import fill_armory_template
from app.services.seed_aof_buffer_armory import seed_relay_buffer_armory, seed_scheduled_buffer_armory


def _trigger_post(post_id: int, *, sync: bool = False, countdown: int = 0) -> dict:
    from app.workers.poster_worker import post_scheduled_text

    try:
        if sync:
            post_scheduled_text(int(post_id), manual_trigger=True)
            return {"post_id": post_id, "ok": True, "mode": "sync"}
        result = post_scheduled_text.apply_async(
            args=[int(post_id)],
            kwargs={"manual_trigger": True},
            countdown=max(0, int(countdown)),
        )
        return {
            "post_id": post_id,
            "ok": True,
            "mode": "celery",
            "task_id": result.id,
            "countdown": max(0, int(countdown)),
        }
    except Exception as e:
        return {"post_id": post_id, "ok": False, "error": str(e)[:300]}


def _prepend_milestone_buffer(db, *, execute: bool) -> dict:
    raw = fill_armory_template(
        MILESTONE_X_TEMPLATE,
        utm_source="buffer",
        utm_medium="x",
        utm_campaign="milestone_20260726",
        for_x=True,
        db=db,
        advance_affiliate=False,
    )
    entry = {"text_preview": raw[:120], "status": "preview"}
    if not execute:
        return entry
    from app.models.listening_relay_settings import ListeningRelaySettings
    from app.models.scheduled_text_post import ScheduledTextPost

    item = {"text": raw}
    relay = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
    if relay:
        q = relay.get_buffer_x_queue() or []
        relay.set_buffer_x_queue([item] + q[:15])
    posts = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.buffer_mirror_enabled.is_(True))
        .all()
    )
    n = 0
    for post in posts:
        q = post.get_buffer_x_queue() or []
        post.set_buffer_x_queue([item] + q[:15])
        n += 1
    entry["status"] = "prepended"
    entry["mirror_posts"] = n
    return entry


def main() -> int:
    p = argparse.ArgumentParser(description="Apply Loot Goblin + milestone Phase 6 promo")
    p.add_argument("--execute", action="store_true", help="Write DB changes")
    p.add_argument("--sync-network", action="store_true", help="Run sync_network_schedulers (goblin ~1/6 + AI prompt drops)")
    p.add_argument("--skip-bulletin", action="store_true", help="Skip Loot Room goblin pinned bulletin")
    p.add_argument("--skip-milestone", action="store_true", help="Skip milestone one-shot schedulers")
    p.add_argument("--fire-milestone", action="store_true", help="Enqueue milestone posts immediately after create")
    p.add_argument("--milestone-minutes", type=int, default=5, help="Schedule milestone burst N minutes from now")
    p.add_argument("--seed-buffer", action="store_true", help="Prepend milestone line to buffer_x_queue armories")
    p.add_argument("--reseed-armory", action="store_true", help="Full armory reseed (relay + mirror schedulers)")
    args = p.parse_args()

    execute = bool(args.execute)
    report: dict = {"execute": execute, "at": datetime.now(timezone.utc).isoformat()}

    db = SessionLocal()
    try:
        loot_cid = channel_id_for_ident(db, MAIN_GROUP_IDENT)
        hub_cid = channel_id_for_ident(db, MAINHUB_CHANNEL_IDENT)
        report["loot_room_channel_id"] = loot_cid
        report["mainhub_channel_id"] = hub_cid

        if not args.skip_bulletin and loot_cid:
            report["goblin_bulletin"] = upsert_loot_room_goblin_bulletin(
                db, channel_id=loot_cid, execute=execute
            )
        elif not args.skip_bulletin:
            report["goblin_bulletin"] = {"status": "loot_room_channel_missing"}

        if not args.skip_milestone and loot_cid:
            report["milestone_burst"] = upsert_milestone_burst_posts(
                db,
                loot_room_channel_id=loot_cid,
                mainhub_channel_id=hub_cid,
                execute=execute,
                fire_in_minutes=args.milestone_minutes,
            )
        elif not args.skip_milestone:
            report["milestone_burst"] = {"status": "loot_room_channel_missing"}

        if args.sync_network or execute:
            report["network_sync"] = sync_network_schedulers(db, execute=execute)

        if args.seed_buffer or (execute and not args.skip_milestone):
            report["buffer_milestone"] = _prepend_milestone_buffer(db, execute=execute)

        if args.reseed_armory and execute:
            report["armory_relay"] = seed_relay_buffer_armory(db, replace=True)
            report["armory_scheduled"] = seed_scheduled_buffer_armory(db, replace=True)

        if execute:
            db.commit()

        if args.fire_milestone and execute:
            from app.models.scheduled_text_post import ScheduledTextPost

            triggers = []
            for name in (MILESTONE_LOOT_ROOM_SCHED_NAME, MILESTONE_MAINHUB_SCHED_NAME):
                row = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == name).first()
                if row and row.sent_at is None:
                    triggers.append(_trigger_post(int(row.id), countdown=30))
            report["milestone_triggers"] = triggers

        print(json.dumps(report, indent=2, default=str))
        return 0
    except Exception as e:
        db.rollback()
        print(json.dumps({"ok": False, "error": str(e)[:500]}, indent=2))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
