#!/usr/bin/env python3
"""Quick island ops snapshot — touches, beacons, companion funnel, poster backlog."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.models.click_link import ClickLink
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.user_funnel_touch import UserFunnelTouch
from app.services.companion_cogs import companion_margin_summary
from app.services.gate_funnel import gate_funnel_report
from app.services.system_health import schedulers_stall_summary

_SPICY_SOURCE = "src_aff_aof_spicy_companion_x_buffer"


def main() -> int:
    db = SessionLocal()
    out: dict = {}
    out["touches_total"] = db.query(UserFunnelTouch).count()
    out["touches_recent"] = [
        {
            "uid": r.telegram_user_id,
            "first": r.first_source_ref,
            "last": r.last_source_ref,
            "count": r.touch_count,
        }
        for r in db.query(UserFunnelTouch).order_by(UserFunnelTouch.last_seen_at.desc()).limit(10)
    ]
    out["wk30_beacons"] = [
        {"slug": s, "hits": int(h or 0)}
        for s, h in db.query(ClickLink.slug, ClickLink.hit_count).filter(ClickLink.slug.like("wk30%")).all()
    ]
    spicy_link = (
        db.query(ClickLink)
        .filter(ClickLink.source_ref == _SPICY_SOURCE)
        .order_by(ClickLink.id.desc())
        .first()
    )
    out["spicy_beacon"] = {
        "slug": getattr(spicy_link, "slug", None),
        "hit_count": int(getattr(spicy_link, "hit_count", 0) or 0),
        "source_ref": _SPICY_SOURCE,
    }
    funnel = gate_funnel_report(db, days=14)
    spicy_rows = [
        r for r in (funnel.get("gate_funnel") or []) if (r.get("source_ref") or "") == _SPICY_SOURCE
    ]
    out["spicy_funnel_14d"] = spicy_rows[0] if spicy_rows else {"source_ref": _SPICY_SOURCE, "clicks": 0, "touches": 0}
    out["companion_margin_30d"] = companion_margin_summary(db, days=30)
    overdue = db.query(ScheduledTextPost).filter(
        ScheduledTextPost.sent_at.is_(None),
        ScheduledTextPost.interval_minutes.is_(None),
        ScheduledTextPost.scheduled_at.isnot(None),
    ).count()
    out["one_time_unsent"] = overdue
    out["stall"] = schedulers_stall_summary()
    print(json.dumps(out, default=str, indent=2))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
