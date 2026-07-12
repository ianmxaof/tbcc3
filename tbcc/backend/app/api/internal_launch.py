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
from pydantic import BaseModel, Field

from app.api.external_payment_orders import _require_internal

logger = logging.getLogger(__name__)

router = APIRouter()


class PlaywrightRecordBody(BaseModel):
    url: str = Field(default="https://www.erome.com/", max_length=500)
    name: str | None = Field(default=None, max_length=64)
    load_auth: bool = True
    use_erome_auth: bool = True


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


@router.post("/playwright/record")
def playwright_record(body: PlaywrightRecordBody, _: None = Depends(_require_internal)):
    """Spawn Playwright Codegen (Record/Stop) in a new console for everyday click-path capture."""
    root = _tbcc_root()
    backend = root / "backend"
    script = backend / "scripts" / "playwright_record.py"
    if not script.is_file():
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "playwright_record.py not found", "path": str(script)},
        )

    url = (body.url or "https://www.erome.com/").strip() or "https://www.erome.com/"
    name = (body.name or "").strip() or "erome-session"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:48] or "session"

    py = sys.executable
    args = [py, str(script), url, "--name", safe]
    auth = backend / ".erome-auth.json"
    if body.load_auth and body.use_erome_auth and auth.is_file():
        args.extend(["--load-auth", str(auth), "--save-auth", str(auth)])

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        subprocess.Popen(args, cwd=str(backend), creationflags=creationflags)
    else:
        subprocess.Popen(args, cwd=str(backend), start_new_session=True)

    logger.info("Launched Playwright record via API: url=%s name=%s", url, safe)
    return JSONResponse(
        content={
            "ok": True,
            "via": "api",
            "url": url,
            "name": safe,
            "cwd": str(backend),
            "output_hint": str(backend / "playwright-recordings" / f"{safe}.py"),
            "detail": "Codegen window opening — use Record/Stop in the Playwright panel.",
        }
    )
