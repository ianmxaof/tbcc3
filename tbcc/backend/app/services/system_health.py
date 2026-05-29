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
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.8):
            return True
    except OSError:
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

    health = collect_system_health()
    return {"ok": health.get("ok", False), "results": results, "health": health}


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

    fixable = [c for c in conflicts if c.get("action")]
    if fixable:
        recommendations.append("Use Fix buttons in the banner above — no scripts required.")

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
        "orphan_uvicorn_workers": orphans,
        "conflicts": conflicts,
        "recommendations": recommendations,
        "fixable_count": len(fixable),
    }


def auto_remediate_on_startup() -> dict[str, Any]:
    """Called when the API boots: clear reload orphans before serving traffic."""
    out = cleanup_uvicorn_orphans()
    if out.get("killed", 0) > 0:
        logger.info("Startup auto-cleanup: killed %s uvicorn orphan worker(s)", out["killed"])
    return out
