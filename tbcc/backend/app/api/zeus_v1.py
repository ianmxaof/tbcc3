"""Zeus control plane — Phase 3a read-only facade over existing ops helpers.

No Start/Stop/Restart, no Telethon, no Layer B. Agents get a stable /zeus/v1 namespace
while tray remains process owner.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.ops_stack import build_stack_status_payload

router = APIRouter(prefix="/zeus/v1", tags=["zeus-v1"])


@router.get("/stack/status")
def zeus_stack_status():
    """Alias of GET /ops/stack-status — same tray-aligned shape."""
    return build_stack_status_payload()
