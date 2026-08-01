#!/usr/bin/env python3
"""Consolidated TBCC ops picture — point-in-time JSON for /ops-picture protocol."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal
from app.services.ops_picture_report import build_ops_picture_report
from app.services.ops_alerts import HIGH_SIGNAL_HUB, _classify_hub_line, _error_hub_path, _is_irregular_hub_line


def _read_error_hub_tail(*, max_lines: int = 120, max_alerts: int = 12) -> dict:
    path = _error_hub_path()
    if not path.is_file():
        return {
            "available": False,
            "path": str(path),
            "alerts": [],
            "note": "error-hub.log not on this host (island: use docker logs)",
        }
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return {"available": False, "path": str(path), "error": str(e)[:200], "alerts": []}
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    alerts: list[dict] = []
    for i, line in enumerate(tail):
        if not line.strip():
            continue
        matched = False
        for pat, code, sev, title in HIGH_SIGNAL_HUB:
            if pat.search(line):
                alerts.append(
                    {
                        "severity": sev,
                        "code": code,
                        "title": title,
                        "line": line[-400:],
                        "line_no": len(lines) - len(tail) + i + 1,
                    }
                )
                matched = True
                break
        if not matched and _is_irregular_hub_line(line):
            classified = _classify_hub_line(line)
            code, sev, title = classified if classified else ("error_hub", "warning", "Error hub")
            alerts.append(
                {
                    "severity": sev,
                    "code": code,
                    "title": title,
                    "line": line[-400:],
                    "line_no": len(lines) - len(tail) + i + 1,
                }
            )
    seen: set[str] = set()
    deduped: list[dict] = []
    for a in reversed(alerts):
        key = a["line"][-120:]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    deduped.reverse()
    return {
        "available": True,
        "path": str(path),
        "total_lines": len(lines),
        "tail_scanned": len(tail),
        "alerts": deduped[-max_alerts:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--post-import-days", type=int, default=7)
    parser.add_argument("--backfill", action="store_true", help="Run subscription income backfill before snapshot")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = build_ops_picture_report(
            db,
            days=args.days,
            post_import_days=args.post_import_days,
            backfill_income=args.backfill,
        )
    finally:
        db.close()

    report["error_hub"] = _read_error_hub_tail()
    print(json.dumps(report, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
