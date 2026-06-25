"""
YAML-driven TBCC ops workflow runner.

Inspired by openclaw-orchestration/core/runner.py — lightweight, no external orchestration host.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.services.ops_flywheel import build_approval_bundle, tick_flywheel
from app.services.ops_tool_permissions import (
    flywheel_can,
    normalize_operator,
    permissions_summary,
)
from app.services.system_health import collect_scheduling_health, collect_system_health

logger = logging.getLogger(__name__)

_WORKFLOW = Path(__file__).resolve().parent.parent / "data" / "ops_workflow.yaml"


def _load_workflow() -> dict[str, Any]:
    if not _WORKFLOW.is_file():
        return {}
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8")) or {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _health_failed(health: dict[str, Any]) -> bool:
    conflicts = health.get("conflicts") or []
    for c in conflicts:
        if str(c.get("severity") or "").lower() == "critical":
            return True
    return not health.get("ok", True)


def _scheduling_issues(sched: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not sched.get("beat_running"):
        issues.append("Celery Beat not running — scheduled posts will stall")
    if not sched.get("celery_post_worker_running"):
        issues.append("Celery-Post worker not running — posts queue won't drain")
    if sched.get("scheduling_paused_by_focus"):
        issues.append(f"Scheduling paused by focus profile ({sched.get('focus_profile')})")
    return issues


def _build_handoff_markdown(state: dict[str, Any], *, operator: str) -> str:
    lines = [
        f"# TBCC ops handoff ({_now_iso()[:10]})",
        "",
        "## Context Summary",
        f"- Operator role: `{operator}`",
        f"- Workflow: `tbcc_ops_turn`",
        f"- Steps run: {', '.join(state.get('steps_run') or [])}",
        "",
        "## Findings",
    ]
    health = state.get("health") or {}
    if _health_failed(health):
        for c in health.get("conflicts") or []:
            sev = c.get("severity", "?")
            code = c.get("code", "")
            msg = c.get("message", "")
            lines.append(f"- **P0/P1** [{code}] ({sev}) {msg}")
    else:
        lines.append("- **P3** System health OK")

    sched_issues = state.get("scheduling_issues") or []
    for issue in sched_issues:
        lines.append(f"- **P1** scheduling: {issue}")

    bundle = state.get("approval_bundle") or {}
    pending = int(bundle.get("pending_count") or 0)
    if pending:
        lines.append(f"- **P2** {pending} pending flywheel approval(s) — Secretary gate")
        lines.append("")
        lines.append("```")
        lines.append(str(bundle.get("markdown") or "")[:2000])
        lines.append("```")

    lines.extend(
        [
            "",
            "## Recommendations",
            "- Use lean stack if CPU hot: `TBCC_STACK_PROFILE=lean` + `start.ps1 -Full -NoReload`",
            "- OpenClaw: notify only; approve via @aof_secretary_bot",
            "",
            "## Implementation Steps",
            "1. Fix P0/P1 findings above",
            "2. `mcporter call tbcc.tbcc_health`",
            "3. Re-run `POST /ops/workflow/run`",
            "",
            "See `tbcc/docs/OPS_HANDOFF_PROTOCOL.md` for full format.",
        ]
    )
    return "\n".join(lines)


def run_ops_workflow(
    *,
    ops_limit: int = 1,
    operator: str | None = "openclaw",
    include_handoff: bool = True,
) -> dict[str, Any]:
    """Execute tbcc_ops_turn workflow from ops_workflow.yaml."""
    wf = _load_workflow()
    if not wf:
        return {"ok": False, "error": "ops_workflow.yaml missing"}

    op = normalize_operator(operator)
    perms = permissions_summary(op)
    state: dict[str, Any] = {}
    steps_run: list[str] = []
    gate_paused_at: str | None = None

    for step in wf.get("steps") or []:
        step_id = str(step.get("id") or "")
        step_type = str(step.get("type") or "")

        if step_type == "check":
            check = str(step.get("check") or "")
            if check == "system_health":
                health = collect_system_health()
                state["health"] = health
                steps_run.append(step_id)
                if step.get("gate_on_fail") and _health_failed(health):
                    gate_paused_at = step_id
                    break
            elif check == "scheduling_health":
                sched = collect_scheduling_health()
                state["scheduling"] = sched
                state["scheduling_issues"] = _scheduling_issues(sched)
                steps_run.append(step_id)
            continue

        if step_type == "action":
            action = str(step.get("action") or "")
            if action == "flywheel_tick":
                if not flywheel_can(op, "tick"):
                    state["flywheel_tick"] = {"ok": False, "skipped": True, "reason": f"{op} cannot tick"}
                else:
                    limit = max(1, min(5, int(ops_limit)))
                    state["flywheel_tick"] = tick_flywheel(limit=limit)
                steps_run.append(step_id)
            continue

        if step_type == "gate":
            gate = str(step.get("gate") or "")
            if gate == "flywheel_pending":
                bundle = build_approval_bundle()
                state["approval_bundle"] = bundle
                steps_run.append(step_id)
                if int(bundle.get("pending_count") or 0) > 0:
                    gate_paused_at = step_id
                    state["gate_message"] = step.get("message")
            continue

        if step_type == "output":
            when = step.get("when")
            if when is not None and not when:
                continue
            if include_handoff:
                state["handoff_markdown"] = _build_handoff_markdown(state, operator=op)
            steps_run.append(step_id)
            continue

    status = "paused_at_gate" if gate_paused_at else "completed"
    return {
        "ok": True,
        "workflow_id": wf.get("id"),
        "workflow_name": wf.get("name"),
        "status": status,
        "gate_paused_at": gate_paused_at,
        "operator": op,
        "permissions": perms,
        "steps_run": steps_run,
        "state": state,
    }


def workflow_status() -> dict[str, Any]:
    wf = _load_workflow()
    return {
        "ok": True,
        "workflow": {
            "id": wf.get("id"),
            "name": wf.get("name"),
            "description": wf.get("description"),
            "step_count": len(wf.get("steps") or []),
        },
        "path": str(_WORKFLOW),
    }
