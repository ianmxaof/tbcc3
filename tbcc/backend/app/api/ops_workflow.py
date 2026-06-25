"""TBCC ops workflow + operator permissions API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel, Field

from app.services.ops_tool_permissions import (
    list_operators,
    mcp_tool_allowed,
    permissions_summary,
)
from app.services.ops_workflow_runner import run_ops_workflow, workflow_status

router = APIRouter(prefix="/ops/workflow", tags=["ops-workflow"])


class WorkflowRunBody(BaseModel):
    ops_limit: int = Field(1, ge=1, le=5)
    operator: str = Field("openclaw", description="openclaw | secretary | cron | api")
    include_handoff: bool = True


@router.get("/status")
def get_workflow_status():
    return workflow_status()


@router.post("/run")
def post_workflow_run(body: WorkflowRunBody | None = None):
    """Run tbcc_ops_turn: health → scheduling → flywheel tick → approval gate → handoff."""
    b = body or WorkflowRunBody()
    return run_ops_workflow(
        ops_limit=b.ops_limit,
        operator=b.operator,
        include_handoff=b.include_handoff,
    )


@router.get("/permissions")
def get_permissions(operator: str = Query("openclaw")):
    return {"ok": True, **permissions_summary(operator)}


@router.get("/permissions/operators")
def list_permission_operators():
    return {"ok": True, "operators": list_operators()}


@router.get("/permissions/mcp/{tool_name}")
def check_mcp_permission(
    tool_name: str,
    operator: str = Query("openclaw"),
):
    allowed = mcp_tool_allowed(operator, tool_name)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Operator '{operator}' cannot use MCP tool '{tool_name}'",
        )
    return {"ok": True, "operator": operator, "tool": tool_name, "allowed": True}
