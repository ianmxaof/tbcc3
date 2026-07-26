"""
Robocopy watermark fan-out CLI — master folder → promo_heavy / lane_light / vault_clean.

  cd tbcc/backend
  py -3.13 scripts/robocopy_watermark_cli.py --master PATH --out PATH --dry-run
  py -3.13 scripts/robocopy_watermark_cli.py --master PATH --out PATH --execute
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.robocopy_watermark import apply_config_for_tier, fan_out_master_folder
from app.data.loot_lane_economy import WatermarkTier


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Robocopy watermark fan-out")
    p.add_argument("--master", required=True, help="Folder of clean master media")
    p.add_argument("--out", required=True, help="Output root (creates promo_heavy/lane_light/vault_clean)")
    p.add_argument("--dry-run", action="store_true", help="Plan only (default if --execute omitted)")
    p.add_argument("--execute", action="store_true", help="Write files")
    p.add_argument("--max-files", type=int, default=None)
    p.add_argument("--show-configs", action="store_true", help="Print tier configs and exit")
    args = p.parse_args()

    if args.show_configs:
        out = {}
        for tier in WatermarkTier:
            cfg = apply_config_for_tier(tier)
            out[tier.value] = {
                "enabled": cfg.enabled,
                "skip": cfg.skip,
                "opacity": cfg.opacity,
                "texts": list(cfg.texts),
                "mode": cfg.mode,
                "position": cfg.position,
            }
        print(json.dumps(out, indent=2))
        return

    dry = not args.execute
    report = fan_out_master_folder(
        args.master,
        args.out,
        max_files=args.max_files,
        dry_run=dry or args.dry_run,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
