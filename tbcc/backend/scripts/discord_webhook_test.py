"""Test Discord webhook + optional scheduled post discord_mirror flag. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.buffer_surface_caption import build_discord_caption
from app.services.outbound_webhook import notify_discord_webhook_text


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Discord webhook test for AOF fan-out")
    p.add_argument("--execute", action="store_true", help="POST test message to Discord webhook")
    p.add_argument("--enable-scheduled", action="store_true", help="Enable discord_mirror on buffer-mirror posts")
    args = p.parse_args()

    import os

    hook = (os.getenv("TBCC_DISCORD_LISTENING_RELAY_WEBHOOK_URL") or "").strip()
    if not hook:
        print("ERROR: TBCC_DISCORD_LISTENING_RELAY_WEBHOOK_URL unset", file=sys.stderr)
        return 2

    body = build_discord_caption(
        teaser="TBCC Discord fan-out test — hub, map, invite, gate.",
        utm_campaign="webhook_test",
    )
    print(body)
    print(file=sys.stderr)

    if args.enable_scheduled:
        with SessionLocal() as db:
            posts = (
                db.query(ScheduledTextPost)
                .filter(ScheduledTextPost.buffer_mirror_enabled.is_(True))
                .order_by(ScheduledTextPost.id.asc())
                .all()
            )
            n = 0
            for post in posts:
                post.discord_mirror_enabled = True
                n += 1
            if n:
                db.commit()
            print(f"enabled discord_mirror on {n} scheduled post(s)", file=sys.stderr)

    if not args.execute:
        print("Dry run — use --execute to post", file=sys.stderr)
        return 0

    ok = notify_discord_webhook_text(hook, body)
    if ok:
        print("OK — Discord webhook POST sent", file=sys.stderr)
        return 0
    print("FAIL — Discord webhook rejected (forum channels need TBCC_DISCORD_WEBHOOK_THREAD_NAME)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
