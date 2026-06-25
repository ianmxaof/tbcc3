"""Operator role permissions for TBCC MCP tools and flywheel actions."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_ROLE = "api"
_YAML = Path(__file__).resolve().parent.parent / "data" / "ops_tool_permissions.yaml"


@lru_cache(maxsize=1)
def _load_permissions() -> dict[str, Any]:
    if not _YAML.is_file():
        return {"operators": {}}
    try:
        raw = yaml.safe_load(_YAML.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {"operators": {}}
    except Exception as e:
        logger.warning("ops_tool_permissions load failed: %s", e)
        return {"operators": {}}


def normalize_operator(role: str | None) -> str:
    r = (role or _DEFAULT_ROLE).strip().lower()
    ops = _load_permissions().get("operators") or {}
    if r in ops:
        return r
    aliases = {
        "openclawtbcc": "openclaw",
        "openclaw_bot": "openclaw",
        "mcp": "openclaw",
        "flywheel_approve": "secretary",
    }
    return aliases.get(r, _DEFAULT_ROLE)


def operator_config(role: str | None) -> dict[str, Any]:
    key = normalize_operator(role)
    ops = _load_permissions().get("operators") or {}
    cfg = ops.get(key)
    if isinstance(cfg, dict):
        return cfg
    return ops.get(_DEFAULT_ROLE) or {}


def list_operators() -> list[str]:
    ops = _load_permissions().get("operators") or {}
    return sorted(ops.keys())


def mcp_tool_allowed(role: str | None, tool_name: str) -> bool:
    name = (tool_name or "").strip()
    if not name:
        return False
    cfg = operator_config(role)
    denied = {str(x) for x in (cfg.get("denied_mcp_tools") or [])}
    if name in denied:
        return False
    allowed = cfg.get("allowed_mcp_tools") or []
    if "*" in allowed:
        return True
    return name in {str(x) for x in allowed}


def flywheel_can(role: str | None, action: str) -> bool:
    cfg = operator_config(role)
    fw = cfg.get("flywheel") or {}
    key = f"can_{(action or '').strip().lower()}"
    return bool(fw.get(key))


def flywheel_lane_allowed(role: str | None, lane: str) -> bool:
    cfg = operator_config(role)
    fw = cfg.get("flywheel") or {}
    lanes = {str(x) for x in (fw.get("allowed_lanes") or [])}
    return (lane or "notify_only") in lanes


def permissions_summary(role: str | None = None) -> dict[str, Any]:
    key = normalize_operator(role)
    cfg = operator_config(key)
    fw = cfg.get("flywheel") or {}
    return {
        "operator": key,
        "description": cfg.get("description"),
        "allowed_mcp_tools": cfg.get("allowed_mcp_tools"),
        "denied_mcp_tools": cfg.get("denied_mcp_tools"),
        "flywheel": fw,
    }


def assert_flywheel_action(role: str | None, action: str) -> None:
    if not flywheel_can(role, action):
        op = normalize_operator(role)
        raise PermissionError(
            f"Operator '{op}' cannot flywheel_{action}. Use Secretary or api role."
        )
