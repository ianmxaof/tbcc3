"""Ensure at most one TBCC bot process per module (Windows-friendly PID lock)."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _lock_dir() -> Path:
    from app.services.import_pipeline import tbcc_run_dir

    d = tbcc_run_dir() / "bot-locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lock_path(bot_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (bot_name or "bot"))
    return _lock_dir() / f"{safe}.pid"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_bot_singleton(bot_name: str) -> bool:
    """
    Return True if this process acquired the lock.
    Return False if another live instance holds it (caller should exit).
    """
    path = _lock_path(bot_name)
    my_pid = os.getpid()
    if path.is_file():
        try:
            other = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            other = 0
        if other and other != my_pid and _pid_alive(other):
            logger.error(
                "%s already running (pid=%s). Stop duplicates via tray or POST /ops/health/remediate.",
                bot_name,
                other,
            )
            return False
    path.write_text(str(my_pid), encoding="utf-8")

    def _release() -> None:
        try:
            if path.is_file() and path.read_text(encoding="utf-8").strip() == str(my_pid):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(_release)
    return True
