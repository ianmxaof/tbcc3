"""Scrape Erome album view counts back into the upload analytics ledger."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.erome_upload_analytics import analytics_dir
from app.services.erome_upload_policy import ledger_path

logger = logging.getLogger(__name__)

_VIEW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'"views"\s*:\s*(\d+)', re.I),
    re.compile(r'class="[^"]*views[^"]*"[^>]*>\s*([\d.,]+[KkMm]?)\s*', re.I),
    re.compile(r'([\d.,]+[KkMm]?)\s*views', re.I),
    re.compile(r'<i[^>]*fa-eye[^>]*></i>\s*([\d.,]+[KkMm]?)', re.I),
)


def view_sync_enabled() -> bool:
    return (os.getenv("TBCC_EROME_VIEW_SYNC_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def view_sync_lookback_days() -> int:
    raw = (os.getenv("TBCC_EROME_VIEW_SYNC_LOOKBACK_DAYS") or "14").strip()
    try:
        return max(1, min(90, int(raw)))
    except ValueError:
        return 14


def parse_view_count(raw: str) -> int | None:
    s = (raw or "").strip().replace(",", "")
    if not s:
        return None
    mult = 1
    if s[-1].lower() == "k":
        mult = 1000
        s = s[:-1]
    elif s[-1].lower() == "m":
        mult = 1_000_000
        s = s[:-1]
    try:
        val = float(s)
    except ValueError:
        return None
    return int(val * mult)


def extract_views_from_html(html: str) -> int | None:
    for pat in _VIEW_PATTERNS:
        m = pat.search(html or "")
        if m:
            parsed = parse_view_count(m.group(1))
            if parsed is not None:
                return parsed
    return None


async def fetch_album_views(album_url: str) -> int | None:
    from app.services.crawler_resolver import _fetch_erome_album

    try:
        page, _warnings = await _fetch_erome_album(album_url)
        return extract_views_from_html(page)
    except Exception as e:
        logger.debug("erome view fetch failed %s: %s", album_url[:80], e)
        return None


def _read_ledger_rows() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_ledger_rows(rows: list[dict[str, Any]]) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def sync_ledger_views(*, max_albums: int = 40) -> dict[str, Any]:
    """Update view counts on recent successful uploads in the JSONL ledger."""
    if not view_sync_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    import asyncio

    rows = _read_ledger_rows()
    if not rows:
        return {"ok": True, "updated": 0, "scanned": 0}

    lookback_days = view_sync_lookback_days()
    cutoff = datetime.now(timezone.utc).timestamp() - lookback_days * 86400
    candidates: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(rows):
        if not row.get("ok") or not row.get("album_url"):
            continue
        ts = row.get("published_at") or row.get("recorded_at")
        if ts:
            try:
                when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when.timestamp() < cutoff:
                    continue
            except ValueError:
                pass
        candidates.append((idx, row))

    candidates = candidates[-max_albums:]
    updated = 0
    scanned = 0

    async def _run() -> None:
        nonlocal updated, scanned
        for idx, row in candidates:
            url = str(row.get("album_url") or "")
            scanned += 1
            views = await fetch_album_views(url)
            if views is None:
                continue
            prev = row.get("views_latest")
            row["views_latest"] = views
            row["views_synced_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if prev != views:
                updated += 1
            rows[idx] = row
            slug = re.sub(r"[^\w.-]+", "_", (row.get("title") or "album")[:30]).strip("_") or "album"
            manifest = analytics_dir() / f"views_{slug}.json"
            manifest.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    asyncio.run(_run())
    _write_ledger_rows(rows)
    return {"ok": True, "updated": updated, "scanned": scanned}
