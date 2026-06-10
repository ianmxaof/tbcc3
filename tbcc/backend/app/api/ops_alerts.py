"""Operational alerts API — conflicts and error-hub anomalies for client toasts."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.ops_alerts import poll_ops_alerts

router = APIRouter(prefix="/ops/alerts", tags=["ops-alerts"])


@router.get("/poll")
def alerts_poll():
    """
    Poll for new breaking conflicts and irregular error-hub log lines.
    Server deduplicates via Redis; safe to call every 30–60s from extension/dashboard/supervisor.
    """
    return poll_ops_alerts()
