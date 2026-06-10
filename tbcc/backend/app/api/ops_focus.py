"""Focus profiles — coordinated service relief without full stack shutdown."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.focus_profile import (
    apply_focus_profile,
    evaluate_and_maybe_auto_apply,
    evaluate_focus_triggers,
    focus_public_snapshot,
    get_focus_state,
    restore_focus_profile,
)

router = APIRouter(prefix="/ops/focus", tags=["ops-focus"])


class FocusApplyBody(BaseModel):
    profile: str = Field(..., description="import_burst | telegram_relief | watch_folder | minimal | off")
    reason: str = ""
    force: bool = False


@router.get("")
def focus_status():
    """Current profile, flags, and trigger evaluation."""
    snap = focus_public_snapshot()
    return snap


@router.get("/evaluate")
def focus_evaluate():
    """Evaluate triggers; does not apply unless TBCC_FOCUS_AUTO_REACT=1 via POST /evaluate/auto."""
    return evaluate_focus_triggers()


@router.post("/evaluate/auto")
def focus_evaluate_auto():
    """Evaluate triggers and auto-apply telegram_relief when lock storm detected."""
    return evaluate_and_maybe_auto_apply()


@router.post("")
def focus_apply(body: FocusApplyBody):
    profile = (body.profile or "").strip().lower()
    if profile == "off":
        return restore_focus_profile(reason=body.reason or "API restore")
    return apply_focus_profile(
        profile,
        reason=body.reason or f"Dashboard/API apply {profile}",
        auto=False,
        force=body.force,
    )


@router.post("/restore")
def focus_restore():
    return restore_focus_profile(reason="API restore")
