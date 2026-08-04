"""Runtime Storage Hub intake policy — master-panel toggles (Redis) over env defaults."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:hub:intake"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _env_auto_approve_default() -> bool:
    gate = (os.getenv("TBCC_GATEKEEPER_HUB_AUTO_APPROVE") or "1").strip().lower()
    dep = (os.getenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE") or "1").strip().lower()
    off = frozenset({"0", "false", "no", "off"})
    return gate not in off and dep not in off


def hub_master_auto_approve_enabled() -> bool:
    """Master Q&A panel auto-approve — gatekeeper hub skip + deposit auto-approve."""
    try:
        raw = (_redis().get(f"{REDIS_PREFIX}:auto_approve") or "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if raw in ("1", "true", "yes", "on"):
            return True
    except Exception:
        logger.debug("hub intake auto_approve read failed", exc_info=True)
    return _env_auto_approve_default()


def set_hub_master_auto_approve(enabled: bool) -> bool:
    try:
        _redis().set(f"{REDIS_PREFIX}:auto_approve", "1" if enabled else "0")
    except Exception:
        logger.debug("hub intake auto_approve write failed", exc_info=True)
    return enabled


def auto_pipe_destination_label() -> str:
    """Human mode line for master panel."""
    from app.services.storage_auto_pipe import storage_auto_pipe_enabled

    if not storage_auto_pipe_enabled():
        return "Manual only — auto-pipe OFF"
    if hub_master_auto_approve_enabled():
        return "Auto-pipe → pool (auto-approve ON)"
    return "Auto-pipe → Q&A review (auto-approve OFF)"
