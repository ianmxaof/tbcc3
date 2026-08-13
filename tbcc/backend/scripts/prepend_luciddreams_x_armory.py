"""Prepend Luciddreamstobot promo line to buffer_x_queue armories (relay + scheduled)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_social_links import affiliate_undress_primary_url

LUCID_COPY = (
    "130 video poses on @aof_spicybot_bot — upload, pick motion, reveal. "
    "Free credits: {link}"
)


def _prepend(queue: list[dict], item: dict, *, cap: int = 50) -> list[dict]:
    if queue and queue[0].get("text") == item.get("text"):
        return queue
    return [item] + [q for q in queue if q.get("text") != item.get("text")][: cap - 1]


def main() -> None:
    link = affiliate_undress_primary_url()
    text = LUCID_COPY.format(link=link)
    item = {"text": text, "source": "luciddreams_spicy_parity"}
    db = SessionLocal()
    report: dict = {"link": link, "text": text}
    try:
        relay = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
        if relay:
            q = relay.get_buffer_x_queue() or []
            relay.set_buffer_x_queue(_prepend(q, item))
            report["relay_before"] = len(q)
            report["relay_after"] = len(relay.get_buffer_x_queue() or [])
        posts = db.query(ScheduledTextPost).all()
        touched = 0
        for post in posts:
            q = post.get_buffer_x_queue() or []
            if not q:
                continue
            post.set_buffer_x_queue(_prepend(q, item))
            touched += 1
        report["scheduled_posts_touched"] = touched
        db.commit()
    finally:
        db.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
