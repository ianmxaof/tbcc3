"""
Audit and dedupe duplicate post_scheduled_text tasks in the Celery post queue.

  cd tbcc/backend
  py -3.13 scripts/dedupe_celery_post_queue.py --audit
  py -3.13 scripts/dedupe_celery_post_queue.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.celery_queue_ops import audit_post_queue, dedupe_post_scheduled_text_queue


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--audit", action="store_true", help="Report queue depth and duplicate counts")
    p.add_argument("--execute", action="store_true", help="Remove duplicate post_scheduled_text tasks")
    p.add_argument("--queue", default="post")
    args = p.parse_args()
    if not args.audit and not args.execute:
        args.audit = True

    report: dict = {}
    if args.audit:
        report["audit"] = audit_post_queue(args.queue)
    if args.execute:
        report["dedupe"] = dedupe_post_scheduled_text_queue(args.queue, keep="oldest")
        report["audit_after"] = audit_post_queue(args.queue)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
