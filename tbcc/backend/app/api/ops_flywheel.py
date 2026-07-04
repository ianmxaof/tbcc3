"""Ops flywheel — route alerts, pending approvals, OpenClaw tick."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.ops_flywheel import (
    approve_action,
    build_approval_bundle,
    flywheel_status,
    list_pending,
    reject_action,
    route_event,
    tick_flywheel,
)
from app.services.admin_inbox import get_inbox_event_by_id
from app.services.ops_tool_permissions import assert_flywheel_action, permissions_summary

router = APIRouter(prefix="/ops/flywheel", tags=["ops-flywheel"])


class FlywheelRouteBody(BaseModel):
    event_id: str = Field(..., min_length=4, max_length=64)
    source: str = "api"


class FlywheelTickBody(BaseModel):
    limit: int = Field(1, ge=1, le=5)


@router.get("/status")
def flywheel_get_status():
    return flywheel_status()


@router.get("/pending")
def flywheel_pending():
    return {"ok": True, "pending": list_pending()}


@router.get("/approval-bundle")
def flywheel_approval_bundle():
    """Pending flywheel actions + markdown summary for OpenClaw / MCP operators."""
    return build_approval_bundle()


@router.post("/route")
def flywheel_route(body: FlywheelRouteBody):
    ev = get_inbox_event_by_id(body.event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Inbox event not found")
    return route_event(ev, source=body.source)


@router.post("/tick")
def flywheel_tick(body: FlywheelTickBody | None = None):
    """TBCC flywheel / scheduled poller entry point (internal event bus)."""
    limit = body.limit if body else 1
    return tick_flywheel(limit=limit)


@router.get("/permissions")
def flywheel_permissions(operator: str = Query("openclaw")):
    return {"ok": True, **permissions_summary(operator)}


@router.post("/approve/{action_id}")
def flywheel_approve(action_id: str, operator: str = Query("api")):
    try:
        assert_flywheel_action(operator, "approve")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return approve_action(action_id, operator=operator)


@router.post("/reject/{action_id}")
def flywheel_reject(action_id: str, operator: str = Query("api")):
    try:
        assert_flywheel_action(operator, "reject")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return reject_action(action_id, operator=operator)
