"""Sync aof_x_promo_image_pool.json from the aof-x-promo R2 bucket (already-uploaded images).

Run from tbcc/backend:

  py -3 scripts/sync_x_promo_pool_from_r2.py --preview
  py -3 scripts/sync_x_promo_pool_from_r2.py --execute

Requires TBCC_R2_ACCOUNT_ID + access keys and TBCC_X_PROMO_R2_PUBLIC_BASE_URL
(pub-….r2.dev for aof-x-promo — not media.powercore.app / aof-media).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.r2_promo_upload import (  # noqa: E402
    pool_json_path,
    sync_x_promo_pool_from_r2,
    x_promo_r2_config,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Sync X promo image pool from R2 bucket")
    p.add_argument("--prefix", default="", help="Override object prefix (default: TBCC_X_PROMO_R2_PREFIX)")
    p.add_argument("--preview", action="store_true", help="List what would be synced")
    p.add_argument("--execute", action="store_true", help="Write pool JSON")
    args = p.parse_args()

    cfg = x_promo_r2_config()
    print("pool file:", pool_json_path(), file=sys.stderr)
    print("x-promo r2:", bool(cfg), file=sys.stderr)
    if cfg:
        print(f"  bucket: {cfg['bucket']}", file=sys.stderr)
        print(f"  public base: {cfg['public_base']}", file=sys.stderr)

    if not args.preview and not args.execute:
        print("Pass --preview or --execute", file=sys.stderr)
        sys.exit(1)

    prefix = args.prefix.strip() or None
    report = sync_x_promo_pool_from_r2(prefix=prefix, dry_run=args.preview)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
