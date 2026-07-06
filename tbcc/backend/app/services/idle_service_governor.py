"""Idle Service Governor — run optional background services only when signals warrant.

Split design (keep these two responsibilities apart):

  * ``governor_tick()`` — the ONLY place signals are evaluated (DB / expensive reads).
    Rate-limited to ~5 min. Writes a per-service desired-state boolean to Redis. Hysteresis:
    a service stays "active" for its idle window after the last wake signal, so it does not
    flap on/off every tick.

  * ``governed_service_active(name)`` — a dumb Redis read on the hot path of each governed
    Beat task. No signal recomputation, no DB. Fail-open: when the governor is disabled or has
    not written state yet, it returns True so tasks never strand.

Governed Beat tasks call ``governed_service_active()`` at entry and return
``{"skipped": "governed_idle"}`` when inactive.

Registration vs governance: the env ``*_ENABLED`` flags remain the Beat *registration* switch.
The governor only idles/wakes tasks that Beat registered at startup — it cannot wake a task
whose Beat entry never registered (``*_ENABLED=0``). To bring a service under governance, set
its ``*_ENABLED=1`` and restart Beat once; the governor then idles/wakes it with no further
restarts. Producer-driven signals (e.g. erome_view_sync) wake on
``touch_service_activity(name)`` — call that where the relevant work is produced. A service is
only added to GOVERNED_SERVICES once a real wake source exists; income_poll is intentionally
NOT governed (default-enabled, no producer signal) so it keeps running as before.

The governor is opt-in via ``TBCC_IDLE_GOVERNOR_ENABLED`` (default off). While off, the gate is
a pure pass-through and nothing changes.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Per-service desired state + activity. <name> is a stable governor id (not a service_id).
_KEY_ACTIVE = "tbcc:idle:{name}:active"
_KEY_LAST_ACTIVITY = "tbcc:idle:{name}:last_activity"
_KEY_LAST_EVAL = "tbcc:idle:governor:last_eval"


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _rget(key: str) -> str | None:
    try:
        return _redis_client().get(key)
    except Exception:
        return None


def _rset(key: str, value: str, ex: int | None = 86400) -> None:
    try:
        _redis_client().set(key, value, ex=ex)
    except Exception:
        logger.debug("idle governor redis set failed key=%s", key, exc_info=True)


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def governor_enabled() -> bool:
    """Opt-in. While off, governed_service_active() is a pass-through (always True)."""
    return _env_flag("TBCC_IDLE_GOVERNOR_ENABLED", False)


def _eval_interval_s() -> int:
    raw = (os.getenv("TBCC_IDLE_GOVERNOR_INTERVAL_S") or "300").strip()
    try:
        return max(60, min(3600, int(raw)))
    except ValueError:
        return 300


def touch_service_activity(name: str) -> None:
    """
    Mark a producer-driven signal: <name> did work now (resets its idle window).
    Persist with no TTL — the idle window is enforced by the time math in _evaluate_service,
    so an early key expiry would truncate long windows (e.g. erome_view_sync's 72h).
    """
    _rset(_KEY_LAST_ACTIVITY.format(name=name), str(time.time()), ex=None)


def _minutes_since_activity(name: str) -> float | None:
    raw = _rget(_KEY_LAST_ACTIVITY.format(name=name))
    if not raw:
        return None
    try:
        return max(0.0, (time.time() - float(raw)) / 60.0)
    except (TypeError, ValueError):
        return None


def governed_service_active(name: str) -> bool:
    """
    Hot-path gate for governed tasks. Dumb Redis read — no signals, no DB.
    Fail-open: governor disabled, or no desired-state written yet -> True (never strand).
    """
    if not governor_enabled():
        return True
    raw = _rget(_KEY_ACTIVE.format(name=name))
    if raw is None:
        return True
    return raw == "1"


@dataclass(frozen=True)
class GovernedService:
    name: str
    idle_minutes_env: str
    idle_minutes_default: int
    # Evaluated in the tick only (may hit DB). True => there is a reason to be active now.
    wake: Callable[[Any], bool]
    needs_db: bool = False


def _idle_minutes(svc: GovernedService) -> int:
    raw = (os.getenv(svc.idle_minutes_env) or "").strip()
    try:
        return max(1, min(10080, int(raw)))
    except ValueError:
        return svc.idle_minutes_default


# --- wake signals (each self-contained; none require the gated task to run) ----------------

def _wake_export_flywheel(db) -> bool:
    try:
        from app.services.export_flywheel_service import build_export_proposals

        return len(build_export_proposals(db)) > 0
    except Exception:
        logger.debug("flywheel wake signal failed", exc_info=True)
        return False


def _wake_listening_relay(db) -> bool:
    # Dashboard toggle is the wake signal (never poll-derived — the poll is the gated task).
    try:
        from app.models.listening_relay_settings import ListeningRelaySettings

        row = (
            db.query(ListeningRelaySettings)
            .filter(ListeningRelaySettings.id == 1)
            .first()
        )
        return bool(row and row.enabled and row.channel_id)
    except Exception:
        logger.debug("listening_relay wake signal failed", exc_info=True)
        return False


def _wake_from_activity(name: str) -> Callable[[Any], bool]:
    # Producer-driven: recent touch_service_activity(name) means there is work to poll for.
    def _wake(_db) -> bool:
        mins = _minutes_since_activity(name)
        if mins is None:
            return False
        return mins < 5.0  # a fresh producer touch within the last tick window

    return _wake


GOVERNED_SERVICES: dict[str, GovernedService] = {
    "export_flywheel": GovernedService(
        name="export_flywheel",
        idle_minutes_env="TBCC_IDLE_FLYWHEEL_MINUTES",
        idle_minutes_default=1440,  # 24h
        wake=_wake_export_flywheel,
        needs_db=True,
    ),
    "listening_relay": GovernedService(
        name="listening_relay",
        idle_minutes_env="TBCC_IDLE_LISTENING_RELAY_MINUTES",
        idle_minutes_default=30,
        wake=_wake_listening_relay,
        needs_db=True,
    ),
    "erome_view_sync": GovernedService(
        name="erome_view_sync",
        idle_minutes_env="TBCC_IDLE_EROME_VIEW_SYNC_MINUTES",
        idle_minutes_default=4320,  # 72h
        wake=_wake_from_activity("erome_view_sync"),
    ),
    # income_poll is intentionally omitted: it is default-enabled and has no producer wake
    # signal, so governing it would permanently idle a running service. Wire
    # touch_service_activity("income_poll") into the revenue producer before adding it here.
}


def _evaluate_service(svc: GovernedService, db) -> bool:
    """
    Desired active state with hysteresis: a wake signal marks activity and returns active;
    with no signal, the service stays active until its idle window elapses since last activity.
    """
    try:
        awake = bool(svc.wake(db))
    except Exception:
        logger.debug("wake eval failed for %s", svc.name, exc_info=True)
        awake = False
    if awake:
        touch_service_activity(svc.name)
        return True
    mins = _minutes_since_activity(svc.name)
    if mins is None:
        return False
    return mins < _idle_minutes(svc)


def _ops_worker_up() -> bool | None:
    """celery_ops liveness from the background-maintained scheduling scan (cheap cache read)."""
    try:
        from app.services.system_health import cached_scheduling_health

        sched = cached_scheduling_health(max_age_s=120.0) or {}
        val = sched.get("celery_ops_worker_running")
        return bool(val) if val is not None else None
    except Exception:
        return None


def governor_tick(*, force: bool = False) -> dict[str, Any]:
    """
    Evaluate every governed service and persist desired-state. Rate-limited to the eval
    interval (the watch loop calls this often; the actual signal work runs ~every 5 min).
    Also surfaces celery_ops liveness so a dead ops worker is observable, not silent.
    """
    if not governor_enabled():
        return {"ok": True, "enabled": False}

    now = time.time()
    if not force:
        last_raw = _rget(_KEY_LAST_EVAL)
        try:
            if last_raw and (now - float(last_raw)) < _eval_interval_s():
                return {"ok": True, "enabled": True, "skipped": "interval"}
        except (TypeError, ValueError):
            pass
    _rset(_KEY_LAST_EVAL, str(now))

    db = None
    if any(s.needs_db for s in GOVERNED_SERVICES.values()):
        try:
            from app.database.session import SessionLocal

            db = SessionLocal()
        except Exception:
            logger.debug("idle governor could not open DB session", exc_info=True)

    states: dict[str, bool] = {}
    try:
        for name, svc in GOVERNED_SERVICES.items():
            active = _evaluate_service(svc, db)
            states[name] = active
            _rset(_KEY_ACTIVE.format(name=name), "1" if active else "0")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    ops_up = _ops_worker_up()
    if ops_up is False:
        # Load-bearing: listening_relay + storage_pool_seed are ungated Beat ticks that route
        # to the ops worker. Surface (do not auto-restart — that is opt-in / Phase 3.1).
        logger.warning(
            "idle governor: TBCC-Celery-Ops worker appears DOWN — ops_growth/ops_relay/"
            "ops_erome tasks will strand until it is restarted"
        )

    return {"ok": True, "enabled": True, "states": states, "ops_worker_up": ops_up}


def governor_snapshot() -> dict[str, Any]:
    """Cheap read of current desired-state + ops liveness (no evaluation). For health/dashboard."""
    if not governor_enabled():
        return {"enabled": False, "ops_worker_up": _ops_worker_up()}
    states = {
        name: (_rget(_KEY_ACTIVE.format(name=name)) == "1") for name in GOVERNED_SERVICES
    }
    return {"enabled": True, "states": states, "ops_worker_up": _ops_worker_up()}
