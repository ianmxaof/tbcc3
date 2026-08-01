"""Dry-run or force daily revenue brief. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.revenue_brief import (
    build_revenue_brief_bundle,
    draft_revenue_brief_html,
    send_revenue_brief,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC daily revenue brief — spectrum Top 5")
    p.add_argument("--dry-run", action="store_true", help="Print bundle + draft only")
    p.add_argument("--force", action="store_true", help="Send now (ignore hour/dedupe)")
    p.add_argument("--no-llm", action="store_true", help="Heuristic fallback only")
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    db = SessionLocal()
    try:
        bundle = build_revenue_brief_bundle(db, days=args.days)
        if args.dry_run:
            html_body = draft_revenue_brief_html(bundle, use_llm=not args.no_llm)
            out = {
                "bundle": bundle,
                "html": html_body,
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return

        result = send_revenue_brief(db, force=args.force, use_llm=not args.no_llm)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result.get("ok"):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
