"""
Cached read of merged growth/referral settings (dashboard + env).

Order: GET /growth-settings → same merge via DB (if HTTP fails) → empty dict last resort.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
_TTL = 55.0
_cache: dict | None = None
_ts: float = 0.0


def get_effective_growth_cached() -> dict:
    """Full effective dict (same keys as app.services.growth_settings_effective)."""
    global _cache, _ts
    now = time.time()
    if _cache is not None and (now - _ts) < _TTL:
        return _cache
    try:
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{API_BASE}/growth-settings")
            if r.status_code == 200:
                data = r.json()
                eff = data.get("effective") if isinstance(data, dict) else None
                if isinstance(eff, dict):
                    _cache = eff
                    _ts = now
                    return eff
    except Exception as e:
        logger.debug("growth-settings HTTP: %s", e)
    try:
        from app.database.session import SessionLocal
        from app.services.growth_settings_effective import get_effective_growth_settings

        db = SessionLocal()
        try:
            eff = get_effective_growth_settings(db)
            _cache = eff
            _ts = now
            return eff
        finally:
            db.close()
    except Exception as e:
        logger.warning("growth-settings DB fallback failed: %s", e)
    _cache = {}
    _ts = now
    return _cache


def referral_cfg() -> dict:
    """Stable keys for payment_bot copy + payloads."""
    g = get_effective_growth_cached()
    mode = (g.get("referral_mode") or os.getenv("REFERRAL_MODE") or "premium").lower().strip()
    if mode not in ("community", "premium"):
        mode = "premium"
    try:
        reward_days = int(g.get("referral_reward_days") if g.get("referral_reward_days") is not None else os.getenv("REFERRAL_REWARD_DAYS", "7"))
    except (TypeError, ValueError):
        reward_days = 7
    return {
        "mode": mode,
        "group_link": (g.get("referral_group_invite_link") or os.getenv("REFERRAL_GROUP_INVITE_LINK") or "").strip(),
        "group_name": g.get("referral_group_name") or os.getenv("REFERRAL_GROUP_NAME") or "our community",
        "reward_days": reward_days,
    }
