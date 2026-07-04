"""Suggest Erome titles/tags from analytics ledger winners."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from app.services.erome_upload_policy import ledger_path


def _ledger_rows() -> list[dict[str, Any]]:
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
        if isinstance(row, dict) and row.get("ok"):
            rows.append(row)
    return rows


def suggest_erome_post(
    *,
    network_key: str | None = None,
    format_hint: str | None = None,
) -> dict[str, Any]:
    """
    Return title template + tag list from best-performing ledger rows.
    Uses views_latest when synced; otherwise recent successful uploads.
    """
    rows = _ledger_rows()
    if network_key:
        nk = network_key.strip().lower()
        filtered = [r for r in rows if str(r.get("network_key") or "").lower() == nk]
        if filtered:
            rows = filtered

    if format_hint:
        fh = format_hint.strip().lower()
        by_fmt = [
            r
            for r in rows
            if str((r.get("staging_meta") or {}).get("format_hint") or "").lower() == fh
        ]
        if by_fmt:
            rows = by_fmt

    def _score(row: dict[str, Any]) -> int:
        views = row.get("views_latest")
        try:
            return int(views) if views is not None else 0
        except (TypeError, ValueError):
            return 0

    rows.sort(key=_score, reverse=True)
    top = rows[:5]
    if not top:
        return {
            "ok": False,
            "error": "no_ledger_rows",
            "title": "Vietnamese MILF jiggly big boobs ready for sex",
            "tags": ["milf", "webcam", "big tits", "latina", "full body"],
            "notes": "Default template — upload once to seed the ledger.",
        }

    tag_counter: Counter[str] = Counter()
    titles: list[str] = []
    for row in top:
        title = str(row.get("title") or "").strip()
        if title and "@" not in title and not title[:8].isdigit():
            titles.append(title)
        for tag in row.get("tags") or []:
            t = str(tag).strip().lower()
            if t:
                tag_counter[t] += 1 + (_score(row) // 100)

    best_title = titles[0] if titles else str(top[0].get("title") or "")
    tags = [t for t, _ in tag_counter.most_common(8)]
    meta = top[0].get("staging_meta") or {}
    notes_parts = []
    if meta.get("primary_duration_sec"):
        notes_parts.append(f"~{int(meta['primary_duration_sec'])}s video")
    if meta.get("format_hint"):
        notes_parts.append(str(meta["format_hint"]))

    return {
        "ok": True,
        "title": best_title[:120],
        "tags": tags,
        "content_notes": ", ".join(notes_parts) or None,
        "based_on_views": _score(top[0]),
        "sample_count": len(top),
    }
