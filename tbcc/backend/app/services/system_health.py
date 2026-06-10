"""
Operational health snapshot: infra, port conflicts, Telethon session risks, import queue depth.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# One-click remediations surfaced in the dashboard health banner.
CONFLICT_ACTIONS: dict[str, dict[str, str]] = {
    "uvicorn_orphans": {"action": "cleanup_uvicorn_orphans", "action_label": "Fix orphan workers"},
    "api_port_duplicate": {"action": "cleanup_uvicorn_orphans", "action_label": "Clear port 8000 conflicts"},
    "redis_down": {"action": "start_docker_redis", "action_label": "Start Redis (Docker)"},
    "postgres_down": {"action": "start_docker_postgres", "action_label": "Start Postgres (Docker)"},
    "session_lock_storm": {"action": "focus_telegram_relief", "action_label": "Telegram relief focus"},
    "celery_queue_backlog": {
        "action": "purge_celery_queues",
        "action_label": "Purge stale Celery queues",
    },
    "beat_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
    "celery_worker_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
    "celery_post_worker_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
}

from sqlalchemy import text

from app.database.session import SessionLocal, engine
from app.services.import_pipeline import TERMINAL_STATUSES, fast_import_enabled
from app.utils.telethon_session import (
    admin_session_stem,
    poster_session_stem,
    telethon_sessions_share_file,
)


def _port_listening(port: int) -> bool:
    """True if something accepts TCP on this port locally (IPv4 or IPv6 loopback)."""
    for host in ("127.0.0.1", "localhost", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.8):
                return True
        except OSError:
            continue
    return False


def _count_port_listeners(port: int) -> int:
    if platform.system() != "Windows":
        return 1 if _port_listening(port) else 0
    try:
        import subprocess

        out = subprocess.check_output(
            ["netstat", "-ano"],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        n = 0
        needle = f":{port} "
        for line in out.splitlines():
            if "LISTENING" in line and f"127.0.0.1{needle}" in line.replace("  ", " "):
                n += 1
        return max(n, 1 if _port_listening(port) else 0)
    except Exception:
        return 1 if _port_listening(port) else 0


def _win_process_command_lines(pattern: str) -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    try:
        import subprocess
        import json

        ps = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -and ($_.CommandLine -match '{pattern}') }} | "
            "Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"
        )
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        ).strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "pid": d.get("ProcessId"),
                "name": d.get("Name"),
                "command_line": (d.get("CommandLine") or "") or "",
            }
            for d in data
            if d
        ]
    except Exception:
        return []


def _win_processes_matching(pattern: str) -> list[dict[str, Any]]:
    return _win_process_command_lines(pattern)


def _orphan_uvicorn_workers() -> int:
    """Uvicorn --reload leaves multiprocessing-fork children; ignore unrelated fork workers."""
    procs = _win_process_command_lines("multiprocessing-fork|multiprocessing\\.spawn")
    n = 0
    for p in procs:
        cmd = (p.get("command_line") or "").lower()
        if "uvicorn" in cmd or "app.main:app" in cmd:
            n += 1
            continue
        if "multiprocessing-fork" in cmd and "python" in (p.get("name") or "").lower():
            n += 1
    return n


def cleanup_uvicorn_orphans() -> dict[str, Any]:
    """Kill stale uvicorn reload workers (Windows). Safe no-op on other OS."""
    if platform.system() != "Windows":
        return {"ok": True, "killed": 0, "platform": platform.system(), "note": "not_windows"}
    killed: list[int] = []
    for p in _win_process_command_lines("multiprocessing-fork|multiprocessing\\.spawn"):
        cmd = (p.get("command_line") or "").lower()
        pid = p.get("pid")
        if not pid:
            continue
        if "uvicorn" in cmd or "app.main:app" in cmd or (
            "multiprocessing-fork" in cmd and "celery" not in cmd and "bots." not in cmd
        ):
            try:
                import subprocess

                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
                killed.append(int(pid))
            except Exception:
                pass
    return {"ok": True, "killed": len(killed), "pids": killed}


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _conflict(
    code: str,
    severity: str,
    message: str,
    *,
    action: str | None = None,
    action_label: str | None = None,
) -> dict[str, str]:
    row: dict[str, str] = {"code": code, "severity": severity, "message": message}
    meta = CONFLICT_ACTIONS.get(code, {})
    act = action or meta.get("action")
    label = action_label or meta.get("action_label")
    if act:
        row["action"] = act
        row["action_label"] = label or "Fix"
    return row


def start_docker_infra(services: list[str]) -> dict[str, Any]:
    """Best-effort: docker compose up for redis/postgres (local TBCC infra file)."""
    root = _tbcc_root()
    compose = root / "infra" / "docker-compose.infra.yml"
    if not compose.is_file():
        return {"ok": False, "error": f"compose file not found: {compose}"}
    try:
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose),
                "up",
                "-d",
                *services,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(root / "infra"),
        )
        return {
            "ok": proc.returncode == 0,
            "services": services,
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-500:],
            "returncode": proc.returncode,
        }
    except FileNotFoundError:
        return {"ok": False, "error": "docker not on PATH"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def start_tbcc_stack_services(service_ids: list[str]) -> dict[str, Any]:
    """Start TBCC Windows stack tabs via tbcc-service-control.ps1 (Beat, Celery, etc.)."""
    if platform.system() != "Windows":
        return {"ok": False, "error": "stack service launch is Windows-only"}
    root = _tbcc_root()
    script = root / "scripts" / "_start-scheduling-stack.ps1"
    if script.is_file() and set(service_ids) >= {"beat", "celery", "celery_post"}:
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                cwd=str(root),
            )
            return {
                "ok": proc.returncode == 0,
                "services": service_ids,
                "stdout": (proc.stdout or "")[-500:],
                "stderr": (proc.stderr or "")[-500:],
                "returncode": proc.returncode,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    ps1 = root / "scripts" / "tbcc-service-control.ps1"
    if not ps1.is_file():
        return {"ok": False, "error": f"missing {ps1}"}
    ids = [s.strip() for s in service_ids if s and s.strip()]
    if not ids:
        return {"ok": False, "error": "no service ids"}
    id_list = ",".join(f'"{i}"' for i in ids)
    ps_cmd = (
        f'. "{ps1}"; '
        f'$root = "{root}"; '
        f'foreach ($id in @({id_list})) {{ '
        f'$svc = Get-TbccStackServices -TbccRoot $root -FullStack | Where-Object {{ $_.Id -eq $id }} | Select-Object -First 1; '
        f'if ($svc) {{ Start-TbccStackService -Service $svc -TbccRoot $root -UseErrorHubWrapper }} '
        f'}}'
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(root),
        )
        return {
            "ok": proc.returncode == 0,
            "services": ids,
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-500:],
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def remediate_system_issues(codes: list[str] | None = None) -> dict[str, Any]:
    """Run automated fixes for known conflict codes (dashboard one-click)."""
    snapshot = collect_system_health()
    want = {c.strip() for c in (codes or []) if c and c.strip()}
    if not want:
        want = {str(c.get("code") or "") for c in snapshot.get("conflicts", [])}
    want.discard("")

    results: list[dict[str, Any]] = []

    if "uvicorn_orphans" in want or "api_port_duplicate" in want:
        r = cleanup_uvicorn_orphans()
        results.append({"code": "cleanup_uvicorn_orphans", **r})

    if "redis_down" in want:
        r = start_docker_infra(["redis"])
        results.append({"code": "start_docker_redis", **r})

    if "postgres_down" in want:
        r = start_docker_infra(["postgres"])
        results.append({"code": "start_docker_postgres", **r})

    if (
        "beat_down" in want
        or "celery_worker_down" in want
        or "celery_post_worker_down" in want
        or "start_scheduling_stack" in want
    ):
        r = start_tbcc_stack_services(["beat", "celery", "celery_post"])
        results.append({"code": "start_scheduling_stack", **r})

    if "session_lock_storm" in want or "focus_telegram_relief" in want:
        try:
            from app.services.focus_profile import apply_focus_profile

            r = apply_focus_profile(
                "telegram_relief",
                reason="Health banner: session lock storm",
                auto=False,
            )
            results.append({"code": "focus_telegram_relief", **r})
        except Exception as e:
            results.append({"code": "focus_telegram_relief", "ok": False, "error": str(e)[:200]})

    if "celery_queue_backlog" in want or "purge_celery_queues" in want:
        try:
            from app.services.celery_queue_ops import purge_celery_queues

            r = purge_celery_queues(["celery", "post"], min_length=1)
            results.append({"code": "purge_celery_queues", **r})
        except Exception as e:
            results.append({"code": "purge_celery_queues", "ok": False, "error": str(e)[:200]})

    if "import_queue_busy" in want or "focus_import_burst" in want:
        try:
            from app.services.focus_profile import apply_focus_profile

            r = apply_focus_profile(
                "import_burst",
                reason="Health banner: import queue busy",
                auto=False,
            )
            results.append({"code": "focus_import_burst", **r})
        except Exception as e:
            results.append({"code": "focus_import_burst", "ok": False, "error": str(e)[:200]})

    health = collect_system_health()
    return {"ok": health.get("ok", False), "results": results, "health": health}


def _scheduling_process_counts() -> dict[str, int]:
    beat = len(_win_processes_matching(r"app\.workers\.celery_app beat|celery.*\sbeat\s"))
    worker = len(
        _win_processes_matching(r"app\.workers\.celery_app worker|celery.*\sworker\s")
    )
    return {"beat": beat, "celery_worker": worker}


def collect_scheduling_health() -> dict[str, Any]:
    """Beat + Celery worker presence for pool/scheduled post cron (Windows process match)."""
    counts = _scheduling_process_counts()
    post_workers = len(
        _win_processes_matching(r"celery.*-Q\s+post|celery.*-n\s+post@")
    )
    pause = False
    focus_profile = "off"
    try:
        from app.services.focus_profile import get_focus_state, pause_beat_scheduling

        pause = pause_beat_scheduling()
        focus_profile = (get_focus_state().get("profile") or "off").strip().lower()
    except Exception:
        pass
    pool_auto = True
    try:
        from app.services.post_scheduler import pool_auto_post_enabled

        pool_auto = pool_auto_post_enabled()
    except Exception:
        pass
    return {
        "beat_processes": counts["beat"],
        "celery_worker_processes": counts["celery_worker"],
        "celery_post_worker_processes": post_workers,
        "beat_running": counts["beat"] > 0,
        "celery_worker_running": counts["celery_worker"] > 0,
        "celery_post_worker_running": post_workers > 0,
        "pool_auto_post_enabled": pool_auto,
        "scheduling_paused_by_focus": pause,
        "focus_profile": focus_profile,
    }


def _redis_ok() -> tuple[bool, str | None]:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        r = redis.from_url(url, socket_connect_timeout=1.5)
        r.ping()
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def collect_system_health() -> dict[str, Any]:
    conflicts: list[dict[str, str]] = []
    recommendations: list[str] = []

    redis_ok, redis_err = _redis_ok()
    if not redis_ok:
        conflicts.append(
            _conflict(
                "redis_down",
                "critical",
                f"Redis unreachable: {redis_err}",
            )
        )

    pg_ok = _port_listening(5432)
    if not pg_ok:
        conflicts.append(
            _conflict(
                "postgres_down",
                "warning",
                "Postgres not listening on :5432",
            )
        )

    api_listeners = _count_port_listeners(8000)
    if api_listeners > 1:
        conflicts.append(
            _conflict(
                "api_port_duplicate",
                "critical",
                f"Multiple listeners on :8000 ({api_listeners}) — API may hang",
            )
        )

    orphans = _orphan_uvicorn_workers()
    if orphans > 0:
        conflicts.append(
            _conflict(
                "uvicorn_orphans",
                "critical",
                f"{orphans} orphan uvicorn worker process(es) detected",
            )
        )

    if telethon_sessions_share_file():
        conflicts.append(
            _conflict(
                "telethon_shared_session",
                "warning",
                f"Admin and poster share {admin_session_stem()}.session — SQLite lock risk",
            )
        )
        recommendations.append("Set TBCC_POSTER_TELEGRAM_SESSION=poster_bot in tbcc/.env")

    # Standalone `python -m bots.scraper_bot` (not the Goonique row in Sources; not Celery unless task is active).
    scraper = _win_processes_matching(r"-m\s+bots\.scraper_bot|run_scrape_once\.py")
    if scraper:
        conflicts.append(
            _conflict(
                "scraper_running",
                "warning",
                (
                    f"Telegram scraper process running ({len(scraper)}). "
                    "Uses scraper.session — still adds Telethon load alongside API/Celery. "
                    "Sources → Goonique only runs when you click Scrape now or run scripts/run_scrape_once.py."
                ),
            )
        )

    admin_bot = _win_processes_matching("admin_bot\\.py")
    if admin_bot:
        conflicts.append(
            _conflict(
                "admin_bot_running",
                "warning",
                f"admin_bot running ({len(admin_bot)} process(es))",
            )
        )

    active_imports = 0
    try:
        db = SessionLocal()
        try:
            from app.models.import_job import ImportJob

            cutoff = datetime.utcnow() - timedelta(hours=2)
            active_imports = (
                db.query(ImportJob)
                .filter(
                    ImportJob.updated_at >= cutoff,
                    ~ImportJob.status.in_(list(TERMINAL_STATUSES)),
                )
                .count()
            )
        finally:
            db.close()
    except Exception:
        active_imports = -1

    try:
        from app.services.focus_profile import (
            count_active_import_jobs,
            focus_auto_import_enabled,
            focus_import_jobs_threshold,
            get_focus_state,
            lock_events_recent_count,
            focus_auto_react_enabled,
        )

        active_imports = count_active_import_jobs()
        focus_prof = (get_focus_state().get("profile") or "off").strip().lower()
        if (
            active_imports >= focus_import_jobs_threshold()
            and focus_prof == "off"
            and lock_events_recent_count() < 2
        ):
            msg = (
                f"{active_imports} active import jobs — import_burst "
                + ("will auto-apply" if focus_auto_import_enabled() else "recommended")
            )
            conflicts.append(
                _conflict(
                    "import_queue_busy",
                    "warning",
                    msg,
                    action=None if focus_auto_import_enabled() else "focus_import_burst",
                    action_label=None if focus_auto_import_enabled() else "Import burst focus",
                )
            )
    except Exception:
        pass

    sched = collect_scheduling_health()
    try:
        from app.services.celery_queue_ops import celery_queue_snapshot

        qsnap = celery_queue_snapshot()
        sched["queues"] = qsnap.get("queues") if qsnap.get("ok") else {}
        post_len = int((qsnap.get("queues") or {}).get("post", {}).get("length") or 0)
        celery_len = int((qsnap.get("queues") or {}).get("celery", {}).get("length") or 0)
        if redis_ok and (post_len >= 50 or celery_len >= 200):
            conflicts.append(
                _conflict(
                    "celery_queue_backlog",
                    "critical",
                    (
                        f"Celery backlog: post queue={post_len}, celery queue={celery_len}. "
                        "Scheduled posts are waiting behind stale tasks — purge queues and restart TBCC-Celery + TBCC-Celery-Post."
                    ),
                    action="purge_celery_queues",
                    action_label="Purge stale Celery queues",
                )
            )
    except Exception:
        pass

    if redis_ok and not sched.get("beat_running"):
        conflicts.append(
            _conflict(
                "beat_down",
                "critical",
                "TBCC-Beat is not running — pool intervals and recurring posts will not enqueue. Start TBCC-Beat (full stack or tray).",
            )
        )
    if redis_ok and not sched.get("celery_worker_running"):
        conflicts.append(
            _conflict(
                "celery_worker_down",
                "critical",
                "TBCC-Celery worker is not running — imports and side tasks will stall.",
            )
        )
    if redis_ok and not sched.get("celery_post_worker_running"):
        conflicts.append(
            _conflict(
                "celery_post_worker_down",
                "critical",
                "TBCC-Celery-Post is not running — scheduled posts and pool cron will not send. Start TBCC-Celery-Post (full stack).",
            )
        )
    if sched.get("scheduling_paused_by_focus"):
        conflicts.append(
            _conflict(
                "scheduling_paused_focus",
                "warning",
                f"Focus profile «{sched.get('focus_profile')}» paused Beat scheduling (TBCC-Beat may still run). Set Focus → Off to resume cron.",
            )
        )

    try:
        from app.services.focus_profile import lock_events_recent_count, focus_auto_react_enabled

        if lock_events_recent_count() >= 2:
            conflicts.append(
                _conflict(
                    "session_lock_storm",
                    "critical",
                    (
                        f"Telethon session stress ({lock_events_recent_count()} events). "
                        "Use Focus → Telegram relief (or wait for auto-react)."
                    ),
                    action="focus_telegram_relief",
                    action_label="Telegram relief focus",
                )
            )
            if not focus_auto_react_enabled():
                recommendations.append("Set TBCC_FOCUS_AUTO_REACT=1 for automatic telegram_relief profile.")
    except Exception:
        pass

    fixable = [c for c in conflicts if c.get("action")]
    if fixable:
        recommendations.append("Use Fix buttons in the banner above — no scripts required.")

    try:
        from app.services.focus_profile import get_focus_state, lock_events_recent_count

        focus_block = {
            "active": get_focus_state(),
            "lock_events_recent": lock_events_recent_count(),
        }
    except Exception:
        focus_block = None

    db_url = str(engine.url)
    return {
        "ok": len([c for c in conflicts if c["severity"] == "critical"]) == 0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "platform": platform.system(),
        "fast_import_enabled": fast_import_enabled(),
        "ports": {
            "api_8000": _port_listening(8000),
            "dashboard_5173": _port_listening(5173),
            "redis_6379": _port_listening(6379),
            "postgres_5432": pg_ok,
            "api_listener_count": api_listeners,
        },
        "redis": {"ok": redis_ok, "error": redis_err},
        "database": {"dialect": "postgresql" if "postgresql" in db_url else "sqlite"},
        "telethon": {
            "admin_session": admin_session_stem(),
            "poster_session": poster_session_stem(),
            "sessions_share_file": telethon_sessions_share_file(),
        },
        "import_pipeline": {"active_jobs": active_imports},
        "scheduling": sched,
        "orphan_uvicorn_workers": orphans,
        "conflicts": conflicts,
        "recommendations": recommendations,
        "fixable_count": len(fixable),
        "focus": focus_block,
    }


def auto_remediate_on_startup() -> dict[str, Any]:
    """Called when the API boots: clear reload orphans before serving traffic."""
    out = cleanup_uvicorn_orphans()
    if out.get("killed", 0) > 0:
        logger.info("Startup auto-cleanup: killed %s uvicorn orphan worker(s)", out["killed"])
    return out
