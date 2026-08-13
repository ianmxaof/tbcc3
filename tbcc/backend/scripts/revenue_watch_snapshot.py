#!/usr/bin/env python3
"""
Weekly revenue watch — spicy funnel + companion margin + loot lane depth.

Run on island (canonical):
  cd /opt/tbcc/backend && python scripts/revenue_watch_snapshot.py

Cadence: Mon + Thu through 2026-08-07, then weekly. Compare spicy_beacon.hit_count
and spicy_funnel_14d.touches vs prior run; companion_margin_30d.photos_sold > 0 = win.
Kill rule Aug 7: spicy clicks still 0 → TBCC_BUFFER_X_SPICY_BIAS_EVERY=2.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.models.click_link import ClickLink
from app.models.user_funnel_touch import UserFunnelTouch
from app.services.companion_cogs import companion_margin_summary
from app.services.gate_funnel import gate_funnel_report
from app.services.lane_survivor_refill import build_lane_survivor_refill_plan

_SPICY_SOURCE = "src_aff_aof_spicy_companion_x_buffer"
_WATCH_UNTIL = "2026-08-07"


def main() -> int:
    db = SessionLocal()
    try:
        spicy_link = (
            db.query(ClickLink)
            .filter(ClickLink.source_ref == _SPICY_SOURCE)
            .order_by(ClickLink.id.desc())
            .first()
        )
        funnel = gate_funnel_report(db, days=14)
        spicy_rows = [
            r for r in (funnel.get("gate_funnel") or []) if (r.get("source_ref") or "") == _SPICY_SOURCE
        ]
        plan, probe_ids = build_lane_survivor_refill_plan(db, target=60, probe_cap=120)
        thin_lanes = {
            k: {
                "approved": v.approved,
                "need": v.need,
                "local_recoverable": len(v.local),
                "posted_probe": len(v.saved),
            }
            for k, v in plan.items()
            if v.need > 0
        }
        total_need = sum(int(v.need) for v in plan.values())

        out = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "watch_until": _WATCH_UNTIL,
            "touches_total": db.query(UserFunnelTouch).count(),
            "spicy_beacon": {
                "slug": getattr(spicy_link, "slug", None),
                "hit_count": int(getattr(spicy_link, "hit_count", 0) or 0),
                "source_ref": _SPICY_SOURCE,
            },
            "spicy_funnel_14d": spicy_rows[0] if spicy_rows else {"clicks": 0, "touches": 0},
            "companion_margin_30d": companion_margin_summary(db, days=30),
            "loot_lanes_thin": thin_lanes,
            "loot_approved_gap_total": total_need,
            "loot_probe_refs": len(probe_ids),
            "next": {
                "loot": "python scripts/loot_durability_check.py [--apply-refill]",
                "spicy_kill_aug7": "if hit_count==0: set TBCC_BUFFER_X_SPICY_BIAS_EVERY=2 on island",
            },
        }
        print(json.dumps(out, default=str, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
