"""Build operator triage bundles for Cursor / agent handoff."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.admin_inbox import get_inbox_event_by_id
from app.services.focus_profile import get_focus_state, lock_events_recent_count


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _error_hub_path() -> Path:
    return _tbcc_root() / ".tbcc-run" / "error-hub.log"


def tail_error_hub(*, max_lines: int = 40) -> str:
    path = _error_hub_path()
    if not path.is_file():
        return "(error-hub.log not found)"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return f"(error-hub read failed: {e})"
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("====")]
    if not lines:
        return "(error-hub empty)"
    return "\n".join(lines[-max(5, min(120, int(max_lines))):])


def build_triage_bundle(
    event: dict[str, Any] | None,
    *,
    event_id: str | None = None,
    hub_lines: int = 40,
) -> str:
    """Plain-text bundle for Cursor chat or Copy-for-Cursor."""
    ev = event or (get_inbox_event_by_id(event_id) if event_id else None)
    if not ev:
        return f"TBCC triage: event not found (id={event_id or '?'})"

    meta = ev.get("meta") or {}
    focus = get_focus_state()
    lock_n = lock_events_recent_count()
    hub = tail_error_hub(max_lines=hub_lines)
    repo = _tbcc_root().resolve()

    lines = [
        "TBCC ops triage bundle",
        f"generated: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"repo: {repo}",
        "",
        "=== inbox event ===",
        f"id: {ev.get('id')}",
        f"ts: {ev.get('ts')}",
        f"category: {ev.get('category')}",
        f"severity: {ev.get('severity')}",
        f"title: {ev.get('title')}",
        f"body: {ev.get('body')}",
        f"meta: {meta}",
        "",
        "=== focus / telethon ===",
        f"profile: {focus.get('profile')}",
        f"reason: {focus.get('reason')}",
        f"lock_events_recent: {lock_n}",
        f"auto_react_env: {(os.getenv('TBCC_FOCUS_AUTO_REACT') or '0').strip()}",
        "",
        "=== error-hub tail ===",
        hub,
        "",
        "=== suggested actions (deterministic first) ===",
        "- session_lock_storm → POST /ops/focus profile=telegram_relief (or tap Telegram relief)",
        "- api_port_duplicate / uvicorn_orphans → restart TBCC-Backend, kill stale :8000",
        "- worker_crash → check .tbcc-run/error-hub.log service tag, restart that service",
        "",
        "Diagnose only unless explicitly asked to apply a fix.",
    ]
    text = "\n".join(lines)
    return text[:12000]
