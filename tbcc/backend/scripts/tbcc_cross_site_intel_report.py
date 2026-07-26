#!/usr/bin/env python3
"""
Cross-site browse-intel revenue report (Erome / ThisVid / Motherless).

Reads the unified ledger at tbcc/.tbcc-run/erome-analytics/browse-intel.jsonl,
prints coverage + overlaps + AOF lane hits, and ranks actionable next moves.

Examples (from tbcc/backend):

  py -3.13 scripts/tbcc_cross_site_intel_report.py
  py -3.13 scripts/tbcc_cross_site_intel_report.py --days 30 --top 15
  py -3.13 scripts/tbcc_cross_site_intel_report.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

SITES = ("erome", "thisvid", "motherless")


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _row_platform(row: dict[str, Any]) -> str:
    return str(row.get("platform") or "erome").strip().lower() or "erome"


def _row_tags(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for t in row.get("tags") or []:
        s = str(t).strip().lower()
        if s:
            out.append(s)
    return out


def _views(row: dict[str, Any]) -> float | None:
    try:
        v = row.get("views")
        if v is not None and int(v) > 0:
            return float(int(v))
    except (TypeError, ValueError):
        pass
    return None


def coverage_block(rows: list[dict[str, Any]], *, days: int, ledger: Path) -> dict[str, Any]:
    by_plat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_plat[_row_platform(r)].append(r)

    ts_all = [_parse_ts(r.get("captured_at")) for r in rows]
    ts_ok = [t for t in ts_all if t]
    ts_ok.sort()

    platforms: dict[str, Any] = {}
    for p in SITES:
        subset = by_plat.get(p, [])
        n = len(subset)
        with_views = sum(1 for r in subset if _views(r) is not None)
        with_tags = sum(1 for r in subset if _row_tags(r))
        with_up = sum(1 for r in subset if str(r.get("uploader") or "").strip())
        platforms[p] = {
            "rows": n,
            "pct_with_views": _pct(with_views, n),
            "pct_with_tags": _pct(with_tags, n),
            "pct_with_uploader": _pct(with_up, n),
        }

    other = {k: len(v) for k, v in by_plat.items() if k not in SITES}
    return {
        "lookback_days": days,
        "ledger_path": str(ledger),
        "total_rows": len(rows),
        "captured_from": ts_ok[0].isoformat() if ts_ok else None,
        "captured_to": ts_ok[-1].isoformat() if ts_ok else None,
        "platforms": platforms,
        "other_platforms": other,
    }


def per_site_block(rows: list[dict[str, Any]], *, top: int) -> dict[str, Any]:
    from app.services.erome_browse_intel import aggregate_format_scores, aggregate_tag_scores

    out: dict[str, Any] = {}
    for p in SITES:
        subset = [r for r in rows if _row_platform(r) == p]
        tag_scores = aggregate_tag_scores(subset, platform=p)
        fmt_scores = aggregate_format_scores(subset)
        views = [v for r in subset if (v := _views(r)) is not None]
        eng = []
        for r in subset:
            try:
                e = int(r.get("engagement_bps") or 0)
                if e > 0:
                    eng.append(float(e))
            except (TypeError, ValueError):
                pass
        uploaders = Counter(
            str(r.get("uploader") or "").strip().lower()
            for r in subset
            if str(r.get("uploader") or "").strip()
            and str(r.get("uploader") or "").strip().lower() not in ("feed", "unknown", "null")
        )
        note = None
        if p == "motherless":
            note = "RSS-first: views/likes often null; tag scores use soft proxies"
        elif p == "thisvid":
            note = "Grid intel: likes often null; duration tags (dur_*) and public/private matter"
        out[p] = {
            "rows": len(subset),
            "median_views": round(_median(views) or 0, 1) if views else None,
            "median_engagement_bps": round(_median(eng) or 0, 1) if eng else None,
            "top_tags": [
                {"tag": t, "score": round(s, 1)}
                for t, s in sorted(tag_scores.items(), key=lambda x: -x[1])[:top]
            ],
            "format_scores": {
                k: round(v, 1) for k, v in sorted(fmt_scores.items(), key=lambda x: -x[1])[:top]
            },
            "top_uploaders": [{"uploader": u, "count": c} for u, c in uploaders.most_common(top)],
            "note": note,
        }
    return out


def connections_block(rows: list[dict[str, Any]], *, top: int) -> dict[str, Any]:
    tag_plats: dict[str, set[str]] = defaultdict(set)
    tag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    uploader_plats: dict[str, set[str]] = defaultdict(set)
    fmt_plats: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        p = _row_platform(r)
        if p not in SITES:
            continue
        for t in _row_tags(r):
            tag_plats[t].add(p)
            tag_counts[t][p] += 1
        up = str(r.get("uploader") or "").strip().lower()
        if up and up not in ("feed", "unknown", "null"):
            uploader_plats[up].add(p)
        fb = str(r.get("format_bucket") or "").strip().lower()
        if fb:
            fmt_plats[fb].add(p)

    multi_tags = []
    for t, plats in tag_plats.items():
        if len(plats) < 2:
            continue
        multi_tags.append(
            {
                "tag": t,
                "platforms": sorted(plats),
                "platform_count": len(plats),
                "counts": dict(tag_counts[t]),
                "total": sum(tag_counts[t].values()),
            }
        )
    multi_tags.sort(key=lambda x: (-x["platform_count"], -x["total"], x["tag"]))

    shared_uploaders = [
        {"uploader": u, "platforms": sorted(ps)}
        for u, ps in uploader_plats.items()
        if len(ps) >= 2
    ]
    shared_uploaders.sort(key=lambda x: (-len(x["platforms"]), x["uploader"]))

    # Formats that win on Erome (by median views) and also appear elsewhere
    from app.services.erome_browse_intel import aggregate_format_scores

    erome_rows = [r for r in rows if _row_platform(r) == "erome"]
    erome_fmt = aggregate_format_scores(erome_rows)
    cross_formats = []
    for fb, score in sorted(erome_fmt.items(), key=lambda x: -x[1]):
        plats = fmt_plats.get(fb, set())
        others = sorted(plats - {"erome"})
        if others:
            cross_formats.append(
                {
                    "format_bucket": fb,
                    "erome_median_views": round(score, 1),
                    "also_on": others,
                }
            )

    return {
        "cross_site_tags": multi_tags[: max(top * 2, 30)],
        "shared_uploaders": shared_uploaders[:top],
        "erome_winning_formats_also_elsewhere": cross_formats[:top],
    }


def lane_map_block(rows: list[dict[str, Any]], *, top: int) -> dict[str, Any]:
    from app.services.aof_lane_tag_map import LANE_TAG_MAP, lane_display_name, normalize_lane_key
    from app.services.erome_browse_intel import aggregate_tag_scores

    tag_scores = aggregate_tag_scores(rows)
    tag_plats: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        p = _row_platform(r)
        if p not in SITES:
            continue
        for t in _row_tags(r):
            tag_plats[t].add(p)

    lane_score: dict[str, float] = defaultdict(float)
    lane_tags: dict[str, set[str]] = defaultdict(set)
    lane_plats: dict[str, set[str]] = defaultdict(set)

    for tag, score in tag_scores.items():
        keys = LANE_TAG_MAP.get(tag)
        if not keys:
            for frag, mapped in LANE_TAG_MAP.items():
                if frag in tag or tag in frag:
                    keys = mapped
                    break
        if not keys:
            continue
        for k in keys:
            nk = normalize_lane_key(k)
            if not nk:
                continue
            lane_score[nk] += float(score)
            lane_tags[nk].add(tag)
            lane_plats[nk] |= tag_plats.get(tag, set())

    lanes = []
    for key, sc in sorted(lane_score.items(), key=lambda x: -x[1]):
        plats = sorted(lane_plats[key] & set(SITES))
        lanes.append(
            {
                "lane": key,
                "display": lane_display_name(key),
                "score": round(sc, 1),
                "platforms": plats,
                "multi_site": len(plats) >= 2,
                "sample_tags": sorted(lane_tags[key])[:8],
            }
        )
    return {
        "lanes": lanes[:top],
        "multi_site_lanes": [x for x in lanes if x["multi_site"]][:top],
    }


def revenue_actions(
    *,
    coverage: dict[str, Any],
    per_site: dict[str, Any],
    connections: dict[str, Any],
    lanes: dict[str, Any],
    upload_hints: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    # 1) Erome upload — highest direct discovery → gate traffic
    top_tags = upload_hints.get("top_tags") or []
    sat = set(upload_hints.get("saturated_tags") or [])
    clean = [t["tag"] for t in top_tags if t.get("tag") not in sat][:6]
    pref_fmt = upload_hints.get("preferred_format_bucket")
    if clean:
        actions.append(
            {
                "priority": 1,
                "impact": "high",
                "title": "Erome upload pack on winning tags",
                "why": (
                    f"Erome intel row_count={upload_hints.get('row_count', 0)}; "
                    f"top tags {', '.join(clean[:5])}"
                    + (f"; prefer format={pref_fmt}" if pref_fmt else "")
                    + (f"; avoid saturated {', '.join(sorted(sat)[:4])}" if sat else "")
                ),
                "how": (
                    "Build/upload an Erome album matching preferred_format_bucket; "
                    "title+tags from clean top tags only; watermark → AOF gate CTA "
                    "(@aof_lootgod_bot / telegram.me/aofmainhub). Skip FetLife analytics."
                ),
            }
        )

    # 2) Cross-site confirmed AOF lanes → watch folders / shop
    #    (fall back to top single-site lane when ThisVid/ML not yet pushed)
    multi = lanes.get("multi_site_lanes") or []
    all_lanes = lanes.get("lanes") or []
    top_lane = (multi[0] if multi else None) or (all_lanes[0] if all_lanes else None)
    if top_lane:
        confirmed = "multi-site" if top_lane.get("multi_site") else "Erome-only (await ThisVid/ML push)"
        actions.append(
            {
                "priority": 2,
                "impact": "high" if top_lane.get("multi_site") else "medium",
                "title": f"Prioritize AOF lane: {top_lane.get('display') or top_lane.get('lane')}",
                "why": (
                    f"Lane score={top_lane.get('score')} ({confirmed}) on "
                    f"{', '.join(top_lane.get('platforms') or [])}; "
                    f"tags={', '.join((top_lane.get('sample_tags') or [])[:5])}"
                ),
                "how": (
                    f"Route watch-folder Save AOF + loot pool seed toward lane "
                    f"`{top_lane.get('lane')}`; schedule VIP/X promo from that lane's library."
                ),
            }
        )

    # 3) Loot / X promo from high engagement Erome + ThisVid duration
    erome = per_site.get("erome") or {}
    thisvid = per_site.get("thisvid") or {}
    erome_tags = [t["tag"] for t in (erome.get("top_tags") or [])[:8]]
    tv_dur = [t["tag"] for t in (thisvid.get("top_tags") or []) if str(t.get("tag", "")).startswith("dur_")][
        :4
    ]
    if erome_tags:
        actions.append(
            {
                "priority": 3,
                "impact": "high",
                "title": "Loot / X promo cluster",
                "why": (
                    f"Erome median engagement_bps={erome.get('median_engagement_bps')}; "
                    f"tags={', '.join(erome_tags[:5])}"
                    + (f"; ThisVid duration bands={', '.join(tv_dur)}" if tv_dur else "")
                ),
                "how": (
                    "Pick 1–2 R2 library clips matching those tags; Gemini/Perchance loot card; "
                    "Buffer queue to wizardstick69 / PowerCoreAi with loot CTA only "
                    "(telegram.me/aof_lootgod_bot)."
                ),
            }
        )

    # 4) Cross-site tag overlaps → scrape / pack themes
    cross = connections.get("cross_site_tags") or []
    triple = [c for c in cross if c.get("platform_count", 0) >= 3][:5]
    dual = [c for c in cross if c.get("platform_count", 0) == 2][:8]
    pick = triple or dual
    if pick:
        tag_list = ", ".join(c["tag"] for c in pick[:6])
        actions.append(
            {
                "priority": 4,
                "impact": "medium",
                "title": "Scrape / mega-pack theme from cross-site tags",
                "why": f"Tags on ≥2 sites: {tag_list}",
                "how": (
                    "Extension Scan+Push on ThisVid/Motherless for those tags; "
                    "Erome Push liked/search; seed a named mega-pack for shop Stars."
                ),
            }
        )

    # 5) Coverage gap — thinnest of the three
    plats = coverage.get("platforms") or {}
    thinnest = min(SITES, key=lambda p: int((plats.get(p) or {}).get("rows") or 0))
    thin_n = int((plats.get(thinnest) or {}).get("rows") or 0)
    richest = max(SITES, key=lambda p: int((plats.get(p) or {}).get("rows") or 0))
    rich_n = int((plats.get(richest) or {}).get("rows") or 0)
    if thin_n < max(50, rich_n // 4):
        how_map = {
            "erome": "Open Erome → Intel/transport Push to /analytics/erome-browse-intel",
            "thisvid": "ThisVid Intel tab → Scan grid + Push",
            "motherless": "Motherless RSS tab → Load feeds + Push",
        }
        actions.append(
            {
                "priority": 5,
                "impact": "medium",
                "title": f"Fill intel gap: {thinnest}",
                "why": f"{thinnest} has {thin_n} rows vs {richest}={rich_n} in lookback",
                "how": how_map.get(thinnest, "Push more browse-intel rows for that platform"),
            }
        )

    # 6) Explicit skip
    actions.append(
        {
            "priority": 6,
            "impact": "skip",
            "title": "Do not scrape FetLife /analytics",
            "why": "SITE_INTEL_FRONTIER_PROMPTS: FetLife is NO-GO for browse-intel ingest",
            "how": "Keep FetLife suite for UX only; revenue path stays Erome/ThisVid/Motherless → AOF",
        }
    )

    # Re-rank: keep listed priority; ensure high-impact first already ordered
    actions.sort(key=lambda a: (0 if a["impact"] == "high" else 1 if a["impact"] == "medium" else 2, a["priority"]))
    for i, a in enumerate(actions, 1):
        a["rank"] = i
    return actions


def build_report(*, days: int, top: int) -> dict[str, Any]:
    from app.services.erome_browse_intel import ledger_path, load_recent_rows
    from app.services.erome_upload_policy import intel_upload_hints

    rows = load_recent_rows(days=days)
    # Keep primary three + note others
    cov = coverage_block(rows, days=days, ledger=ledger_path())
    per = per_site_block(rows, top=top)
    conn = connections_block(rows, top=top)
    lanes = lane_map_block(rows, top=top)
    hints = intel_upload_hints(top_n=top)
    actions = revenue_actions(
        coverage=cov,
        per_site=per,
        connections=conn,
        lanes=lanes,
        upload_hints=hints,
    )
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": cov,
        "per_site": per,
        "connections": conn,
        "aof_lanes": lanes,
        "erome_upload_hints": hints,
        "revenue_actions": actions,
    }


def _fmt_tag_list(items: list[dict[str, Any]], *, score_key: str = "score") -> str:
    if not items:
        return "(none)"
    parts = []
    for it in items:
        if score_key in it:
            parts.append(f"{it.get('tag') or it.get('uploader')} ({it[score_key]})")
        elif "count" in it:
            parts.append(f"{it.get('uploader') or it.get('tag')}×{it['count']}")
        else:
            parts.append(str(it.get("tag") or it))
    return ", ".join(parts)


def render_markdown(report: dict[str, Any]) -> str:
    cov = report["coverage"]
    lines: list[str] = []
    lines.append("# Cross-site browse-intel revenue report")
    lines.append("")
    lines.append(f"Generated: `{report.get('generated_at')}`")
    lines.append(f"Ledger: `{cov.get('ledger_path')}`")
    lines.append(f"Lookback: **{cov.get('lookback_days')}** days · rows **{cov.get('total_rows')}**")
    if cov.get("captured_from"):
        lines.append(f"Captured range: `{cov['captured_from']}` → `{cov['captured_to']}`")
    lines.append("")

    lines.append("## 1. Coverage")
    lines.append("")
    lines.append("| Platform | Rows | % views | % tags | % uploader |")
    lines.append("|---|---:|---:|---:|---:|")
    for p in SITES:
        pl = (cov.get("platforms") or {}).get(p) or {}
        lines.append(
            f"| {p} | {pl.get('rows', 0)} | {pl.get('pct_with_views', 0)} | "
            f"{pl.get('pct_with_tags', 0)} | {pl.get('pct_with_uploader', 0)} |"
        )
    other = cov.get("other_platforms") or {}
    if other:
        lines.append("")
        lines.append(f"Other platforms in ledger: `{other}`")
    lines.append("")

    lines.append("## 2. Per-site")
    lines.append("")
    for p in SITES:
        site = (report.get("per_site") or {}).get(p) or {}
        lines.append(f"### {p}")
        if site.get("note"):
            lines.append(f"_{site['note']}_")
        lines.append(
            f"- rows={site.get('rows')} · median_views={site.get('median_views')} · "
            f"median_engagement_bps={site.get('median_engagement_bps')}"
        )
        lines.append(f"- top tags: {_fmt_tag_list(site.get('top_tags') or [])}")
        fmts = site.get("format_scores") or {}
        if fmts:
            lines.append("- formats: " + ", ".join(f"{k} ({v})" for k, v in fmts.items()))
        lines.append(f"- top uploaders: {_fmt_tag_list(site.get('top_uploaders') or [])}")
        lines.append("")

    lines.append("## 3. Connections")
    lines.append("")
    conn = report.get("connections") or {}
    lines.append("### Cross-site tags (≥2 platforms)")
    lines.append("")
    for c in (conn.get("cross_site_tags") or [])[:20]:
        lines.append(
            f"- **{c['tag']}** on {', '.join(c['platforms'])} "
            f"(n={c['total']}, {c['counts']})"
        )
    if not conn.get("cross_site_tags"):
        lines.append("- (none yet — push more ThisVid/Motherless intel)")
    lines.append("")
    lines.append("### Shared uploaders")
    lines.append("")
    for u in conn.get("shared_uploaders") or []:
        lines.append(f"- `{u['uploader']}` → {', '.join(u['platforms'])}")
    if not conn.get("shared_uploaders"):
        lines.append("- (none)")
    lines.append("")
    lines.append("### Erome-winning formats also on other sites")
    lines.append("")
    for f in conn.get("erome_winning_formats_also_elsewhere") or []:
        lines.append(
            f"- **{f['format_bucket']}** erome_median_views={f['erome_median_views']} "
            f"also_on={', '.join(f['also_on'])}"
        )
    if not conn.get("erome_winning_formats_also_elsewhere"):
        lines.append("- (none)")
    lines.append("")

    lines.append("## 4. AOF lane map")
    lines.append("")
    for ln in (report.get("aof_lanes") or {}).get("lanes") or []:
        flag = " **[multi-site]**" if ln.get("multi_site") else ""
        lines.append(
            f"- **{ln.get('display')}** (`{ln.get('lane')}`) score={ln.get('score')} "
            f"platforms={', '.join(ln.get('platforms') or [])}{flag}"
        )
        if ln.get("sample_tags"):
            lines.append(f"  - tags: {', '.join(ln['sample_tags'])}")
    lines.append("")

    lines.append("## 5. Revenue actions (highest impact first)")
    lines.append("")
    for a in report.get("revenue_actions") or []:
        lines.append(f"### {a.get('rank')}. [{a.get('impact')}] {a.get('title')}")
        lines.append(f"- **Why:** {a.get('why')}")
        lines.append(f"- **How:** {a.get('how')}")
        lines.append("")

    hints = report.get("erome_upload_hints") or {}
    if hints.get("top_tags"):
        lines.append("## Appendix — Erome upload hints")
        lines.append("")
        lines.append(f"- preferred_format: `{hints.get('preferred_format_bucket')}`")
        lines.append(f"- top tags: {_fmt_tag_list(hints.get('top_tags') or [])}")
        if hints.get("saturated_tags"):
            lines.append(f"- saturated: {', '.join(hints['saturated_tags'])}")
        lines.append("")

    return "\n".join(lines)


def render_text(report: dict[str, Any]) -> str:
    # Same content as markdown; terminals render fine without a separate format.
    return render_markdown(report)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-site browse-intel revenue report")
    ap.add_argument("--days", type=int, default=30, help="Lookback days (default 30)")
    ap.add_argument("--top", type=int, default=15, help="Top-N lists (default 15)")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    ap.add_argument(
        "--out",
        default=None,
        help="Write markdown snapshot (default: analytics dir cross-site-intel-report.md)",
    )
    ap.add_argument("--no-write", action="store_true", help="Do not write markdown file")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from app.services.erome_browse_intel import ledger_path
    from app.services.erome_upload_analytics import analytics_dir

    report = build_report(days=max(1, args.days), top=max(3, args.top))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        text = render_text(report)
        print(text)

    if not args.no_write:
        out = Path(args.out) if args.out else (analytics_dir() / "cross-site-intel-report.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(report), encoding="utf-8")
        if not args.json:
            print(f"\n— wrote {out}")
            print(f"— ledger {ledger_path()}")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
