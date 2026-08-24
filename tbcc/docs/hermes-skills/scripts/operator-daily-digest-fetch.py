#!/usr/bin/env python3
"""Fetch Gmail + Calendar JSON for operator-daily-digest cron.

Hermes cron on Windows cannot use bare `python` (Store stub) or ${HERMES_HOME}
(mangles to C:\\c\\Users\\...). This script always shells the known-good
interpreter that holds google-api packages + google_token.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PY = Path(r"C:\Python314\python.exe")
GW = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "skills" / "productivity" / "google-workspace" / "scripts"
GAPI = GW / "google_api.py"
GSETUP = GW / "setup.py"
TZ = ZoneInfo("America/Los_Angeles")
STATE_PATH = Path(__file__).resolve().parent / "operator-daily-digest-state.json"
PREP_GAP_MINUTES = 10  # under this gap between two timed events counts as "tight"
FOLLOW_THROUGH_WINDOW_DAYS = 14  # forget a MUST ACT fingerprint if unseen this long


def _run(args: list[str], timeout: int = 60) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    r = subprocess.run(
        [str(PY), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "").strip()
    if r.returncode != 0 and r.stderr:
        out = (out + "\n" + r.stderr.strip()).strip()
    return r.returncode, out


def _parse_json(raw: str):
    raw = raw.strip()
    if not raw or raw == "No messages found.":
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:1500]}


def _parse_event_dt(raw: str):
    """None for all-day events (date-only, no 'T') — they don't participate in
    overlap/gap math."""
    if not raw or "T" not in raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def analyze_calendar(events: list) -> dict:
    """Overlaps, tight back-to-back gaps, and tentative events — computed here
    (deterministic Python) so the digest can surface real conflicts instead of
    a static placeholder the LLM has no way to derive from raw event JSON."""
    timed: list[tuple] = []
    tentative: list[str] = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        name = e.get("summary") or "(no title)"
        if str(e.get("status") or "").lower() == "tentative":
            tentative.append(name)
        start = _parse_event_dt(e.get("start") or "")
        end = _parse_event_dt(e.get("end") or "")
        if start and end:
            timed.append((start, end, name))
    timed.sort(key=lambda t: t[0])
    overlaps: list[str] = []
    tight_gaps: list[str] = []
    for i in range(1, len(timed)):
        prev_start, prev_end, prev_name = timed[i - 1]
        start, end, name = timed[i]
        if start < prev_end:
            overlaps.append(f"{prev_name} overlaps {name}")
        else:
            gap_min = (start - prev_end).total_seconds() / 60
            if 0 <= gap_min < PREP_GAP_MINUTES:
                tight_gaps.append(f"{prev_name} -> {name} ({int(gap_min)}m gap)")
    return {"overlaps": overlaps, "tight_gaps": tight_gaps, "tentative": tentative}


def _fingerprint_message(msg: dict) -> str:
    tid = str(msg.get("threadId") or msg.get("id") or "").strip()
    if tid:
        return tid
    return f"{msg.get('from', '')}|{msg.get('subject', '')}"


def update_follow_through_state(mail: dict, today: str) -> list[dict]:
    """Track how many consecutive days each money/unread thread has reappeared
    in the fetch, so the digest can flag stale unresolved items ("day 3
    unresolved") instead of re-listing them as new every morning. State is
    rebuilt from what's actually present today — a thread that stops matching
    (resolved, archived, read) silently drops out on its own."""
    try:
        prev_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        prev_state = {}

    today_state: dict[str, dict] = {}
    for key in ("money_3d", "unread_2d"):
        for msg in (mail.get(key) or {}).get("messages") or []:
            if not isinstance(msg, dict):
                continue
            fp = _fingerprint_message(msg)
            if not fp or fp in today_state:
                continue
            prev_row = prev_state.get(fp) or {}
            today_state[fp] = {
                "subject": msg.get("subject", ""),
                "from": msg.get("from", ""),
                "first_seen": prev_row.get("first_seen", today),
            }

    try:
        STATE_PATH.write_text(json.dumps(today_state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    out: list[dict] = []
    for row in today_state.values():
        try:
            first = datetime.strptime(row["first_seen"], "%Y-%m-%d")
            days_open = (datetime.strptime(today, "%Y-%m-%d") - first).days + 1
        except Exception:
            days_open = 1
        if days_open > 1:
            out.append({"subject": row["subject"], "from": row["from"], "days_open": days_open})
    out.sort(key=lambda r: -r["days_open"])
    return out


def main() -> int:
    payload: dict = {
        "ok": False,
        "tz": "America/Los_Angeles",
        "python": str(PY),
        "gapi": str(GAPI),
    }
    if not PY.is_file():
        payload["error"] = f"missing python: {PY}"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    if not GAPI.is_file() or not GSETUP.is_file():
        payload["error"] = f"missing google-workspace scripts under {GW}"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    now = datetime.now(TZ)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(days=1)
    payload["now"] = now.isoformat()
    payload["day_start"] = day0.isoformat()
    payload["day_end"] = day1.isoformat()

    rc, auth = _run([str(GSETUP), "--check"])
    payload["auth_check"] = auth
    payload["auth_ok"] = rc == 0 and "AUTHENTICATED" in auth and "NOT_AUTHENTICATED" not in auth

    rc_cal, cal_raw = _run(
        [
            str(GAPI),
            "calendar",
            "list",
            "--start",
            day0.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "--end",
            day1.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "--max",
            "25",
        ]
    )
    payload["calendar_rc"] = rc_cal
    calendar_events = _parse_json(cal_raw)
    payload["calendar"] = calendar_events
    payload["calendar_analysis"] = analyze_calendar(
        calendar_events if isinstance(calendar_events, list) else []
    )

    searches = {
        "inbox_1d": 'in:inbox newer_than:1d -category:promotions -category:social',
        "unread_2d": "is:unread newer_than:2d",
        "starred_7d": "is:starred newer_than:7d",
        "money_3d": "(invoice OR payment OR failed OR verify OR security OR urgent OR deadline OR action required) newer_than:3d",
    }
    mail: dict = {}
    for key, q in searches.items():
        rc_m, raw = _run([str(GAPI), "gmail", "search", q, "--max", "15"])
        mail[key] = {"rc": rc_m, "messages": _parse_json(raw)}
    payload["gmail"] = mail
    payload["follow_through"] = update_follow_through_state(mail, now.strftime("%Y-%m-%d"))

    health = {"ok": None, "raw": ""}
    try:
        h = subprocess.run(
            ["curl", "-fsS", "--max-time", "8", "https://api.powercore.app/health"],
            capture_output=True,
            text=True,
            timeout=12,
        )
        health["ok"] = h.returncode == 0
        health["raw"] = (h.stdout or h.stderr or "")[:400]
    except Exception as e:
        health["ok"] = False
        health["raw"] = str(e)
    payload["island_health"] = health
    payload["ok"] = bool(payload["auth_ok"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
