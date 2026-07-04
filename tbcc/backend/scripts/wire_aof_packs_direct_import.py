#!/usr/bin/env python3

"""Wire pack-pool modifiers into AOF PACKS scheduler + enable Stars checkout."""



from __future__ import annotations



import sys

from pathlib import Path



_backend = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_backend))



from app.utils.load_tbcc_dotenv import load_tbcc_dotenv



load_tbcc_dotenv()



from app.database.session import SessionLocal

from app.services.loot_pack_pool import refresh_aof_packs_scheduler





def main() -> None:

    db = SessionLocal()

    try:

        result = refresh_aof_packs_scheduler(db)

        if not result.get("ok"):

            raise SystemExit(result.get("error") or "refresh_failed")

        print(f"scheduler_id={result.get('scheduler_id')}")
        print(f"modifiers={result.get('modifier_count')} captions={result.get('caption_count')}")
        print(f"promo_media={result.get('promo_media_count')} pool_only={result.get('pool_only_mode')}")
        print(f"album_unique_media={result.get('album_unique_media')}")
        print(f"primary_gate={str(result.get('primary_gate_url') or '')[:90]}")

    finally:

        db.close()





if __name__ == "__main__":

    main()

