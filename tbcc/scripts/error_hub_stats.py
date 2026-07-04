"""
TBCC Error Hub analytics.

What it does:
- Parses tbcc/.tbcc-run/error-hub.log lines into (service, error-kind) buckets.
- Produces a per-session summary (counts + top kinds).
- Optionally appends aggregated results into tbcc/.tbcc-run/error-hub-history.jsonl
  so you can rank “persistent” error kinds across sessions.

Run:
  python tbcc/scripts/error_hub_stats.py
  python tbcc/scripts/error_hub_stats.py --log tbcc/.tbcc-run/error-hub.log
  python tbcc/scripts/error_hub_stats.py --update-history
  python tbcc/scripts/error_hub_stats.py --rank --top 10
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


HUB_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<service>[^\]]+)\]\s+\[(?P<level>[^\]]+)\]\s+(?P<body>.*)$"
)


@dataclass(frozen=True)
class Bucket:
    kind: str
    detail: str | None = None


MISSING_TBCC_VAR_RE = re.compile(r"TBCC_([A-Z0-9_]+)='([^']+)' not found")


def _infer_bucket(body: str) -> Bucket | None:
    """
    Map a hub log 'body' to a stable 'kind' bucket.
    We intentionally ignore raw 'Traceback' lines to avoid double-counting.
    """
    b = body.strip()

    # Skip raw tracebacks unless they contain one of the patterns we care about.
    if "Traceback" in b and not re.search(r"(502 Bad Gateway|database is locked|WinError 121|not found)", b, re.I):
        return None

    # Config / env value missing (often co-occurs with unrelated access-log noise)
    if re.search(r"TBCC_.*not found", b):
        m = MISSING_TBCC_VAR_RE.search(b)
        if m:
            var_name = m.group(1)
            return Bucket(kind="missing_config_value", detail=f"Missing TBCC_{var_name}")
        return Bucket(kind="missing_config_value", detail="Missing TBCC_* config value")

    # sqlite DB locking (Celery/worker + poster worker)
    if "database is locked" in b:
        return Bucket(kind="sqlite_database_locked", detail="database is locked")

    if "WinError 121" in b and "semaphore timeout" in b.lower():
        return Bucket(kind="winerror_121_semaphore_timeout", detail="WinError 121: semaphore timeout period has expired")

    # Generic connection / semaphore
    if "Server closed the connection" in b and "WinError 121" in b:
        return Bucket(kind="winerror_121_semaphore_timeout", detail="Server closed connection (WinError 121)")

    # Telegram Bot API transient 5xx (only when the body looks like Telegram polling)
    if (
        "api.telegram.org" in b
        and re.search(r"\b5\d\d\b|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout", b, re.I)
    ):
        return Bucket(kind="telegram_api_5xx", detail="Telegram Bot API 5xx")

    # Fallback: if a specific exception type is present, bucket it.
    m_exc = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*Error|RuntimeError)\b\s*:\s*(.*)$", b)
    if m_exc:
        exc_type = m_exc.group(1)
        msg = m_exc.group(2).strip()
        return Bucket(kind=exc_type.lower(), detail=msg[:120] if msg else None)

    return None


def _parse_session(log_path: Path) -> dict:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    per_kind = Counter()
    per_kind_service = defaultdict(Counter)
    per_kind_first_last: dict[str, tuple[str, str]] = {}
    per_kind_samples: dict[str, list[str]] = defaultdict(list)

    total_hub_lines = 0
    counted_lines = 0

    session_started = None
    for i in range(min(50, len(lines))):
        if "TBCC Error Hub session started" in lines[i]:
            session_started = lines[i]
            break

    for line in lines:
        m = HUB_LINE_RE.match(line)
        if not m:
            continue

        total_hub_lines += 1
        service = m.group("service").strip()
        body = m.group("body").strip()

        bucket = _infer_bucket(body)
        if bucket is None:
            continue

        counted_lines += 1
        kind = bucket.kind
        per_kind[kind] += 1
        per_kind_service[kind][service] += 1

        # Track first/last timestamps (as they appear; hub lines contain wall time)
        ts = m.group("ts").strip()
        if kind not in per_kind_first_last:
            per_kind_first_last[kind] = (ts, ts)
        else:
            per_kind_first_last[kind] = (per_kind_first_last[kind][0], ts)

        if len(per_kind_samples[kind]) < 3:
            per_kind_samples[kind].append(body[:220])

    ranked = sorted(per_kind.items(), key=lambda kv: kv[1], reverse=True)
    top = [
        {
            "kind": kind,
            "count": count,
            "top_services": per_kind_service[kind].most_common(5),
            "first_seen": per_kind_first_last.get(kind, ("", ""))[0],
            "last_seen": per_kind_first_last.get(kind, ("", ""))[1],
            "samples": per_kind_samples.get(kind, []),
        }
        for kind, count in ranked
    ]

    return {
        "log_path": str(log_path),
        "session_started_line": session_started,
        "utc_analyzed_at": datetime.now(timezone.utc).isoformat(),
        "total_hub_lines": total_hub_lines,
        "counted_lines": counted_lines,
        "top_kinds": top,
    }


def _append_history(history_path: Path, entry: dict) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _rank_from_history(history_path: Path, top_n: int) -> dict:
    if not history_path.exists():
        return {"history_missing": True, "top_kinds": []}

    counts = Counter()
    kind_services = defaultdict(Counter)
    first_seen = {}
    last_seen = {}

    with history_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except Exception:
                continue

            for k in entry.get("top_kinds", []):
                kind = k.get("kind")
                c = int(k.get("count", 0))
                if not kind or c <= 0:
                    continue
                counts[kind] += c
                for svc, sc in k.get("top_services", []):
                    try:
                        kind_services[kind][svc] += int(sc)
                    except Exception:
                        pass

                fs = k.get("first_seen") or ""
                ls = k.get("last_seen") or ""
                if kind not in first_seen and fs:
                    first_seen[kind] = fs
                if ls:
                    last_seen[kind] = ls

    ranked = counts.most_common(top_n)
    return {
        "history_missing": False,
        "top_kinds": [
            {
                "kind": kind,
                "count": c,
                "top_services": kind_services[kind].most_common(5),
                "first_seen": first_seen.get(kind, ""),
                "last_seen": last_seen.get(kind, ""),
            }
            for kind, c in ranked
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tbcc-root", default=None, help="Path to tbcc/ (defaults to script parent)")
    ap.add_argument("--log", default=None, help="Path to error-hub.log")
    ap.add_argument("--history", default=None, help="Path to history jsonl")
    ap.add_argument("--update-history", action="store_true", help="Append current session summary into history")
    ap.add_argument("--rank", action="store_true", help="Rank kinds across history")
    ap.add_argument("--top", type=int, default=10, help="How many kinds to show")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    tbcc_root = Path(args.tbcc_root).resolve() if args.tbcc_root else script_dir.parent

    log_path = Path(args.log).resolve() if args.log else tbcc_root / ".tbcc-run" / "error-hub.log"
    history_path = Path(args.history).resolve() if args.history else tbcc_root / ".tbcc-run" / "error-hub-history.jsonl"

    if args.rank:
        rank = _rank_from_history(history_path, top_n=max(1, int(args.top)))
        print(json.dumps(rank, indent=2, ensure_ascii=False))
        return

    if not log_path.exists():
        raise SystemExit(f"Missing log: {log_path}")

    session = _parse_session(log_path)
    print(json.dumps(session, indent=2, ensure_ascii=False))

    if args.update_history:
        entry = {
            "session_id": datetime.now(timezone.utc).isoformat(),
            "session_started_line": session.get("session_started_line"),
            "top_kinds": session.get("top_kinds", []),
        }
        _append_history(history_path, entry)
        print(f"Appended to history: {history_path}")


if __name__ == "__main__":
    main()

