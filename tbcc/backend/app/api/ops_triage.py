"""Ops triage bundles and optional Cursor agent runs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.admin_inbox import get_inbox_event_by_id
from app.services.cursor_triage import (
    auto_fix_allowlist,
    auto_fix_enabled,
    auto_fix_allowed_for_event,
    can_run_triage,
    max_per_day,
    pr_only_enabled,
    run_cursor_triage,
    triage_enabled,
    triage_usage_today,
)
from app.services.ops_triage_bundle import build_triage_bundle

router = APIRouter(prefix="/ops/triage", tags=["ops-triage"])


class TriageRunBody(BaseModel):
    event_id: str = Field(..., min_length=4, max_length=64)
    source: str = "api"


@router.get("/status")
def triage_status():
    return {
        "enabled": triage_enabled(),
        "auto_fix": auto_fix_enabled(),
        "auto_fix_allowlist": sorted(auto_fix_allowlist()),
        "pr_only": pr_only_enabled(),
        "max_per_day": max_per_day(),
        "usage": triage_usage_today(),
    }


@router.get("/bundle/{event_id}")
def triage_bundle(event_id: str):
    ev = get_inbox_event_by_id(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Inbox event not found")
    ok, reason = can_run_triage(ev)
    return {
        "ok": True,
        "event_id": event_id,
        "can_agent": ok,
        "can_agent_reason": reason if not ok else None,
        "auto_fix_allowed": auto_fix_allowed_for_event(ev),
        "bundle": build_triage_bundle(ev),
    }


@router.post("/run")
def triage_run(body: TriageRunBody):
    ev = get_inbox_event_by_id(body.event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Inbox event not found")
    return run_cursor_triage(body.event_id, source=body.source)
