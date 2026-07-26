"""
Seed Stars-bait funnel RAG + channel pacing scheduler + optional DM outreach preview.

  cd tbcc/backend
  py -3.13 scripts/apply_stars_bait_outreach.py              # preview
  py -3.13 scripts/apply_stars_bait_outreach.py --execute
  py -3.13 scripts/apply_stars_bait_outreach.py --execute --post-channel-now

Enable paced DMs on island after seed:
  TBCC_STARS_BAIT_DM_ENABLED=1
  TBCC_STARS_BAIT_DM_INTERVAL_MIN=45
  TBCC_STARS_BAIT_DM_BATCH=5
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
from app.services.stars_bait_outreach import apply_stars_bait_outreach


def main() -> None:
    p = argparse.ArgumentParser(description="Apply Stars-bait outreach (RAG + channel pace)")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--post-channel-now", action="store_true", help="Queue immediate main-group bait post")
    args = p.parse_args()
    db = SessionLocal()
    try:
        report = apply_stars_bait_outreach(
            db,
            execute=args.execute,
            post_channel_now=args.post_channel_now,
        )
        if args.execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
