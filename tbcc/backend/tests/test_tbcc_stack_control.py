"""Tests for tray stack control helpers."""

from __future__ import annotations

from app.services.tbcc_stack_control import (
    bot_service_id,
    infer_service_id_from_event,
    resolve_bot_runtime_commands,
)


def test_bot_service_id_map():
    assert bot_service_id("payment_bot") == "payment"
    assert bot_service_id("loot_bot") == "loot"


def test_infer_service_from_title():
    ev = {"service": "TBCC-Celery-Post", "message": "child process died"}
    assert infer_service_id_from_event(ev) == "celery_post"


def test_infer_scheduler_lane_exact_match_wins():
    # Reverse of the above: an exact match on the longer scheduler needle must still
    # resolve to the scheduler lane, not collapse back to celery_post.
    ev = {"service": "TBCC-Celery-Post-Scheduler", "message": "child process died"}
    assert infer_service_id_from_event(ev) == "celery_post_scheduler"


def test_infer_payment_from_409_body():
    ev = {"service": "TBCC-PaymentBot", "body": "Conflict: terminated by other getUpdates request"}
    assert infer_service_id_from_event(ev) == "payment"


def test_resolve_commands_fills_status():
    cmds = resolve_bot_runtime_commands("payment_bot", {"start": "", "stop": "", "restart": "", "reload": "", "status": ""})
    if __import__("platform").system() == "Windows":
        assert "tbcc-stack-cli.ps1" in cmds["status"]
        assert "-Service payment" in cmds["status"]
