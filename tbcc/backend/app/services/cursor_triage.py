"""Optional Cursor agent triage — gated, allowlisted, daily-capped."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.services.admin_inbox import get_inbox_event_by_id
from app.services.cursor_triage_playbooks import playbook_for_event
from app.services.ops_triage_bundle import build_triage_bundle

logger = logging.getLogger(__name__)

REDIS_DAILY_KEY = "tbcc:cursor_triage:day"
REDIS_DAILY_COUNT = "tbcc:cursor_triage:count"

DEFAULT_ALLOWLIST = frozenset(
    {
        "session_lock_storm",
        "service_traceback",
        "worker_crash",
        "api_port_duplicate",
        "uvicorn_orphans",
        "api_port_bind",
        "telethon_session_invalid",
        "session_sqlite_lock",
        "redis_down",
        "redis_unreachable",
    }
)


def triage_enabled() -> bool:
    return (os.getenv("TBCC_CURSOR_TRIAGE_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def auto_fix_enabled() -> bool:
    return (os.getenv("TBCC_CURSOR_TRIAGE_AUTO_FIX") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def max_per_day() -> int:
    raw = (os.getenv("TBCC_CURSOR_TRIAGE_MAX_PER_DAY") or "3").strip()
    try:
        return max(0, min(20, int(raw)))
    except ValueError:
        return 3


def allowlist() -> frozenset[str]:
    raw = (os.getenv("TBCC_CURSOR_TRIAGE_ALLOWLIST") or "").strip()
    if not raw:
        return DEFAULT_ALLOWLIST
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


DEFAULT_AUTO_FIX_ALLOWLIST = frozenset(
    {
        "session_sqlite_lock",
        "uvicorn_orphans",
    }
)


def auto_fix_allowlist() -> frozenset[str]:
    raw = (os.getenv("TBCC_CURSOR_TRIAGE_AUTO_FIX_ALLOWLIST") or "").strip()
    if not raw:
        return DEFAULT_AUTO_FIX_ALLOWLIST
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def pr_only_enabled() -> bool:
    return (os.getenv("TBCC_CURSOR_TRIAGE_PR_ONLY") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def auto_fix_allowed_for_event(event: dict[str, Any] | None) -> bool:
    if not auto_fix_enabled():
        return False
    if not event:
        return False
    code = _event_code(event)
    return bool(code and code in auto_fix_allowlist())


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def triage_usage_today() -> dict[str, Any]:
    cap = max_per_day()
    try:
        r = _redis_client()
        day = r.get(REDIS_DAILY_KEY) or ""
        if day != _today_key():
            return {"day": _today_key(), "used": 0, "cap": cap, "remaining": cap}
        used = int(r.get(REDIS_DAILY_COUNT) or "0")
        return {"day": day, "used": used, "cap": cap, "remaining": max(0, cap - used)}
    except Exception:
        return {"day": _today_key(), "used": 0, "cap": cap, "remaining": cap}


def _event_code(event: dict[str, Any]) -> str:
    meta = event.get("meta") or {}
    return str(meta.get("code") or meta.get("alert_id") or "").strip()


def can_run_triage(event: dict[str, Any] | None) -> tuple[bool, str]:
    if not triage_enabled():
        return False, "Cursor triage disabled (set TBCC_CURSOR_TRIAGE_ENABLED=1)"
    if not event:
        return False, "Event not found"
    code = _event_code(event)
    if code and code not in allowlist():
        return False, f"Code {code!r} not in TBCC_CURSOR_TRIAGE_ALLOWLIST"
    usage = triage_usage_today()
    if usage["remaining"] <= 0:
        return False, f"Daily cap reached ({usage['used']}/{usage['cap']})"
    if not (os.getenv("CURSOR_API_KEY") or os.getenv("TBCC_CURSOR_API_KEY") or "").strip():
        return False, "Set CURSOR_API_KEY (or TBCC_CURSOR_API_KEY) for agent runs"
    return True, "ok"


def _increment_daily() -> None:
    try:
        r = _redis_client()
        today = _today_key()
        if r.get(REDIS_DAILY_KEY) != today:
            r.set(REDIS_DAILY_KEY, today)
            r.set(REDIS_DAILY_COUNT, "0")
        r.incr(REDIS_DAILY_COUNT)
    except Exception as e:
        logger.debug("cursor triage daily increment failed: %s", e)


def _build_agent_prompt(event: dict[str, Any]) -> str:
    bundle = build_triage_bundle(event)
    code = _event_code(event)
    playbook = playbook_for_event(event)
    may_patch = auto_fix_allowed_for_event(event)

    if may_patch:
        pr_rule = (
            "Create a feature branch, apply the minimal code fix, run targeted tests, "
            "open a PR — NEVER push to main/master or force-push."
            if pr_only_enabled()
            else "Apply minimal safe fixes locally; do not push without operator approval."
        )
        mode = (
            f"Auto-fix ENABLED for code {code!r}. {pr_rule} "
            "Operational relief (telegram_relief, supervisor restarts) is OK without a PR."
        )
    elif auto_fix_enabled():
        mode = (
            f"Auto-fix is globally on but NOT allowed for code {code!r}. "
            "Diagnose and propose fixes only — do NOT edit files or restart services."
        )
    else:
        mode = (
            "Diagnose and propose fixes only — do NOT edit files, commit, or restart services unless asked."
        )

    parts = [
        "TBCC operator triage (ops flywheel / automation).",
        mode,
        "",
        "Prioritize deterministic ops: telegram_relief for session lock storms, "
        "kill duplicate bot processes, restart stale backend on :8000.",
    ]
    if playbook:
        parts.extend(["", playbook])
    parts.extend(["", bundle])
    return "\n".join(parts)


def _run_agent_prompt(prompt: str) -> dict[str, Any]:
    api_key = (os.getenv("CURSOR_API_KEY") or os.getenv("TBCC_CURSOR_API_KEY") or "").strip()
    model = (os.getenv("TBCC_CURSOR_TRIAGE_MODEL") or "composer-2.5").strip()
    from pathlib import Path

    repo_root = str(
        Path(os.getenv("TBCC_REPO_ROOT") or Path(__file__).resolve().parents[3])
    ).replace("\\", "/")

    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions  # type: ignore[import-untyped]
    except ImportError:
        return {
            "ok": False,
            "error": "cursor-sdk not installed (pip install cursor-sdk)",
            "hint": "Paste the triage bundle into Cursor chat instead.",
        }

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=repo_root),
            ),
        )
        status = getattr(result, "status", None) or (result.get("status") if isinstance(result, dict) else None)
        text = getattr(result, "result", None) or (result.get("result") if isinstance(result, dict) else str(result))
        return {"ok": True, "status": status, "result": str(text or "")[:8000]}
    except Exception as e:
        logger.warning("Cursor agent triage failed: %s", e)
        return {"ok": False, "error": str(e)[:500]}


def run_cursor_triage(event_id: str, *, source: str = "api") -> dict[str, Any]:
    event = get_inbox_event_by_id(event_id)
    bundle = build_triage_bundle(event, event_id=event_id)
    ok, reason = can_run_triage(event)
    if not ok:
        return {
            "ok": False,
            "event_id": event_id,
            "source": source,
            "reason": reason,
            "bundle": bundle[:4000],
            "usage": triage_usage_today(),
        }

    prompt = _build_agent_prompt(event or {})
    agent_out = _run_agent_prompt(prompt)
    if agent_out.get("ok"):
        _increment_daily()
    return {
        "ok": bool(agent_out.get("ok")),
        "event_id": event_id,
        "source": source,
        "agent": agent_out,
        "usage": triage_usage_today(),
        "auto_fix": auto_fix_enabled(),
        "auto_fix_allowed": auto_fix_allowed_for_event(event),
        "pr_only": pr_only_enabled(),
    }
