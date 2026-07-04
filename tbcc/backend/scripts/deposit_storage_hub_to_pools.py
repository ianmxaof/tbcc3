"""

Deposit media from AOF Storage Hub forum topics into matching channel pools.



Small-batch pool seeding (content lanes only — milf, abg, big_tits, …):

  cd tbcc/backend

  py -3.13 scripts/deposit_storage_hub_to_pools.py --execute --content-lanes

  py -3.13 scripts/deposit_storage_hub_to_pools.py --execute --limit 8 --topics milf,abg,big_tits

  py -3.13 scripts/deposit_storage_hub_to_pools.py --execute --all-topics --limit 50

In Storage Hub forum topics (admin_bot): /deposit 15 — queue 15 newest deduped videos into that topic's pool.
  Optional: /deposit 15 both | photos | videos  (default: TBCC_STORAGE_DEPOSIT_MEDIA_TYPES or videos)



Automated beat (optional): TBCC_STORAGE_POOL_SEED_ENABLED=1 in tbcc/.env

"""



from __future__ import annotations



import argparse

import json

import sys

from pathlib import Path



sys.path.insert(0, str(Path(__file__).resolve().parents[1]))



from app.utils.load_tbcc_dotenv import load_tbcc_dotenv



load_tbcc_dotenv()



from app.database.session import SessionLocal

from app.services.aof_growth_hub import (

    queue_storage_hub_deposits,

    storage_pool_seed_batch_size,

    sync_network_schedulers,

)





def main() -> None:

    if hasattr(sys.stdout, "reconfigure"):

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Storage Hub → AOF channel pool deposits")

    p.add_argument("--execute", action="store_true", help="Queue import jobs (default: preview status only)")

    p.add_argument(

        "--limit",

        type=int,

        default=None,

        help=f"Items per topic (1–200). Default: TBCC_STORAGE_POOL_SEED_BATCH or {storage_pool_seed_batch_size()}",

    )

    p.add_argument(

        "--topics",

        type=str,

        default="",

        help="Comma-separated network keys (milf,big_tits,goon). Default: all matched topics.",

    )

    p.add_argument("--all-topics", action="store_true", help="Include packs + every mapped storage lane")

    p.add_argument(

        "--content-lanes",

        action="store_true",

        help="Content receive channels only (excludes PACKS storage lane)",

    )

    p.add_argument("--media-types", choices=["both", "photos", "videos"], default="both")

    p.add_argument("--sync-pools", action="store_true", help="Ensure GOON/BOP/etc. channels+pools exist first")

    args = p.parse_args()



    db = SessionLocal()

    try:

        if args.sync_pools and args.execute:

            sync_network_schedulers(db, execute=True)

            db.commit()

        if not args.execute:

            from app.data.aof_storage_hub_map import content_lane_storage_topics

            from app.services.aof_growth_hub import growth_hub_status



            status = growth_hub_status(db)

            lanes = [

                {

                    "network_key": m.network_key,

                    "topic_title": m.topic_title,

                    "topic_id": m.message_thread_id,

                }

                for m in content_lane_storage_topics()

            ]

            print(json.dumps({"content_lanes": lanes, "default_batch": storage_pool_seed_batch_size()}, indent=2))

            print(json.dumps(status, indent=2, ensure_ascii=False)[:3000])

            print("\n(dry run — pass --execute --content-lanes to queue imports)")

            return

        keys = None

        if args.topics.strip() and not args.all_topics:

            keys = [k.strip().lower() for k in args.topics.split(",") if k.strip()]

        content_only = args.content_lanes or (not args.all_topics and not keys)

        report = queue_storage_hub_deposits(

            db,

            limit=args.limit,

            topic_keys=keys,

            media_types=args.media_types,

            content_lanes_only=content_only,

        )

        print(json.dumps(report, indent=2, ensure_ascii=False))

    finally:

        db.close()





if __name__ == "__main__":

    main()

