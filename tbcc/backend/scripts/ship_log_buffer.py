"""Publish TBCC ship log text to Buffer (Idea or X queue). Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buffer_graphql import (
    buffer_target_channel_ids,
    create_idea,
    create_post,
    find_channel_id_by_service,
)
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded


def main() -> None:
    p = argparse.ArgumentParser(description="TBCC ship log → Buffer")
    p.add_argument("--dry-run", action="store_true", help="Validate env only; do not call Buffer")
    p.add_argument("--idea", action="store_true", help="Create Buffer Idea (default if neither --idea nor --queue)")
    p.add_argument("--queue", action="store_true", help="addToQueue on X primary channel")
    p.add_argument("--share-now", action="store_true", help="With --queue: publish immediately")
    p.add_argument("--title", default="", help="Idea title")
    p.add_argument("--text", required=True, help="Tweet / idea body")
    args = p.parse_args()

    text = (args.text or "").strip()
    if not text:
        print("--text is required", file=sys.stderr)
        sys.exit(1)
    if len(text) > 280:
        print(f"warning: text is {len(text)} chars (X limit 280)", file=sys.stderr)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "chars": len(text), "text": text}, indent=2))
        return

    use_idea = args.idea or not args.queue
    if use_idea:
        title = (args.title or "").strip() or f"TBCC ship log {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        res = create_idea(title=title, text=text)
        print(json.dumps(res, indent=2))
        idea = (res.get("data") or {}).get("createIdea") if isinstance(res.get("data"), dict) else None
        if isinstance(idea, dict) and idea.get("id"):
            print(f"\nIdea created: {idea.get('id')} — edit at https://publish.buffer.com", file=sys.stderr)
        elif res.get("errors"):
            sys.exit(1)
        return

    chans = buffer_target_channel_ids(x_primary_only=True)
    cid = chans[0] if chans else find_channel_id_by_service("twitter")
    if not cid:
        print("Set TBCC_BUFFER_CHANNEL_ID_PRIMARY or run buffer_channels.py", file=sys.stderr)
        sys.exit(1)
    mode = "shareNow" if args.share_now else "addToQueue"
    res = create_post(cid, text, mode=mode)
    print(json.dumps(res, indent=2))
    if not buffer_create_post_succeeded(res):
        err = buffer_create_post_error_message(res)
        print(f"createPost failed: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"\nQueued to channel {cid} ({mode}) — https://publish.buffer.com", file=sys.stderr)


if __name__ == "__main__":
    main()
