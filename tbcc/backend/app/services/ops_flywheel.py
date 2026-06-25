"""
TBCC ops flywheel — route inbox alerts to deterministic fixes, Claude Code handoffs, or Cursor agents.

Pending destructive actions require Secretary approval (TBCC_FLYWHEEL_APPROVAL=1, default on).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from app.services.admin_inbox import get_inbox_event_by_id, list_inbox_events, push_admin_inbox_event
from app.services.cursor_triage import run_cursor_triage, triage_enabled
from app.services.focus_profile import apply_focus_profile
from app.services.ops_triage_bundle import build_triage_bundle
from app.services.tbcc_stack_control import execute_flywheel_stack_action, infer_service_id_from_event

logger = logging.getLogger(__name__)

Lane = Literal["deterministic", "claude_code", "cursor", "notify_only"]

REDIS_PENDING = "tbcc:flywheel:pending"
REDIS_HANDLED = "tbcc:flywheel:handled"
REDIS_CURSOR = "tbcc:flywheel:last_poll"

# code -> lane + optional deterministic profile
SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "session_lock_storm": {
        "lane": "deterministic",
        "action": "telegram_relief",
        "label": "Apply telegram_relief focus profile",
        "requires_approval": False,
    },
    "session_sqlite_lock": {
        "lane": "deterministic",
        "action": "telegram_relief",
        "label": "Apply telegram_relief (SQLite session contention)",
        "requires_approval": False,
    },
    "worker_crash": {
        "lane": "deterministic",
        "action": "restart_stack_service",
        "label": "Restart crashed TBCC service via supervisor tray",
        "requires_approval": False,
    },
    "api_port_duplicate": {
        "lane": "deterministic",
        "action": "restart_stack_service",
        "service_id": "backend",
        "label": "Restart TBCC-Backend (port 8000 conflict)",
        "requires_approval": False,
    },
    "telegram_409_conflict": {
        "lane": "deterministic",
        "action": "restart_stack_service",
        "label": "Restart duplicate Telegram bot via supervisor",
        "requires_approval": False,
    },
    "uvicorn_orphans": {
        "lane": "claude_code",
        "label": "Claude Code: clean orphan uvicorn workers",
        "requires_approval": True,
    },
    "service_traceback": {
        "lane": "cursor",
        "label": "Cursor agent diagnose-only triage",
        "requires_approval": True,
    },
    "redis_down": {
        "lane": "notify_only",
        "label": "Manual: start Redis / Docker stack",
        "requires_approval": False,
    },
    "redis_unreachable": {
        "lane": "notify_only",
        "label": "Manual: check REDIS_URL and Docker",
        "requires_approval": False,
    },
}


def flywheel_enabled() -> bool:
    return (os.getenv("TBCC_FLYWHEEL_ENABLED") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def approval_required() -> bool:
    return (os.getenv("TBCC_FLYWHEEL_APPROVAL") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def openclaw_auto_tick() -> bool:
    raw = (os.getenv("TBCC_FLYWHEEL_AUTO_TICK") or os.getenv("TBCC_OPENCLAW_AUTO_TICK") or "0").strip()
    return raw.lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def flywheel_auto_tick() -> bool:
    return openclaw_auto_tick()


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_code(event: dict[str, Any]) -> str:
    meta = event.get("meta") or {}
    return str(meta.get("code") or "").strip()


def registry_for_code(code: str) -> dict[str, Any] | None:
    return SKILL_REGISTRY.get(code)


def list_pending() -> list[dict[str, Any]]:
    try:
        r = _redis_client()
        raw = r.lrange(REDIS_PENDING, 0, 49)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except (TypeError, json.JSONDecodeError):
            continue
    return out


def _pending_event_ids() -> set[str]:
    return {str(a.get("event_id") or "") for a in list_pending() if a.get("event_id")}


def _store_pending(action: dict[str, Any]) -> dict[str, Any]:
    event_id = str(action.get("event_id") or "")
    for existing in list_pending():
        if event_id and str(existing.get("event_id") or "") == event_id:
            return existing
    try:
        r = _redis_client()
        r.lpush(REDIS_PENDING, json.dumps(action, separators=(",", ":")))
        r.ltrim(REDIS_PENDING, 0, 49)
    except Exception as e:
        logger.debug("flywheel pending store failed: %s", e)
    return action


def _mark_handled(event_id: str) -> None:
    try:
        r = _redis_client()
        r.sadd(REDIS_HANDLED, event_id)
        r.expire(REDIS_HANDLED, 86400 * 7)
    except Exception:
        pass


def _was_handled(event_id: str) -> bool:
    try:
        r = _redis_client()
        return bool(r.sismember(REDIS_HANDLED, event_id))
    except Exception:
        return False


def build_claude_code_handoff(event: dict[str, Any], *, code: str, label: str) -> str:
    bundle = build_triage_bundle(event)
    repo = os.getenv("TBCC_REPO_ROOT") or str(
        __import__("pathlib").Path(__file__).resolve().parents[3]
    )
    return (
        "# Claude Code handoff — TBCC ops flywheel\n\n"
        f"## Goal\n{label}\n\n"
        f"Alert code: `{code}` · event id: `{event.get('id')}`\n\n"
        "## Scope\n"
        f"- Repo: `{repo}`\n"
        "- Only touch TBCC service control scripts and process cleanup unless clearly required.\n"
        "- Do NOT commit secrets or modify `.env`.\n\n"
        "## Verification\n"
        "- `curl http://127.0.0.1:8000/ops/focus`\n"
        "- Check `.tbcc-run/error-hub.log` for the service tag stopped erroring.\n\n"
        "## Context bundle\n\n"
        f"{bundle}"
    )


def _notify_proposal(action: dict[str, Any]) -> None:
    aid = action.get("id", "")
    code = action.get("code", "")
    label = action.get("label", "")
    push_admin_inbox_event(
        category="ops",
        severity="important",
        title=f"Flywheel approval: {code}",
        body=f"{label}\n\nApprove in Secretary: /flywheel or tap buttons on this message.",
        meta={"flywheel_action_id": aid, "code": code, "event_id": action.get("event_id")},
        instant=True,
    )


def route_event(event: dict[str, Any], *, source: str = "router") -> dict[str, Any]:
    """Route one inbox event through the flywheel registry."""
    event_id = str(event.get("id") or "")
    code = _event_code(event)
    reg = registry_for_code(code) if code else None

    if not reg:
        return {
            "ok": True,
            "routed": False,
            "event_id": event_id,
            "code": code,
            "reason": "no registry entry — use /triage or Copy for Cursor",
        }

    lane = str(reg.get("lane") or "notify_only")
    needs_approval = bool(reg.get("requires_approval")) and approval_required()

    if lane == "deterministic":
        profile = str(reg.get("action") or "telegram_relief")
        stack_action = profile if profile in ("restart_stack_service", "restart_scheduling_stack") else None
        if stack_action:
            if needs_approval:
                action = {
                    "id": secrets.token_hex(6),
                    "event_id": event_id,
                    "code": code,
                    "lane": lane,
                    "label": reg.get("label"),
                    "profile": profile,
                    "service_id": reg.get("service_id") or infer_service_id_from_event(event),
                    "status": "pending",
                    "created": _now_iso(),
                    "source": source,
                }
                _store_pending(action)
                _notify_proposal(action)
                return {"ok": True, "routed": True, "lane": lane, "pending_id": action["id"], "approval": True}
            result = execute_flywheel_stack_action(stack_action, event, reg=reg)
            _mark_handled(event_id)
            return {"ok": True, "routed": True, "lane": lane, "stack_action": stack_action, "result": result}

        if needs_approval:
            action = {
                "id": secrets.token_hex(6),
                "event_id": event_id,
                "code": code,
                "lane": lane,
                "label": reg.get("label"),
                "profile": profile,
                "status": "pending",
                "created": _now_iso(),
                "source": source,
            }
            _store_pending(action)
            _notify_proposal(action)
            return {"ok": True, "routed": True, "lane": lane, "pending_id": action["id"], "approval": True}

        result = apply_focus_profile(profile, reason=f"Flywheel auto ({code})", auto=True)
        _mark_handled(event_id)
        return {"ok": True, "routed": True, "lane": lane, "result": result}

    if lane == "claude_code":
        handoff = build_claude_code_handoff(event, code=code, label=str(reg.get("label") or ""))
        action = {
            "id": secrets.token_hex(6),
            "event_id": event_id,
            "code": code,
            "lane": lane,
            "label": reg.get("label"),
            "handoff": handoff[:10000],
            "status": "pending" if needs_approval else "ready",
            "created": _now_iso(),
            "source": source,
        }
        _store_pending(action)
        if needs_approval:
            _notify_proposal(action)
        _mark_handled(event_id)
        return {
            "ok": True,
            "routed": True,
            "lane": lane,
            "pending_id": action["id"],
            "approval": needs_approval,
            "handoff_preview": handoff[:500],
        }

    if lane == "cursor":
        if not triage_enabled():
            return {
                "ok": True,
                "routed": False,
                "lane": lane,
                "reason": "Cursor triage disabled — enable TBCC_CURSOR_TRIAGE_ENABLED",
            }
        if needs_approval:
            action = {
                "id": secrets.token_hex(6),
                "event_id": event_id,
                "code": code,
                "lane": lane,
                "label": reg.get("label"),
                "status": "pending",
                "created": _now_iso(),
                "source": source,
            }
            _store_pending(action)
            _notify_proposal(action)
            _mark_handled(event_id)
            return {"ok": True, "routed": True, "lane": lane, "pending_id": action["id"], "approval": True}
        out = run_cursor_triage(event_id, source=source)
        _mark_handled(event_id)
        return {"ok": True, "routed": True, "lane": lane, "cursor": out}

    _mark_handled(event_id)
    return {"ok": True, "routed": True, "lane": "notify_only", "label": reg.get("label")}


def approve_action(action_id: str) -> dict[str, Any]:
    pending = list_pending()
    action = next((a for a in pending if str(a.get("id")) == action_id), None)
    if not action:
        return {"ok": False, "error": "pending action not found"}

    lane = str(action.get("lane") or "")
    event_id = str(action.get("event_id") or "")
    event = get_inbox_event_by_id(event_id) or {}

    if lane == "deterministic":
        profile = str(action.get("profile") or "telegram_relief")
        if profile in ("restart_stack_service", "restart_scheduling_stack"):
            reg = {
                "action": profile,
                "service_id": action.get("service_id"),
            }
            result = execute_flywheel_stack_action(profile, event, reg=reg)
            _remove_pending(action_id)
            _mark_handled(event_id)
            return {"ok": True, "executed": True, "lane": lane, "result": result}
        result = apply_focus_profile(profile, reason=f"Flywheel approved ({action.get('code')})", auto=False)
        _remove_pending(action_id)
        _mark_handled(event_id)
        return {"ok": True, "executed": True, "lane": lane, "result": result}

    if lane == "cursor" and event_id:
        out = run_cursor_triage(event_id, source="flywheel_approve")
        _remove_pending(action_id)
        _mark_handled(event_id)
        return {"ok": True, "executed": True, "lane": lane, "cursor": out}

    if lane == "claude_code":
        _remove_pending(action_id)
        return {
            "ok": True,
            "executed": False,
            "lane": lane,
            "handoff": action.get("handoff"),
            "hint": "Paste handoff into Claude Code — execution is manual by design.",
        }

    _remove_pending(action_id)
    return {"ok": True, "executed": False, "lane": lane}


def reject_action(action_id: str) -> dict[str, Any]:
    _remove_pending(action_id)
    return {"ok": True, "rejected": action_id}


def _remove_pending(action_id: str) -> None:
    try:
        r = _redis_client()
        raw_items = r.lrange(REDIS_PENDING, 0, 49)
        kept: list[str] = []
        for raw in raw_items:
            try:
                a = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                kept.append(raw)
                continue
            if str(a.get("id")) != action_id:
                kept.append(raw)
        r.delete(REDIS_PENDING)
        if kept:
            r.rpush(REDIS_PENDING, *reversed(kept))
    except Exception as e:
        logger.debug("flywheel remove pending failed: %s", e)


def tick_flywheel(*, limit: int = 1) -> dict[str, Any]:
    """OpenClaw / cron entry: route newest unhandled critical ops events."""
    if not flywheel_enabled():
        return {"ok": True, "enabled": False, "processed": []}

    events = list_inbox_events(limit=10, category="ops", min_severity="critical")  # type: ignore[arg-type]
    processed: list[dict[str, Any]] = []
    for ev in events:
        eid = str(ev.get("id") or "")
        if not eid or _was_handled(eid) or eid in _pending_event_ids():
            continue
        code = _event_code(ev)
        if not registry_for_code(code):
            continue
        processed.append(route_event(ev, source="flywheel_tick"))
        if len(processed) >= max(1, limit):
            break

    try:
        r = _redis_client()
        r.set(REDIS_CURSOR, str(time.time()))
    except Exception:
        pass

    return {"ok": True, "enabled": True, "processed": processed, "pending": len(list_pending())}


def build_approval_bundle(*, max_items: int = 10) -> dict[str, Any]:
    """Structured pending queue for external operators (OpenClaw MCP, scripts)."""
    pending = list_pending()[: max(1, max_items)]
    lines: list[str] = []
    for i, action in enumerate(pending, 1):
        code = str(action.get("code") or "")
        aid = str(action.get("id") or "")
        label = str(action.get("label") or "")
        created = str(action.get("created") or "")
        lane = str(action.get("lane") or "")
        lines.append(f"{i}. [{code}] {label} (id={aid}, lane={lane}, created={created})")
    return {
        "ok": True,
        "pending_count": len(list_pending()),
        "pending": pending,
        "markdown": "\n".join(lines) if lines else "No pending flywheel approvals.",
        "secretary_hint": "Approve/Reject in @aof_secretary_bot via /flywheel or inline buttons.",
        "api": {
            "approve": "POST /ops/flywheel/approve/{action_id}",
            "reject": "POST /ops/flywheel/reject/{action_id}",
        },
    }


def flywheel_status() -> dict[str, Any]:
    from app.services.content_signals import growth_signals_status

    return {
        "enabled": flywheel_enabled(),
        "approval": approval_required(),
        "openclaw_auto_tick": openclaw_auto_tick(),
        "registry_codes": sorted(SKILL_REGISTRY.keys()),
        "pending_count": len(list_pending()),
        "pending": list_pending()[:10],
        "cursor_triage": triage_enabled(),
        "growth_signals": growth_signals_status(),
    }
