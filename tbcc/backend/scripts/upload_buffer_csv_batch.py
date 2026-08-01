"""Upload rows from a Buffer bulk-import CSV via GraphQL (customScheduled + dueAt).

Run from tbcc/backend:

  py -3.13 scripts/upload_buffer_csv_batch.py --csv ~/Downloads/buffer_import_primary.csv --limit 8
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_graphql import create_post, list_posts, resolve_organization_id  # noqa: E402
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")


def _pt_to_iso(posting_time: str) -> str:
    raw = (posting_time or "").strip()
    dt = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=PT)
    return dt.isoformat(timespec="seconds")


def _scheduled_count(org_id: str) -> int:
    return len(list_posts(organization_id=org_id, status=["scheduled"], first=100))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Upload Buffer CSV batch via API")
    p.add_argument("--csv", required=True, help="Path to Buffer import CSV")
    p.add_argument("--limit", type=int, default=8, help="Max rows to upload (default 8)")
    p.add_argument("--offset", type=int, default=0, help="Skip first N data rows")
    p.add_argument(
        "--channel-id",
        default="",
        help="Buffer channel id (default: TBCC_BUFFER_CHANNEL_ID_PRIMARY)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--pause-s", type=float, default=1.5, help="Pause between API calls")
    args = p.parse_args()

    import os

    channel_id = (args.channel_id or os.getenv("TBCC_BUFFER_CHANNEL_ID_PRIMARY") or "").strip()
    if not channel_id:
        raise SystemExit("TBCC_BUFFER_CHANNEL_ID_PRIMARY unset")

    path = Path(args.csv).expanduser()
    if not path.is_file():
        raise SystemExit(f"CSV not found: {path}")

    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    batch = rows[args.offset : args.offset + max(0, args.limit)]
    if not batch:
        raise SystemExit("No rows in batch")

    org_id = resolve_organization_id()
    before: int | None = None
    if not args.dry_run:
        before = _scheduled_count(org_id)
    report: dict[str, object] = {
        "channel_id": channel_id,
        "org_scheduled_before": before,
        "uploaded": 0,
        "results": [],
        "errors": [],
    }

    for i, row in enumerate(batch, start=1):
        text = (row.get("Text") or "").strip()
        image = (row.get("Image URL") or "").strip()
        posting = (row.get("Posting Time") or "").strip()
        due_at = _pt_to_iso(posting) if posting else ""
        item = {
            "index": args.offset + i,
            "posting_time": posting,
            "due_at": due_at,
            "text_preview": text[:100],
        }
        if args.dry_run:
            item["status"] = "dry_run"
            report["results"].append(item)
            continue
        try:
            res = create_post(
                channel_id,
                text,
                mode="customScheduled",
                scheduling_type="automatic",
                image_url=image or None,
                due_at=due_at,
            )
            ok = buffer_create_post_succeeded(res)
            item["status"] = "ok" if ok else "error"
            if ok:
                report["uploaded"] = int(report["uploaded"]) + 1
            else:
                msg = buffer_create_post_error_message(res) or "createPost failed"
                item["error"] = msg[:300]
                report["errors"].append(msg[:300])
            post = ((res.get("data") or {}).get("createPost") or {}).get("post") or {}
            if isinstance(post, dict) and post.get("id"):
                item["post_id"] = post.get("id")
        except Exception as e:
            item["status"] = "exception"
            item["error"] = str(e)[:300]
            report["errors"].append(str(e)[:300])
        report["results"].append(item)
        if not args.dry_run and i < len(batch):
            time.sleep(max(0.5, args.pause_s))

    if not args.dry_run:
        report["org_scheduled_after"] = _scheduled_count(org_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
