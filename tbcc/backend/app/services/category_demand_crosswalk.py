"""Category demand (industry priors) vs AOF supply (tagged media) crosswalk."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.industry_benchmark import IndustryBenchmark
from app.models.media import Media
from app.models.tbcc_tag import MediaTagLink, TbccTag

_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CLIP_CATEGORIES = _TBCC_ROOT / "data" / "clip-categories.json"


def _load_clip_categories() -> list[dict[str, Any]]:
    if not _CLIP_CATEGORIES.is_file():
        return []
    data = json.loads(_CLIP_CATEGORIES.read_text(encoding="utf-8"))
    return list(data.get("categories") or [])


def _category_aliases(cat: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    slug = str(cat.get("slug") or "").strip().lower()
    if slug:
        aliases.add(slug)
    name = str(cat.get("name") or "").strip().lower()
    if name:
        aliases.add(name)
        aliases.add(name.replace(" ", "-"))
    for p in cat.get("prompts") or []:
        p = str(p).strip().lower()
        if p:
            aliases.add(p)
            aliases.add(p.replace(" ", "-"))
    return aliases


def _supply_counts(db: Session) -> dict[str, int]:
    """Map normalized tag slug/name -> distinct media count."""
    rows = (
        db.query(TbccTag.slug, TbccTag.name, func.count(MediaTagLink.media_id.distinct()))
        .join(MediaTagLink, MediaTagLink.tag_id == TbccTag.id)
        .group_by(TbccTag.slug, TbccTag.name)
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for slug, name, cnt in rows:
        for key in (slug, name):
            k = str(key or "").strip().lower()
            if k:
                counts[k] += int(cnt or 0)
                counts[k.replace(" ", "-")] += int(cnt or 0)
    return counts


def _total_media(db: Session) -> int:
    return int(db.query(func.count(Media.id)).scalar() or 0)


def compute_category_demand_crosswalk(
    db: Session,
    *,
    limit: int = 40,
    gap_threshold: float = 15.0,
) -> dict[str, Any]:
    """
    Crosswalk industry demand_index (benchmarks) against tagged media supply.
    Returns opportunity gaps where demand exceeds normalized supply.
    """
    benchmarks = (
        db.query(IndustryBenchmark)
        .filter(
            IndustryBenchmark.is_active.is_(True),
            IndustryBenchmark.topic_type == "category",
            IndustryBenchmark.demand_index.isnot(None),
        )
        .order_by(IndustryBenchmark.demand_index.desc())
        .all()
    )
    if not benchmarks:
        return {
            "ok": True,
            "seeded": False,
            "message": "No category benchmarks in DB — run POST /analytics/industry-benchmarks/seed",
            "rows": [],
            "gaps": [],
        }

    supply = _supply_counts(db)
    total_media = max(_total_media(db), 1)
    clip_cats = {str(c.get("slug") or ""): c for c in _load_clip_categories()}

    rows: list[dict[str, Any]] = []
    for bench in benchmarks:
        slug = bench.slug.lower()
        aliases = {slug, slug.replace("_", "-")}
        cat = clip_cats.get(slug) or clip_cats.get(slug.replace("-", "_"))
        if cat:
            aliases |= _category_aliases(cat)

        supply_count = 0
        for alias in aliases:
            supply_count = max(supply_count, supply.get(alias, 0))

        supply_pct = round(100.0 * supply_count / total_media, 2)
        demand = float(bench.demand_index or 0)
        gap_score = round(demand - supply_pct, 2)
        status = "balanced"
        if gap_score >= gap_threshold:
            status = "under_supplied"
        elif supply_pct > demand + gap_threshold:
            status = "over_supplied"

        rows.append(
            {
                "slug": bench.slug,
                "title": bench.title,
                "demand_index": demand,
                "supply_count": supply_count,
                "supply_pct": supply_pct,
                "gap_score": gap_score,
                "status": status,
                "in_clip_catalog": cat is not None,
                "summary": bench.summary,
            }
        )

    rows.sort(key=lambda x: (-float(x["gap_score"]), -float(x["demand_index"])))
    gaps = [r for r in rows if r["status"] == "under_supplied"][:limit]

    return {
        "ok": True,
        "seeded": True,
        "total_media": total_media,
        "benchmark_count": len(benchmarks),
        "gap_threshold": gap_threshold,
        "rows": rows[:limit],
        "gaps": gaps[:15],
        "top_opportunities": gaps[:5],
    }
