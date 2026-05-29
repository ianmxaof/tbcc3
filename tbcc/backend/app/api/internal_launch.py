"""
Launch full TBCC stack (start.ps1 -Full) from the browser extension when the API is already running.

Prefer tbcc/tools/tbcc-launch-daemon.ps1 when the API is down (cold start).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.external_payment_orders import _require_internal

logger = logging.getLogger(__name__)

router = APIRouter()


def _tbcc_root() -> Path:
    # backend/app/api/internal_launch.py -> parents: api, app, backend -> tbcc
    return Path(__file__).resolve().parent.parent.parent.parent


@router.post("/launch-full-stack")
def launch_full_stack(_: None = Depends(_require_internal)):
    """Spawn start.ps1 -Full in a new console (Windows)."""
    root = _tbcc_root()
    start_ps1 = root / "start.ps1"
    if not start_ps1.is_file():
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "start.ps1 not found", "path": str(start_ps1)},
        )

    if sys.platform == "win32":
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(start_ps1),
            "-Full",
            "-WtTabs",
            "-NoOpen",
        ]
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        subprocess.Popen(args, cwd=str(root), creationflags=creationflags)
    else:
        # Non-Windows: try PowerShell Core if available
        for exe in ("pwsh", "powershell"):
            try:
                subprocess.Popen(
                    [exe, "-NoProfile", "-File", str(start_ps1), "-Full"],
                    cwd=str(root),
                )
                break
            except FileNotFoundError:
                continue
        else:
            return JSONResponse(
                status_code=501,
                content={
                    "ok": False,
                    "error": "Full launch from API is only wired for Windows PowerShell; use tbcc-launch-daemon.ps1 or run start.ps1 manually.",
                },
            )

    logger.info("Launched full stack via API: cwd=%s script=%s", root, start_ps1)
    return JSONResponse(content={"ok": True, "via": "api", "cwd": str(root)})


def _supervisor_running_win() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import subprocess as sp

        out = sp.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -EA SilentlyContinue | "
                "Where-Object { $_.CommandLine -match 'tbcc-supervisor\\.ps1' }).Count -gt 0",
            ],
            text=True,
            timeout=8,
        )
        return out.strip().lower() == "true"
    except Exception:
        return False


@router.post("/launch-supervisor")
def launch_supervisor(_: None = Depends(_require_internal)):
    """Spawn tbcc-supervisor.ps1 (tray) on Windows."""
    root = _tbcc_root()
    supervisor = root / "tools" / "tbcc-supervisor.ps1"
    if not supervisor.is_file():
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "tbcc-supervisor.ps1 not found", "path": str(supervisor)},
        )

    if _supervisor_running_win():
        return JSONResponse(
            content={
                "ok": True,
                "via": "api",
                "already_running": True,
                "detail": "Tray supervisor already running.",
            }
        )

    if sys.platform == "win32":
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-Sta",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(supervisor),
            ],
            cwd=str(supervisor.parent),
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        )
    else:
        return JSONResponse(
            status_code=501,
            content={
                "ok": False,
                "error": "Tray supervisor is Windows-only; run tbcc-launch-daemon.ps1 locally.",
            },
        )

    logger.info("Launched tray supervisor via API: %s", supervisor)
    return JSONResponse(
        content={"ok": True, "via": "api", "already_running": False, "path": str(supervisor)}
    )
