"""Companion bot ops API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/ops")
async def companion_ops_route() -> dict[str, Any]:
    from app.services.companion_ops import companion_ops_status

    return await companion_ops_status()
