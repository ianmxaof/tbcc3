#!/usr/bin/env python3
"""One-shot wk30 hub teaser — Loot Room post + Buffer mirror attempt."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_scheduled_text


def main() -> int:
    beacon = "https://api.powercore.app/r/wk30-x-hub"
    caption = (
        "AOF hub — wk30 burst. Gates + map in one tap.\n\n"
        f"{beacon}\n\n"
        "Stars checkout in every lane."
    )
    db = SessionLocal()
    post = ScheduledTextPost(
        name="wk30-x-hub-teaser",
        scheduler_category="promo_bulletin",
        channel_id=8,
        content=caption,
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        buffer_mirror_enabled=True,
        buffer_publish_now=True,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=10,
        checkout_button_label="Pay ⭐ 500",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    task = post_scheduled_text.delay(post.id, manual_trigger=True)
    out = {"ok": True, "post_id": post.id, "task_id": str(task.id), "beacon": beacon}
    print(json.dumps(out))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
