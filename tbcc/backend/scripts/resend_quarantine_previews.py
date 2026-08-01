"""Resend gatekeeper quarantine review cards with media preview (copyMessage).

Usage:
  py -3.13 scripts/resend_quarantine_previews.py --limit 20
  py -3.13 scripts/resend_quarantine_previews.py --media-id 7440
"""

from __future__ import annotations

import argparse

from app.database.session import SessionLocal
from app.models.media import Media
from app.services.gatekeeper_review import send_quarantine_review_message
from app.services.media_gatekeeper import gatekeeper_verdict_from_media


def main() -> None:
    p = argparse.ArgumentParser(description="Resend quarantine review cards with media preview")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--media-id", type=int, default=0)
    args = p.parse_args()

    with SessionLocal() as db:
        if args.media_id:
            ids = [int(args.media_id)]
        else:
            rows = (
                db.query(Media)
                .filter(Media.status.in_(("pending", "posted")))
                .order_by(Media.id.desc())
                .limit(max(1, int(args.limit)) * 5)
                .all()
            )
            ids = [int(r.id) for r in rows if gatekeeper_verdict_from_media(r) == "quarantine"][
                : max(1, int(args.limit))
            ]

        if not ids:
            print("No quarantine media found.")
            return

        for mid in ids:
            out = send_quarantine_review_message(db, mid)
            print(mid, out.get("preview"), out.get("ok"), out.get("reason") or out.get("error") or "")


if __name__ == "__main__":
    main()
