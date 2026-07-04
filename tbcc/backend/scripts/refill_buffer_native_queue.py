"""Refill Buffer native X queue with Linkvertise captions. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_native_queue_refill import refill_buffer_native_queue


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Top up Buffer native X queue with LV gates")
    p.add_argument("--dry-run", action="store_true", help="Preview captions without creating posts")
    args = p.parse_args()
    report = refill_buffer_native_queue(dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
