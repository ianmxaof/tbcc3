"""Undress affiliate traffic stats for surge threshold tuning. Run from tbcc/backend."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy import func

from app.database.session import SessionLocal
from app.models.click_link import ClickLink, ClickLinkHit
from app.services.undress_surge import is_undress_signal, spike_state, undress_spike_hit_threshold


def main() -> None:
    days = 7
    since = datetime.now(timezone.utc) - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (
            db.query(ClickLink.source_ref, ClickLink.label, func.count(ClickLinkHit.id))
            .join(ClickLinkHit, ClickLinkHit.link_id == ClickLink.id)
            .filter(ClickLinkHit.created_at >= since)
            .group_by(ClickLink.source_ref, ClickLink.label)
            .order_by(func.count(ClickLinkHit.id).desc())
            .all()
        )
        undress_rows = [
            (ref, label, cnt)
            for ref, label, cnt in rows
            if is_undress_signal(source_ref=ref, link_label=label)
        ]
        total_undress = sum(c for _, _, c in undress_rows)
        windows_30m = days * 24 * 2
        avg_per_window = total_undress / windows_30m if windows_30m else 0

        try:
            from app.services.admin_inbox import _redis_client
            from app.services.traffic_pulse import REDIS_DIGEST_REFS

            refs = _redis_client().hgetall(REDIS_DIGEST_REFS) or {}
            pulse_undress = {
                str(k): int(v)
                for k, v in refs.items()
                if is_undress_signal(source_ref=str(k))
            }
        except Exception:
            pulse_undress = {}

        out = {
            "window_days": days,
            "beacon_hits_undress_labeled": total_undress,
            "avg_hits_per_30min_window_naive": round(avg_per_window, 3),
            "recommended_spike_threshold": max(3, min(12, int(round(avg_per_window * 2.5)) or 4)),
            "current_env_threshold": undress_spike_hit_threshold(),
            "current_spike_state": spike_state(),
            "top_undress_refs": [
                {"source_ref": r, "label": l, "hits": c} for r, l, c in undress_rows[:15]
            ],
            "traffic_pulse_undress_refs": pulse_undress,
            "note": (
                "Surge also counts affiliate_served + beacon pulse hooks in Redis (30m sliding window). "
                "Enable TBCC_AFFILIATE_BEACON_WRAP=1 for measurable undress refs."
            ),
        }
        print(json.dumps(out, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
