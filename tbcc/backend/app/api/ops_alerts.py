"""Operational alerts API — conflicts and error-hub anomalies for client toasts."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.ops_alerts import (
    adjust_max_client_toasts_per_2min,
    get_alert_toast_settings,
    poll_ops_alerts,
    set_max_client_toasts_per_2min,
    skip_hub_alert_backlog,
)

router = APIRouter(prefix="/ops/alerts", tags=["ops-alerts"])


class ToastBudgetPatch(BaseModel):
    max_toasts_per_2min: int | None = Field(default=None, ge=0, le=10)
    adjust: int | None = Field(default=None, ge=-10, le=10)


@router.get("/poll")
def alerts_poll():
    """
    Poll for new breaking conflicts and irregular error-hub log lines.
    Server deduplicates via Redis; safe to call every 30–60s from extension/dashboard/supervisor.
    """
    return poll_ops_alerts()


@router.get("/toast-settings")
def alerts_toast_settings():
    """Current desktop toast budget (non-payment); adjustable live via Secretary /toasts."""
    return {"ok": True, **get_alert_toast_settings()}


@router.patch("/toast-settings")
def patch_toast_settings(body: ToastBudgetPatch):
    if body.max_toasts_per_2min is not None:
        n = set_max_client_toasts_per_2min(body.max_toasts_per_2min)
    elif body.adjust is not None:
        n = adjust_max_client_toasts_per_2min(body.adjust)
    else:
        n = get_alert_toast_settings()["max_toasts_per_2min"]
    return {"ok": True, "max_toasts_per_2min": n, **get_alert_toast_settings()}


@router.post("/skip-backlog")
def alerts_skip_backlog():
    """Advance error-hub scan + inbox toast cursors (stops catch-up notification floods)."""
    return skip_hub_alert_backlog()
