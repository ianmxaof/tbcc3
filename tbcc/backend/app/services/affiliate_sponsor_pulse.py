"""Sponsor pulse + pack source_ref rollup for Analytics v2."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.data.affiliate_sponsor_packs import SPONSOR_PACKS, label_to_pack_ids, slots_for_pack
from app.services.affiliate_sponsor_report import collect_affiliate_sponsor_rows


def build_sponsor_pulse(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Pack-aware affiliate click / attributed-$ pulse for the dashboard."""
    rows = collect_affiliate_sponsor_rows(db, revenue_days=days, include_inactive=False)
    by_label = {(r.get("label") or "").strip(): r for r in rows}
    label_packs = label_to_pack_ids()

    pack_blocks: list[dict[str, Any]] = []
    for pack in SPONSOR_PACKS:
        # Use default network for lane_pps slot list in the pulse overview
        slots = slots_for_pack(pack, network_key="milf" if pack.id == "lane_pps" else None)
        slot_rows: list[dict[str, Any]] = []
        clicks_total = 0
        usd_total = 0.0
        for slot in slots:
            src = by_label.get(slot.label) or {}
            clicks = int(src.get("clicks") or 0)
            usd = float(src.get("attributed_usd") or 0.0)
            clicks_total += clicks
            usd_total += usd
            slot_rows.append(
                {
                    "index": slot.index,
                    "label": slot.label,
                    "role": slot.role,
                    "active": bool(src.get("active")) if src else False,
                    "clicks": clicks,
                    "attributed_usd": usd,
                    "priority_tier": src.get("priority_tier"),
                    "placements": src.get("placements") or [],
                }
            )
        pack_blocks.append(
            {
                "id": pack.id,
                "title": pack.title,
                "lane": pack.lane,
                "surfaces": list(pack.surfaces),
                "clicks": clicks_total,
                "attributed_usd": round(usd_total, 4),
                "slots": slot_rows,
            }
        )

    # Orphans: active sponsors not in any pack
    pack_labels = set(label_packs.keys())
    orphans = [
        {
            "label": r.get("label"),
            "clicks": int(r.get("clicks") or 0),
            "attributed_usd": float(r.get("attributed_usd") or 0.0),
            "priority_tier": r.get("priority_tier"),
        }
        for r in rows
        if (r.get("label") or "").strip() not in pack_labels
    ]
    orphans.sort(key=lambda x: (-x["clicks"], -x["attributed_usd"], x.get("label") or ""))

    return {
        "ok": True,
        "days": days,
        "packs": pack_blocks,
        "orphan_sponsors": orphans[:40],
        "sponsor_count": len(rows),
    }
