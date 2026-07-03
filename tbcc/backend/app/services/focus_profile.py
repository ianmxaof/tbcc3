"""
TBCC focus profiles — reduce background contention without stopping the full stack.

Profiles stop optional Windows services (via scripts/tbcc-focus-profile.ps1) and set Redis flags
workers/API read. Auto-reaction can engage ``telegram_relief`` on session lock storms.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REDIS_KEY_PROFILE = "tbcc:focus:profile"
REDIS_KEY_REASON = "tbcc:focus:reason"
REDIS_KEY_SINCE = "tbcc:focus:since"
REDIS_KEY_AUTO = "tbcc:focus:auto"
REDIS_KEY_STOPPED = "tbcc:focus:stopped_services"
REDIS_KEY_FLAGS = "tbcc:focus:flags"
REDIS_KEY_PREVIOUS = "tbcc:focus:previous_profile"
REDIS_KEY_LOCK_EVENTS = "tbcc:focus:lock_events_ts"
REDIS_KEY_LAST_EVAL = "tbcc:focus:last_eval"
REDIS_KEY_LAST_IMPORT_ACTIVITY = "tbcc:focus:last_import_activity"

VALID_PROFILES = frozenset({"off", "import_burst", "telegram_relief", "watch_folder", "minimal"})

# Service ids from Get-TbccStackServices (tbcc-service-control.ps1) — never stop these in any profile.
CORE_ALWAYS_UP = frozenset({"backend", "celery", "celery_post", "celery_post_scheduler", "dashboard", "beat"})

# Beat is never stopped — focus profiles use pause_beat so TBCC-Beat can stay up 24/7.
PROFILE_STOP_SERVICES: dict[str, list[str]] = {
    "import_burst": [
        "nsfw",
        "clip",
        "lustpress",
        "payment",
        "secretary",
        "macro_search",
        "loot",
        "album_composer",
    ],
    "telegram_relief": ["nsfw", "clip", "lustpress"],
    "watch_folder": [
        "payment",
        "secretary",
        "macro_search",
        "loot",
        "album_composer",
    ],
    "minimal": [
        "nsfw",
        "clip",
        "lustpress",
        "payment",
        "secretary",
        "macro_search",
        "loot",
        "album_composer",
        "forum",
    ],
    "off": [],
}

PROFILE_FLAGS: dict[str, dict[str, bool]] = {
    "import_burst": {
        "import_focus": True,
        "pause_auto_tag": True,
        "pause_beat": True,
        "skip_sidecar_enrich": True,
    },
    "telegram_relief": {
        "import_focus": False,
        "pause_auto_tag": True,
        # Keep Beat scheduling on — relief stops NSFW/CLIP/Lustpress Telethon contention only.
        "pause_beat": False,
        "skip_sidecar_enrich": True,
    },
    "watch_folder": {
        "import_focus": False,
        "pause_auto_tag": True,
        "pause_beat": True,
        "skip_sidecar_enrich": False,
    },
    "minimal": {
        "import_focus": False,
        "pause_auto_tag": True,
        "pause_beat": True,
        "skip_sidecar_enrich": True,
    },
    "off": {},
}


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def focus_auto_react_enabled() -> bool:
    return (os.getenv("TBCC_FOCUS_AUTO_REACT") or "1").strip().lower() in ("1", "true", "yes", "on")


def focus_auto_import_enabled() -> bool:
    return (os.getenv("TBCC_FOCUS_AUTO_IMPORT") or "1").strip().lower() in ("1", "true", "yes", "on")


def focus_watch_loop_enabled() -> bool:
    return focus_auto_react_enabled() or focus_auto_import_enabled()


def focus_import_jobs_threshold() -> int:
    try:
        return max(1, int(os.getenv("TBCC_FOCUS_IMPORT_JOBS_THRESHOLD") or "2"))
    except ValueError:
        return 2


def focus_lock_threshold() -> int:
    try:
        return max(2, int(os.getenv("TBCC_FOCUS_LOCK_EVENTS_THRESHOLD") or "3"))
    except ValueError:
        return 3


def focus_lock_window_s() -> int:
    try:
        return max(30, int(os.getenv("TBCC_FOCUS_LOCK_WINDOW_S") or "120"))
    except ValueError:
        return 120


def focus_telegram_relief_restore_minutes() -> int:
    """Auto-restore telegram_relief after session is calm this many minutes."""
    raw = (os.getenv("TBCC_FOCUS_TELEGRAM_RELIEF_RESTORE_MIN") or "5").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 5


def focus_idle_restore_minutes() -> int:
    try:
        return max(5, int(os.getenv("TBCC_FOCUS_IDLE_RESTORE_MIN") or "20"))
    except ValueError:
        return 20


def focus_import_idle_restore_minutes() -> int:
    raw = (os.getenv("TBCC_FOCUS_IMPORT_IDLE_RESTORE_MIN") or "").strip()
    if raw:
        try:
            return max(5, int(raw))
        except ValueError:
            pass
    return focus_idle_restore_minutes()


def focus_import_queue_only_restore_minutes() -> int:
    """When imports are only queued (none processing), restore focus sooner."""
    try:
        return max(2, int(os.getenv("TBCC_FOCUS_IMPORT_QUEUE_ONLY_RESTORE_MIN") or "3"))
    except ValueError:
        return 3


def count_active_import_jobs(*, include_queued: bool = True) -> int:
    """Non-terminal import jobs updated in the last 2 hours (same rule as /import/queue/status)."""
    try:
        from datetime import timedelta

        from app.database.session import SessionLocal
        from app.models.import_job import ImportJob
        from app.services.import_pipeline import TERMINAL_STATUSES

        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=2)
            q = db.query(ImportJob).filter(
                ImportJob.updated_at >= cutoff,
                ~ImportJob.status.in_(list(TERMINAL_STATUSES)),
            )
            if not include_queued:
                q = q.filter(ImportJob.status != "queued")
            return int(q.count())
        finally:
            db.close()
    except Exception:
        return 0


def count_processing_import_jobs() -> int:
    """Imports actively consuming workers — only these should block scheduling restore."""
    try:
        from datetime import timedelta

        from app.database.session import SessionLocal
        from app.models.import_job import ImportJob

        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=2)
            return int(
                db.query(ImportJob)
                .filter(
                    ImportJob.updated_at >= cutoff,
                    ImportJob.status == "processing",
                )
                .count()
            )
        finally:
            db.close()
    except Exception:
        return 0


def touch_import_activity() -> None:
    try:
        _redis_set(REDIS_KEY_LAST_IMPORT_ACTIVITY, str(time.time()), ex=86400)
    except Exception:
        pass


def _minutes_since_iso(since_raw: str) -> float | None:
    if not since_raw:
        return None
    try:
        since_dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - since_dt).total_seconds() / 60
    except Exception:
        return None


def _minutes_since_import_activity() -> float | None:
    raw = _redis_get(REDIS_KEY_LAST_IMPORT_ACTIVITY)
    if not raw:
        return None
    try:
        ts = float(raw)
        return (time.time() - ts) / 60
    except (TypeError, ValueError):
        return None


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _redis_get(key: str) -> str | None:
    try:
        r = _redis_client()
        v = r.get(key)
        return str(v) if v is not None else None
    except Exception:
        return None


def _redis_set(key: str, value: str, ex: int | None = None) -> None:
    r = _redis_client()
    if ex:
        r.set(key, value, ex=ex)
    else:
        r.set(key, value)


def _redis_delete(*keys: str) -> None:
    try:
        r = _redis_client()
        if keys:
            r.delete(*keys)
    except Exception:
        pass


def get_focus_state() -> dict[str, Any]:
    profile = (_redis_get(REDIS_KEY_PROFILE) or "off").strip().lower()
    if profile not in VALID_PROFILES:
        profile = "off"
    flags_raw = _redis_get(REDIS_KEY_FLAGS)
    flags: dict[str, bool] = {}
    if flags_raw:
        try:
            flags = json.loads(flags_raw)
        except json.JSONDecodeError:
            flags = {}
    stopped_raw = _redis_get(REDIS_KEY_STOPPED)
    stopped: list[str] = []
    if stopped_raw:
        try:
            stopped = json.loads(stopped_raw)
        except json.JSONDecodeError:
            stopped = []
    return {
        "profile": profile,
        "reason": _redis_get(REDIS_KEY_REASON) or "",
        "since": _redis_get(REDIS_KEY_SINCE) or "",
        "auto": (_redis_get(REDIS_KEY_AUTO) or "") == "1",
        "flags": flags,
        "stopped_services": stopped,
        "previous_profile": _redis_get(REDIS_KEY_PREVIOUS) or "",
    }


def focus_flags() -> dict[str, bool]:
    st = get_focus_state()
    if st["profile"] == "off":
        return {}
    return dict(st.get("flags") or PROFILE_FLAGS.get(st["profile"], {}))


def pause_auto_tag_work() -> bool:
    return bool(focus_flags().get("pause_auto_tag"))


def import_focus_active() -> bool:
    return bool(focus_flags().get("import_focus"))


def skip_sidecar_enrich() -> bool:
    return bool(focus_flags().get("skip_sidecar_enrich"))


def pause_beat_scheduling() -> bool:
    """When True, scheduler_worker skips enqueueing (Beat process may still run)."""
    return bool(focus_flags().get("pause_beat"))


def record_session_stress_event(source: str = "telethon") -> None:
    """Increment lock/stress counter for auto telegram_relief (sorted set by timestamp)."""
    try:
        r = _redis_client()
        now = time.time()
        member = f"{now}:{source}"
        r.zadd(REDIS_KEY_LOCK_EVENTS, {member: now})
        cutoff = now - focus_lock_window_s()
        r.zremrangebyscore(REDIS_KEY_LOCK_EVENTS, "-inf", cutoff)
    except Exception as e:
        logger.debug("record_session_stress_event failed: %s", e)


def lock_events_recent_count() -> int:
    try:
        r = _redis_client()
        now = time.time()
        cutoff = now - focus_lock_window_s()
        r.zremrangebyscore(REDIS_KEY_LOCK_EVENTS, "-inf", cutoff)
        return int(r.zcard(REDIS_KEY_LOCK_EVENTS) or 0)
    except Exception:
        return 0


def session_lock_storm_threshold() -> int:
    """
    Lock count that counts as a real storm (toasts / auto telegram_relief).
    Higher while imports are active — deposit + CLIP downloads briefly share Telethon sessions.
    """
    base = focus_lock_threshold()
    try:
        if count_active_import_jobs() > 0:
            return max(base + 4, base * 3)
    except Exception:
        pass
    return base


def session_lock_storm_active() -> bool:
    return lock_events_recent_count() >= session_lock_storm_threshold()


def _invoke_focus_ps1(profile: str, action: str) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"ok": False, "error": "focus_profiles require Windows (PowerShell service control)"}
    script = _tbcc_root() / "scripts" / "tbcc-focus-profile.ps1"
    if not script.is_file():
        return {"ok": False, "error": f"missing {script}"}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Profile",
                profile,
                "-Action",
                action,
                "-TbccRoot",
                str(_tbcc_root()),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            encoding="utf-8",
            errors="ignore",
        )
        out: dict[str, Any] = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-800:],
            "stderr": (proc.stderr or "")[-400:],
        }
        if proc.stdout:
            try:
                parsed = json.loads(proc.stdout.strip().splitlines()[-1])
                if isinstance(parsed, dict):
                    out.update(parsed)
            except (json.JSONDecodeError, IndexError):
                pass
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def apply_focus_profile(
    profile: str,
    *,
    reason: str = "",
    auto: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    profile = (profile or "off").strip().lower()
    if profile not in VALID_PROFILES:
        return {"ok": False, "error": f"unknown profile: {profile}"}

    current = get_focus_state()
    if profile == "off":
        return restore_focus_profile(reason=reason or "manual restore")

    if not force and current["profile"] == profile:
        return {"ok": True, "profile": profile, "unchanged": True, "state": current}

    if current["profile"] != "off" and current["profile"] != profile:
        _redis_set(REDIS_KEY_PREVIOUS, current["profile"])

    ps = _invoke_focus_ps1(profile, "apply")
    flags = PROFILE_FLAGS.get(profile, {})
    stopped = PROFILE_STOP_SERVICES.get(profile, [])
    now = datetime.now(timezone.utc).isoformat()
    _redis_set(REDIS_KEY_PROFILE, profile)
    _redis_set(REDIS_KEY_REASON, reason[:500] if reason else f"Applied {profile}")
    _redis_set(REDIS_KEY_SINCE, now)
    _redis_set(REDIS_KEY_AUTO, "1" if auto else "0")
    _redis_set(REDIS_KEY_FLAGS, json.dumps(flags))
    _redis_set(REDIS_KEY_STOPPED, json.dumps(stopped))

    logger.info("Focus profile applied: %s auto=%s reason=%s ps_ok=%s", profile, auto, reason, ps.get("ok"))
    return {
        "ok": True,
        "profile": profile,
        "reason": reason,
        "auto": auto,
        "powershell": ps,
        "flags": flags,
        "stopped_services": stopped,
        "since": now,
    }


def restore_focus_profile(*, reason: str = "") -> dict[str, Any]:
    current = get_focus_state()
    prev = current.get("profile") or "off"
    ps = _invoke_focus_ps1("off", "restore")
    _redis_set(REDIS_KEY_PROFILE, "off")
    _redis_set(REDIS_KEY_REASON, reason[:500] if reason else "Restored default stack")
    _redis_delete(REDIS_KEY_FLAGS, REDIS_KEY_STOPPED, REDIS_KEY_AUTO)
    _redis_set(REDIS_KEY_SINCE, datetime.now(timezone.utc).isoformat())
    logger.info("Focus profile restored (was %s) ps_ok=%s", prev, ps.get("ok"))
    return {
        "ok": True,
        "profile": "off",
        "previous": prev,
        "powershell": ps,
        "reason": reason,
    }


def evaluate_focus_triggers() -> dict[str, Any]:
    """
    Suggest or auto-apply a profile based on health signals. Never stops backend/celery.
    """
    from app.services.system_health import collect_system_health

    health = collect_system_health()
    state = get_focus_state()
    triggers: list[dict[str, Any]] = []
    suggested: str | None = None
    lock_n = lock_events_recent_count()

    if session_lock_storm_active():
        triggers.append(
            {
                "code": "session_lock_storm",
                "severity": "critical",
                "message": f"{lock_n} Telethon session lock/stress events in {focus_lock_window_s()}s",
                "suggested_profile": "telegram_relief",
            }
        )
        suggested = "telegram_relief"

    processing = count_processing_import_jobs()
    queued = count_active_import_jobs(include_queued=True) - processing
    burst_threshold = focus_import_jobs_threshold()
    if processing >= burst_threshold and state["profile"] == "off":
        triggers.append(
            {
                "code": "import_queue_busy",
                "severity": "warning",
                "message": (
                    f"{processing} import jobs running"
                    + (f" ({queued} queued)" if queued else "")
                    + " — "
                    + (
                        "import_burst will auto-apply"
                        if focus_auto_import_enabled()
                        else "consider import_burst"
                    )
                ),
                "suggested_profile": "import_burst",
            }
        )
        if not suggested and lock_n < focus_lock_threshold():
            suggested = "import_burst"

    if state["profile"] == "off":
        nsfw_cfg = bool((os.getenv("TBCC_NSFW_DETECT_URL") or "").strip())
        clip_cfg = bool((os.getenv("TBCC_CLIP_CATEGORIZE_URL") or "").strip())
        if (nsfw_cfg and not _port_open(8001)) or (clip_cfg and not _port_open(8002)):
            triggers.append(
                {
                    "code": "enrichment_sidecars_down",
                    "severity": "info",
                    "message": "NSFW/CLIP configured but sidecar not listening — enrich logs warnings; optional telegram_relief skips HTTP",
                    "suggested_profile": None,
                }
            )

    for c in health.get("conflicts") or []:
        code = str(c.get("code") or "")
        if code in ("scraper_running", "admin_bot_running") and state["profile"] == "off":
            triggers.append(
                {
                    "code": code,
                    "severity": "warning",
                    "message": c.get("message") or code,
                    "suggested_profile": "telegram_relief",
                }
            )
            if not suggested:
                suggested = "telegram_relief"

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "current": state,
        "triggers": triggers,
        "suggested_profile": suggested,
        "lock_events": lock_n,
        "active_import_jobs": processing + queued,
        "processing_import_jobs": processing,
        "queued_import_jobs": queued,
        "auto_react_enabled": focus_auto_react_enabled(),
        "auto_import_enabled": focus_auto_import_enabled(),
    }
    _redis_set(REDIS_KEY_LAST_EVAL, result["timestamp"], ex=3600)
    return result


def _port_open(port: int) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except OSError:
        return False


def on_fast_import_queued(source: str = "import") -> dict[str, Any] | None:
    """
    Immediate import_burst when auto-import is on (first fast-import enqueue).
    Skipped during session lock storms (telegram_relief takes priority).
    """
    touch_import_activity()
    if not focus_auto_import_enabled():
        return None
    if session_lock_storm_active():
        return None
    state = get_focus_state()
    if state["profile"] != "off":
        return None
    return apply_focus_profile(
        "import_burst",
        reason=f"Auto: fast import queued ({source})",
        auto=True,
    )


def sync_focus_flags_from_profile() -> bool:
    """Refresh Redis flags when PROFILE_FLAGS change (e.g. telegram_relief no longer pauses Beat)."""
    st = get_focus_state()
    profile = (st.get("profile") or "off").strip().lower()
    if profile == "off":
        return False
    expected = PROFILE_FLAGS.get(profile, {})
    current = dict(st.get("flags") or {})
    if current == expected:
        return False
    _redis_set(REDIS_KEY_FLAGS, json.dumps(expected))
    return True


def evaluate_and_maybe_auto_apply() -> dict[str, Any]:
    sync_focus_flags_from_profile()
    ev = evaluate_focus_triggers()
    ev["auto_applied"] = False
    state = get_focus_state()
    lock_n = lock_events_recent_count()
    processing = count_processing_import_jobs()
    queued = count_active_import_jobs(include_queued=True) - processing

    if processing > 0:
        touch_import_activity()

    if state["profile"] != "off":
        if (
            session_lock_storm_active()
            and state["profile"] != "telegram_relief"
            and focus_auto_react_enabled()
        ):
            applied = apply_focus_profile(
                "telegram_relief",
                reason="Auto: session lock storm during focus profile",
                auto=True,
            )
            ev["auto_applied"] = applied.get("ok", False)
            ev["apply_result"] = applied
            return ev

        if state["profile"] == "telegram_relief" and focus_auto_react_enabled():
            if not session_lock_storm_active():
                idle_min = _minutes_since_iso(state.get("since") or "")
                restore_after = focus_telegram_relief_restore_minutes()
                if idle_min is not None and idle_min >= restore_after:
                    ev["auto_restored"] = restore_focus_profile(
                        reason=f"Auto-restore: session calm for {int(idle_min)}m"
                    )
            elif lock_n < 1:
                idle_min = _minutes_since_iso(state.get("since") or "")
                if idle_min is not None and idle_min >= focus_idle_restore_minutes():
                    ev["auto_restored"] = restore_focus_profile(reason="Auto-restore after idle (session calm)")

        elif (
            state["profile"] == "import_burst"
            and state.get("auto")
            and focus_auto_import_enabled()
            and processing == 0
        ):
            idle_min = _minutes_since_import_activity()
            if idle_min is None:
                idle_min = _minutes_since_iso(state.get("since") or "")
            restore_after = focus_import_idle_restore_minutes()
            if queued > 0:
                # Stale queued backlog should not block scheduling indefinitely.
                restore_after = min(restore_after, focus_import_queue_only_restore_minutes())
            if idle_min is not None and idle_min >= restore_after:
                ev["auto_restored"] = restore_focus_profile(
                    reason=(
                        f"Auto-restore: no running imports for {int(idle_min)}m"
                        + (f" ({queued} still queued)" if queued else "")
                    )
                )

        return ev

    if focus_auto_react_enabled() and session_lock_storm_active():
        applied = apply_focus_profile(
            "telegram_relief",
            reason="Auto: Telethon session lock storm detected",
            auto=True,
        )
        ev["auto_applied"] = applied.get("ok", False)
        ev["apply_result"] = applied
        return ev

    if focus_auto_import_enabled() and processing >= focus_import_jobs_threshold():
        applied = apply_focus_profile(
            "import_burst",
            reason=(
                f"Auto: {processing} import jobs running (threshold {focus_import_jobs_threshold()})"
                + (f", {queued} queued" if queued else "")
            ),
            auto=True,
        )
        ev["auto_applied"] = applied.get("ok", False)
        ev["apply_result"] = applied
        return ev

    return ev


def focus_public_snapshot() -> dict[str, Any]:
    st = get_focus_state()
    ev = evaluate_focus_triggers()
    return {
        "state": st,
        "evaluation": {
            "suggested_profile": ev.get("suggested_profile"),
            "triggers": ev.get("triggers"),
            "lock_events": ev.get("lock_events"),
            "active_import_jobs": ev.get("active_import_jobs"),
            "auto_react_enabled": ev.get("auto_react_enabled"),
            "auto_import_enabled": ev.get("auto_import_enabled"),
        },
    }
