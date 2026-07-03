"""
Operational health snapshot: infra, port conflicts, Telethon session risks, import queue depth.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
import time
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
        "action": "resume_scheduled_posting",
        "action_label": "Resume scheduled posting",
    },
    "schedulers_overdue": {
        "action": "resume_scheduled_posting",
        "action_label": "Resume scheduled posting",
    },
    "scheduling_paused_focus": {
        "action": "restore_focus",
        "action_label": "End focus (resume scheduling)",
    },
    "beat_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
    "celery_worker_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
    "celery_post_worker_down": {"action": "start_scheduling_stack", "action_label": "Start Beat + Celery"},
    "celery_post_scheduler_worker_down": {
        "action": "start_scheduling_stack",
        "action_label": "Start Beat + Celery",
    },
    "celery_post_worker_duplicate": {
        "action": "trim_scheduling_workers",
        "action_label": "Trim duplicate workers",
    },
    "beat_duplicate": {
        "action": "trim_scheduling_workers",
        "action_label": "Trim duplicate Beat",
    },
    "celery_worker_duplicate": {
        "action": "trim_scheduling_workers",
        "action_label": "Trim duplicate Celery",
    },
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
            "Select-Object ProcessId, ParentProcessId, Name, CommandLine | ConvertTo-Json -Compress"
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
                "parent_pid": d.get("ParentProcessId"),
                "name": d.get("Name"),
                "command_line": (d.get("CommandLine") or "") or "",
            }
            for d in data
            if d
        ]
    except Exception:
        return []


def _win_leaf_worker_pids(procs: list[dict[str, Any]]) -> list[int]:
    """Count py.exe + python.exe launcher pairs as one worker (matches process-audit.ps1)."""
    import re

    # Ignore cmd.exe / WT shells — their command lines embed the celery argv but are not workers.
    worker_procs = [
        p
        for p in procs
        if re.match(r"^(python|py)(\d+)?\.exe$", (p.get("name") or "").lower())
    ]
    if len(worker_procs) <= 1:
        return [int(p["pid"]) for p in worker_procs if p.get("pid")]
    pid_set = {int(p["pid"]) for p in worker_procs if p.get("pid")}
    leaf: list[int] = []
    seen: set[int] = set()
    for p in worker_procs:
        pid = p.get("pid")
        if not pid:
            continue
        ipid = int(pid)
        if ipid in seen:
            continue
        name = (p.get("name") or "").lower()
        if name == "py.exe":
            children = [
                c for c in worker_procs if c.get("parent_pid") == ipid and c.get("pid") in pid_set
            ]
            if children:
                continue
        seen.add(ipid)
        leaf.append(ipid)
    return leaf


def _win_leaf_workers_matching(pattern: str) -> list[dict[str, Any]]:
    procs = _win_process_command_lines(pattern)
    leaf_pids = set(_win_leaf_worker_pids(procs))
    return [p for p in procs if p.get("pid") in leaf_pids]


def _win_leaf_worker_count(pattern: str) -> int:
    return len(_win_leaf_worker_pids(_win_process_command_lines(pattern)))


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


def trim_scheduling_worker_duplicates() -> dict[str, Any]:
    """Trim duplicate Beat / Celery / Celery-Post workers (Windows)."""
    if platform.system() != "Windows":
        return {"ok": True, "trimmed": 0, "note": "not_windows"}
    root = _tbcc_root()
    script = root / "scripts" / "kill-celery-post-strays.ps1"
    if not script.is_file():
        return {"ok": False, "error": f"missing {script}"}
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
            timeout=120,
            cwd=str(root),
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": (proc.stdout or "")[-800:],
            "stderr": (proc.stderr or "")[-400:],
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _maybe_auto_trim_scheduling_duplicates(sched: dict[str, Any]) -> None:
    """Best-effort singleton trim when health poll sees duplicate Beat/Celery workers (cooldown)."""
    if platform.system() != "Windows":
        return
    beat = int(sched.get("beat_processes") or 0)
    celery = int(sched.get("celery_worker_processes") or 0)
    post = int(sched.get("celery_post_worker_processes") or 0)
    if beat <= 1 and celery <= 1 and post <= 1:
        return
    root = _tbcc_root()
    cooldown = root / ".tbcc-run" / "health-auto-trim-cooldown.txt"
    try:
        if cooldown.is_file():
            raw = cooldown.read_text(encoding="utf-8").strip()
            if raw:
                last = datetime.fromisoformat(raw)
                if (datetime.now() - last).total_seconds() < 90:
                    return
    except Exception:
        pass
    try:
        trim_scheduling_worker_duplicates()
        cooldown.parent.mkdir(parents=True, exist_ok=True)
        cooldown.write_text(datetime.now().isoformat(), encoding="utf-8")
    except Exception as e:
        logger.debug("auto trim scheduling workers failed: %s", e)


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
    if script.is_file() and {"beat", "celery", "celery_post", "celery_post_scheduler"} <= set(service_ids):
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

    if (
        "scheduling_paused_focus" in want
        or "restore_focus" in want
        or "focus_restore" in want
    ):
        try:
            from app.services.focus_profile import get_focus_state, restore_focus_profile

            st = get_focus_state()
            if (st.get("profile") or "off") != "off":
                r = restore_focus_profile(reason="Health banner: resume scheduling")
                results.append({"code": "restore_focus", **r})
            else:
                results.append({"code": "restore_focus", "ok": True, "skipped": "already_off"})
        except Exception as e:
            results.append({"code": "restore_focus", "ok": False, "error": str(e)[:200]})

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
        "celery_post_worker_duplicate" in want
        or "beat_duplicate" in want
        or "celery_worker_duplicate" in want
        or "trim_scheduling_workers" in want
    ):
        r = trim_scheduling_worker_duplicates()
        results.append({"code": "trim_scheduling_workers", **r})

    if (
        "beat_down" in want
        or "celery_worker_down" in want
        or "celery_post_worker_down" in want
        or "celery_post_scheduler_worker_down" in want
        or "start_scheduling_stack" in want
    ):
        r = start_tbcc_stack_services(["beat", "celery", "celery_post", "celery_post_scheduler"])
        results.append({"code": "start_scheduling_stack", **r})

    if "session_lock_storm" in want or "focus_telegram_relief" in want:
        try:
            from app.services.focus_profile import apply_focus_profile, get_focus_state

            current = (get_focus_state().get("profile") or "off").strip().lower()
            if current == "telegram_relief":
                results.append(
                    {
                        "code": "focus_telegram_relief",
                        "ok": True,
                        "skipped": "already_telegram_relief",
                    }
                )
            else:
                r = apply_focus_profile(
                    "telegram_relief",
                    reason="Health banner: session lock storm",
                    auto=False,
                )
                results.append({"code": "focus_telegram_relief", **r})
        except Exception as e:
            results.append({"code": "focus_telegram_relief", "ok": False, "error": str(e)[:200]})

    if "celery_queue_backlog" in want or "purge_celery_queues" in want or "resume_scheduled_posting" in want:
        try:
            from app.services.post_scheduler import resume_scheduled_posting

            r = resume_scheduled_posting(purge_post_queue=True)
            results.append({"code": "resume_scheduled_posting", **r})
        except Exception as e:
            results.append({"code": "resume_scheduled_posting", "ok": False, "error": str(e)[:200]})

    if "purge_celery_queues" in want and "resume_scheduled_posting" not in want:
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
    beat = _win_leaf_worker_count(r"app\.workers\.celery_app beat")
    worker = _win_leaf_worker_count(r"app\.workers\.celery_app worker.*-Q\s+celery")
    post_scheduler = _win_leaf_worker_count(
        r"app\.workers\.celery_app worker.*-Q\s+post_scheduler|-n\s+scheduler@"
    )
    post = _win_leaf_worker_count(
        r"app\.workers\.celery_app worker.*-Q\s+post\s+-n\s+post@"
    )
    return {
        "beat": beat,
        "celery_worker": worker,
        "celery_post_scheduler": post_scheduler,
        "celery_post": post,
    }


# Background-maintained cache of the (expensive) scheduling process scan so the fast
# health endpoint never has to run powershell/netstat on a request thread.
_SCHEDULING_HEALTH_CACHE: dict[str, Any] = {}


def cached_scheduling_health(max_age_s: float = 40.0) -> dict[str, Any] | None:
    """Last scheduling-health scan if fresh enough, else None. Read from any thread."""
    cache = _SCHEDULING_HEALTH_CACHE
    if cache and (time.time() - float(cache.get("ts") or 0)) <= max_age_s:
        return cache.get("data")
    return None


def collect_scheduling_health() -> dict[str, Any]:
    """Beat + Celery worker presence for pool/scheduled post cron (Windows process match)."""
    counts = _scheduling_process_counts()
    post_workers = counts["celery_post"]
    scheduler_workers = counts["celery_post_scheduler"]
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
    result = {
        "beat_processes": counts["beat"],
        "celery_worker_processes": counts["celery_worker"],
        "celery_post_scheduler_worker_processes": scheduler_workers,
        "celery_post_worker_processes": post_workers,
        "beat_running": counts["beat"] > 0,
        "celery_worker_running": counts["celery_worker"] > 0,
        "celery_post_scheduler_worker_running": scheduler_workers > 0,
        "celery_post_worker_running": post_workers > 0,
        "pool_auto_post_enabled": pool_auto,
        "scheduling_paused_by_focus": pause,
        "focus_profile": focus_profile,
    }
    # Atomically publish for the fast health endpoint (new dict, single-assignment).
    global _SCHEDULING_HEALTH_CACHE
    _SCHEDULING_HEALTH_CACHE = {"data": result, "ts": time.time()}
    return result


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

        from app.services.focus_profile import count_processing_import_jobs

        processing_imports = count_processing_import_jobs()
        queued_imports = count_active_import_jobs(include_queued=True) - processing_imports
        focus_prof = (get_focus_state().get("profile") or "off").strip().lower()
        if (
            processing_imports >= focus_import_jobs_threshold()
            and focus_prof == "off"
            and lock_events_recent_count() < 2
        ):
            msg = (
                f"{processing_imports} import jobs running"
                + (f" ({queued_imports} queued)" if queued_imports else "")
                + " — import_burst "
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

    # Reuse the watchdog's fresh background scan (refreshed every ~25s tick, and again
    # immediately before auto_remediate) instead of running powershell/netstat on every
    # HTTP request. Only a very fresh cache is trusted so post-fix reports stay accurate.
    sched = cached_scheduling_health(max_age_s=20.0) or collect_scheduling_health()
    _maybe_auto_trim_scheduling_duplicates(sched)
    try:
        from app.services.celery_queue_ops import celery_queue_snapshot

        qsnap = celery_queue_snapshot()
        sched["queues"] = qsnap.get("queues") if qsnap.get("ok") else {}
        post_len = int((qsnap.get("queues") or {}).get("post", {}).get("length") or 0)
        celery_len = int((qsnap.get("queues") or {}).get("celery", {}).get("length") or 0)
        from app.services.post_scheduler import post_queue_backlog_threshold

        backlog_threshold = post_queue_backlog_threshold()
        if redis_ok and (post_len >= backlog_threshold or celery_len >= 200):
            if post_len >= backlog_threshold:
                backlog_msg = (
                    f"Post queue backed up ({post_len} tasks, threshold {backlog_threshold}) — "
                    "scheduled posts are stalled behind pool auto-post jobs."
                )
            else:
                backlog_msg = (
                    f"Celery home queue deep ({celery_len} tasks, threshold 200) — "
                    "Beat ticks may be delayed; post queue currently empty."
                )
            conflicts.append(
                _conflict(
                    "celery_queue_backlog",
                    "critical",
                    backlog_msg + " Resume scheduled posting to purge stale tasks and re-enqueue.",
                    action="resume_scheduled_posting",
                    action_label="Resume scheduled posting",
                )
            )
    except Exception:
        pass

    try:
        from app.services.post_scheduler import schedulers_stall_summary

        stall = schedulers_stall_summary()
        if redis_ok and int(stall.get("count") or 0) > 0:
            names = ", ".join(
                str(x.get("name") or f"id={x.get('id')}") for x in (stall.get("posts") or [])[:3]
            )
            extra = f" (+{stall['count'] - 3} more)" if stall["count"] > 3 else ""
            conflicts.append(
                _conflict(
                    "schedulers_overdue",
                    "critical",
                    (
                        f"{stall['count']} scheduler(s) overdue ≥{stall.get('threshold_minutes')}m "
                        f"(max {stall.get('max_overdue_minutes')}m late): {names}{extra}."
                    ),
                    action="resume_scheduled_posting",
                    action_label="Resume scheduled posting",
                )
            )
            sched["schedulers_stalled"] = stall
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
    if redis_ok and not sched.get("celery_post_scheduler_worker_running"):
        conflicts.append(
            _conflict(
                "celery_post_scheduler_worker_down",
                "critical",
                "TBCC-Celery-Post-Scheduler is not running — channel schedulers will not send. Start TBCC-Celery-Post-Scheduler (full stack).",
            )
        )
    if redis_ok and not sched.get("celery_post_worker_running"):
        conflicts.append(
            _conflict(
                "celery_post_worker_down",
                "critical",
                "TBCC-Celery-Post is not running — pool auto-post and relay posts will not send. Start TBCC-Celery-Post (full stack).",
            )
        )
    post_n = int(sched.get("celery_post_worker_processes") or 0)
    if redis_ok and post_n > 1:
        conflicts.append(
            _conflict(
                "celery_post_worker_duplicate",
                "critical",
                (
                    f"{post_n} TBCC-Celery-Post workers detected (expected 1) — "
                    "admin_poster.session SQLite lock storms and auto-pauses."
                ),
            )
        )
    beat_n = int(sched.get("beat_processes") or 0)
    if redis_ok and beat_n > 1:
        conflicts.append(
            _conflict(
                "beat_duplicate",
                "warning",
                (
                    f"{beat_n} TBCC-Beat processes detected (expected 1) — "
                    "duplicate scheduler ticks can pile enqueue locks."
                ),
            )
        )
    celery_n = int(sched.get("celery_worker_processes") or 0)
    if redis_ok and celery_n > 1:
        conflicts.append(
            _conflict(
                "celery_worker_duplicate",
                "warning",
                (
                    f"{celery_n} TBCC-Celery workers detected (expected 1) — "
                    "duplicate task consumers can amplify queue contention."
                ),
            )
        )
    if sched.get("scheduling_paused_by_focus"):
        fp = str(sched.get("focus_profile") or "off")
        try:
            from app.services.focus_profile import (
                count_active_import_jobs,
                count_processing_import_jobs,
                focus_import_idle_restore_minutes,
            )

            queued = count_active_import_jobs(include_queued=True) - count_processing_import_jobs()
            processing = count_processing_import_jobs()
        except Exception:
            queued = 0
            processing = 0

            def focus_import_idle_restore_minutes() -> int:
                return 20

        if fp == "import_burst" and processing > 0:
            msg = (
                f"Focus «import_burst» paused scheduling while {processing} import job(s) are processing. "
                f"Auto-resumes when processing finishes and queue is idle "
                f"(≥{focus_import_idle_restore_minutes()}m)."
            )
        elif fp == "import_burst" and queued > 0:
            msg = (
                f"Focus «import_burst» paused scheduling — {queued} import(s) queued but not running. "
                "Auto-remediate will restore focus shortly, or use End focus to resume posting now."
            )
        else:
            msg = (
                f"Focus profile «{fp}» paused Beat scheduling (TBCC-Beat may still run). "
                "Auto-remediate will restore focus when safe, or use End focus."
            )
        conflicts.append(
            _conflict(
                "scheduling_paused_focus",
                "warning",
                msg,
                action="restore_focus",
                action_label="End focus (resume scheduling)",
            )
        )

    try:
        from app.services.focus_profile import lock_events_recent_count, focus_auto_react_enabled, session_lock_storm_active

        if session_lock_storm_active():
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

    try:
        from app.services.companion_access import gate_enabled
        from app.services.companion_gate_health import probe_companion_bot_channel_admin_sync

        if gate_enabled():
            gate_probe = probe_companion_bot_channel_admin_sync()
            if gate_probe.get("ok") and not gate_probe.get("bot_admin_all_channels"):
                missing = gate_probe.get("missing_channels") or []
                names = ", ".join(
                    str(m.get("display_name") or m.get("ident") or "?") for m in missing[:4]
                )
                extra = f" +{len(missing) - 4} more" if len(missing) > 4 else ""
                conflicts.append(
                    _conflict(
                        "companion_gate_channels",
                        "warning",
                        (
                            f"@aof_spicybot_bot is not admin in {len(missing)}/{gate_probe.get('channel_count', '?')} "
                            f"AOF channels ({names}{extra}) — companion membership verify fails outside Main Group. "
                            "Run scripts/ensure_companion_bot_channel_admin.py --execute or add the bot manually."
                        ),
                        action="companion_gate_channels",
                        action_label="Fix companion gate channels",
                    )
                )
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


def health_auto_remediate_enabled() -> bool:
    """Background loop applies banner fixes without dashboard clicks (default on)."""
    return (os.getenv("TBCC_HEALTH_AUTO_REMEDIATE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


_AUTO_REMEDIATE_COOLDOWN_S: dict[str, int] = {
    "restore_focus": 90,
    # Post-queue lane recovery is owned by scheduler_watchdog_tick and must react fast
    # enough to clear overdue schedulers within the 5-minute unattended SLO.
    "resume_scheduled_posting": 30,
    "watchdog_pool_purge": 30,
    "start_scheduling_stack": 300,
}


def _auto_remediate_cooldown_file() -> Path:
    return _tbcc_root() / ".tbcc-run" / "health-auto-remediate-cooldown.json"


def _auto_remediate_cooldown_ok(code: str) -> bool:
    min_s = _AUTO_REMEDIATE_COOLDOWN_S.get(code, 180)
    path = _auto_remediate_cooldown_file()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw = data.get(code)
                if raw:
                    last = datetime.fromisoformat(str(raw))
                    if (datetime.now() - last).total_seconds() < min_s:
                        return False
    except Exception:
        pass
    return True


def _mark_auto_remediate_cooldown(codes: list[str]) -> None:
    path = _auto_remediate_cooldown_file()
    try:
        data: dict[str, str] = {}
        if path.is_file():
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                data = {str(k): str(v) for k, v in parsed.items()}
        now = datetime.now().isoformat()
        for code in codes:
            data[code] = now
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.debug("auto remediate cooldown write failed: %s", e)


def auto_remediate_health_conflicts() -> dict[str, Any]:
    """
    Apply safe banner remediations automatically (focus watch loop, ~25s).
    Does not re-apply telegram_relief when already active — evaluate_and_maybe_auto_apply owns that.
    """
    if not health_auto_remediate_enabled():
        return {"ok": True, "skipped": "disabled"}

    from app.services.focus_profile import (
        get_focus_state,
        pause_beat_scheduling,
        sync_focus_flags_from_profile,
    )

    sync_focus_flags_from_profile()

    health = collect_system_health()
    codes = {str(c.get("code") or "") for c in health.get("conflicts", [])}
    codes.discard("")

    to_fix: list[str] = []
    focus_profile = (get_focus_state().get("profile") or "off").strip().lower()

    if "scheduling_paused_focus" in codes and pause_beat_scheduling():
        # import_burst restore (with an idle dwell timer) is owned by scheduler_watchdog_tick;
        # only auto-restore other focus profiles here.
        if focus_profile == "import_burst":
            pass
        elif _auto_remediate_cooldown_ok("restore_focus"):
            to_fix.append("restore_focus")

    worker_down = {
        "beat_down",
        "celery_worker_down",
        "celery_post_worker_down",
        "celery_post_scheduler_worker_down",
    } & codes
    if worker_down and _auto_remediate_cooldown_ok("start_scheduling_stack"):
        to_fix.append("beat_down")
        to_fix.append("celery_post_worker_down")
        to_fix.append("celery_post_scheduler_worker_down")

    # Post-queue lane (schedulers_overdue / celery_queue_backlog / resume_scheduled_posting)
    # is owned by scheduler_watchdog_tick, which runs earlier in the same watch loop with
    # its own 30s cooldown. Do not resume here — it would double-fire and purge the queue
    # the watchdog just re-populated.

    # session_lock_storm → focus evaluate loop; never remediate focus_telegram_relief here.

    if not to_fix:
        return {"ok": health.get("ok", True), "auto_fixed": [], "conflicts": sorted(codes)}

    deduped = list(dict.fromkeys(to_fix))
    logger.info("Health auto-remediate: %s", deduped)
    result = remediate_system_issues(deduped)
    _mark_auto_remediate_cooldown(deduped)
    result["auto_fixed"] = deduped
    return result


# ---------------------------------------------------------------------------
# Scheduler watchdog (closed loop) — single owner of the post-queue lane.
#
# Runs every ~25s from the focus watch loop, BEFORE auto_remediate_health_conflicts.
# State below is written only from that single background thread; the fast health
# endpoint reads it (last-action + cached scan) from a request thread. Each shared
# value is replaced by whole-object assignment so cross-thread reads never tear.
# ---------------------------------------------------------------------------

_WATCHDOG_OVERDUE_STREAK = 0
_WATCHDOG_IMPORT_IDLE_SINCE: datetime | None = None
_WATCHDOG_LAST_ACTION: dict[str, Any] | None = None


def _watchdog_import_idle_dwell_minutes() -> int:
    """Restore import_burst focus once no import job has been processing this long."""
    raw = (os.getenv("TBCC_WATCHDOG_IMPORT_IDLE_MINUTES") or "3").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 3


def reset_scheduler_watchdog_state() -> None:
    """Reset in-memory watchdog state (test hook / manual reset). Cooldowns are file-based."""
    global _WATCHDOG_OVERDUE_STREAK, _WATCHDOG_IMPORT_IDLE_SINCE, _WATCHDOG_LAST_ACTION
    _WATCHDOG_OVERDUE_STREAK = 0
    _WATCHDOG_IMPORT_IDLE_SINCE = None
    _WATCHDOG_LAST_ACTION = None


def _record_watchdog_action(
    action: str, reason: str, actions: list[dict[str, Any]], result: dict[str, Any] | None
) -> None:
    global _WATCHDOG_LAST_ACTION
    entry = {"action": action, "reason": reason, "at": datetime.utcnow().isoformat() + "Z"}
    _WATCHDOG_LAST_ACTION = entry  # atomic single-assignment for the fast endpoint
    actions.append({**entry, "result_ok": bool((result or {}).get("ok", True))})
    logger.info("scheduler_watchdog action=%s reason=%s", action, reason)


def scheduler_watchdog_tick() -> dict[str, Any]:
    """
    Closed-loop scheduler recovery. Owns the post-queue lane and import_burst restore.
    Refreshes the cached scheduling scan every tick so /health/scheduling/fast stays cheap.
    """
    global _WATCHDOG_OVERDUE_STREAK, _WATCHDOG_IMPORT_IDLE_SINCE

    from app.services.post_scheduler import (
        _post_queue_length,
        clear_post_scheduling_redis_state,
        post_queue_backlog_threshold,
        resume_scheduled_posting,
        schedulers_stall_summary,
    )

    # Expensive process scan — background-only; publishes the fast-endpoint cache.
    try:
        sched = collect_scheduling_health()
    except Exception:
        sched = cached_scheduling_health(max_age_s=120.0) or {}

    try:
        stall = schedulers_stall_summary()
        overdue = int(stall.get("count") or 0)
    except Exception:
        overdue = 0

    try:
        post_len = _post_queue_length()
    except Exception:
        post_len = 0

    try:
        from app.services.focus_profile import get_focus_state, pause_beat_scheduling

        focus_profile = (get_focus_state().get("profile") or "off").strip().lower()
        beat_paused = pause_beat_scheduling()
    except Exception:
        focus_profile = "off"
        beat_paused = False

    if overdue > 0:
        _WATCHDOG_OVERDUE_STREAK += 1
    else:
        _WATCHDOG_OVERDUE_STREAK = 0

    actions: list[dict[str, Any]] = []
    enabled = health_auto_remediate_enabled()

    try:
        backlog_threshold = post_queue_backlog_threshold()
    except Exception:
        backlog_threshold = 5

    if enabled:
        # Overdue schedulers OR scheduler-lane backlog: purge, clear locks, re-enqueue.
        resume_needed = overdue > 0 or post_len >= backlog_threshold
        if resume_needed and _auto_remediate_cooldown_ok("resume_scheduled_posting"):
            try:
                r = resume_scheduled_posting(purge_post_queue=True)
            except Exception as e:
                r = {"ok": False, "error": str(e)[:200]}
            _mark_auto_remediate_cooldown(["resume_scheduled_posting"])
            _record_watchdog_action(
                "resume_scheduled_posting",
                f"overdue={overdue} scheduler_queue={post_len} backlog_threshold={backlog_threshold}",
                actions,
                r,
            )

        # import_burst paused Beat but no import job has been *processing* for the dwell
        #     window — restore focus so schedulers resume. Queued-only imports never qualify.
        if focus_profile == "import_burst" and beat_paused:
            try:
                from app.services.focus_profile import (
                    count_processing_import_jobs,
                    restore_focus_profile,
                )

                processing = count_processing_import_jobs()
            except Exception:
                processing = 1  # fail safe: assume busy, do not restore

            if processing > 0:
                _WATCHDOG_IMPORT_IDLE_SINCE = None
            else:
                if _WATCHDOG_IMPORT_IDLE_SINCE is None:
                    _WATCHDOG_IMPORT_IDLE_SINCE = datetime.utcnow()
                idle_min = (
                    datetime.utcnow() - _WATCHDOG_IMPORT_IDLE_SINCE
                ).total_seconds() / 60
                if idle_min >= _watchdog_import_idle_dwell_minutes() and _auto_remediate_cooldown_ok(
                    "restore_focus"
                ):
                    try:
                        r = restore_focus_profile(
                            reason="scheduler_watchdog: import_burst idle, processing=0"
                        )
                    except Exception as e:
                        r = {"ok": False, "error": str(e)[:200]}
                    _mark_auto_remediate_cooldown(["restore_focus"])
                    _WATCHDOG_IMPORT_IDLE_SINCE = None
                    _record_watchdog_action(
                        "restore_focus",
                        f"import_burst idle {round(idle_min, 1)}m processing=0",
                        actions,
                        r,
                    )
        else:
            _WATCHDOG_IMPORT_IDLE_SINCE = None

    return {
        "ok": True,
        "enabled": enabled,
        "overdue_count": overdue,
        "overdue_streak": _WATCHDOG_OVERDUE_STREAK,
        "post_queue_depth": post_len,
        "focus": focus_profile,
        "actions": actions,
    }


def scheduling_fast_snapshot() -> dict[str, Any]:
    """
    Cheap scheduling status for GET /health/scheduling/fast (<500ms, no process scans).
    beat/celery-post come from the background-maintained cache; queue depth, overdue count,
    and focus are cheap direct probes (redis llen, a small DB query, a focus-state file read).
    """
    sched = cached_scheduling_health()  # None if the watchdog loop is not maintaining it

    post_len: int | None = None
    overdue: int | None = None
    focus: str | None = None
    try:
        from app.services.post_scheduler import _post_queue_length, schedulers_stall_summary

        post_len = _post_queue_length()
        overdue = int(schedulers_stall_summary().get("count") or 0)
    except Exception:
        pass
    try:
        from app.services.focus_profile import get_focus_state

        focus = (get_focus_state().get("profile") or "off").strip().lower()
    except Exception:
        pass

    cache = _SCHEDULING_HEALTH_CACHE
    snapshot_age = (
        round(time.time() - float(cache.get("ts") or 0), 1) if cache else None
    )
    return {
        "focus": focus,
        "beat_up": bool(sched.get("beat_running")) if sched else None,
        "celery_post_up": bool(sched.get("celery_post_scheduler_worker_running")) if sched else None,
        "celery_pool_post_up": bool(sched.get("celery_post_worker_running")) if sched else None,
        "post_queue_depth": post_len,
        "overdue_count": overdue,
        "last_watchdog_action": _WATCHDOG_LAST_ACTION,
        "scheduling_snapshot_age_s": snapshot_age,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
