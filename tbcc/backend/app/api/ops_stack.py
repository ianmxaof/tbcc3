"""TBCC stack status — mirrors tray supervisor 8/8 summary."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.tbcc_stack_control import get_stack_status, stack_control_available

router = APIRouter(prefix="/ops", tags=["ops-stack"])


@router.get("/stack-status")
def ops_stack_status():
    """Tray-aligned process summary (enabled_up / enabled, per-service up/down)."""
    if not stack_control_available():
        return {
            "ok": False,
            "available": False,
            "error": "stack status requires Windows tray supervisor (tbcc-stack-cli.ps1)",
        }
    data = get_stack_status()
    data["available"] = True
    return data
