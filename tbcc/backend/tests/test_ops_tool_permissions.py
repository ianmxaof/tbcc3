"""Tests for ops tool permissions."""

from app.services.ops_tool_permissions import (
    flywheel_can,
    mcp_tool_allowed,
    normalize_operator,
)


def test_openclaw_cannot_approve():
    assert not flywheel_can("openclaw", "approve")
    assert not flywheel_can("openclaw", "reject")
    assert flywheel_can("openclaw", "tick")


def test_secretary_can_approve():
    assert flywheel_can("secretary", "approve")
    assert flywheel_can("secretary", "reject")


def test_openclaw_mcp_denied_destructive():
    assert mcp_tool_allowed("openclaw", "tbcc_health")
    assert mcp_tool_allowed("openclaw", "flywheel_approval_bundle")
    assert not mcp_tool_allowed("openclaw", "flywheel_approve")
    assert not mcp_tool_allowed("openclaw", "create_scheduled_post")


def test_operator_aliases():
    assert normalize_operator("openclawtbcc") == "openclaw"
    assert normalize_operator("cron") == "cron"
