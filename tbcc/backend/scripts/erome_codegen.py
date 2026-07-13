#!/usr/bin/env python3
"""Erome upload recorder.

Two modes:

  --codegen   Real Playwright Codegen UI (Record / Stop / copy Python)  ← use this
  (default)   Inspector pause (Resume only — no Record button)

Usage:
  py -3.13 scripts/erome_codegen.py --codegen
  py -3.13 scripts/erome_codegen.py --codegen --skip-login
  py -3.13 scripts/erome_codegen.py --codegen -o erome_recording.py

Close other Brave automation-profile windows first if launch fails.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.erome_upload_provision import (
    auth_state_path,
    load_flow_config,
    navigate_to_email_login,
    _accept_age_gate,
    _looks_logged_in,
)
from app.services.playwright_browser import (
    browser_label,
    default_brave_profile_name,
    open_playwright_session,
    resolve_browser_executable,
)

DEFAULT_RECORDING = Path(__file__).resolve().parents[1] / "erome_recording.py"


def run_codegen(*, url: str, output: Path, load_storage: Path | None) -> int:
    """Launch Playwright's Codegen panel (Record / Stop) with Brave when available."""
    exe = resolve_browser_executable()
    auth = load_storage if load_storage and load_storage.is_file() else None
    cmd = [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--target",
        "python",
        "-o",
        str(output),
        "--browser",
        "chromium",
    ]
    if auth:
        cmd.extend(["--load-storage", str(auth)])
        cmd.extend(["--save-storage", str(auth)])
    cmd.append(url)

    env = os.environ.copy()
    if exe and exe.is_file():
        env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = str(exe)
        print(f"Browser executable: {exe}", flush=True)
    else:
        print("Brave not found — using Playwright Chromium for codegen.", flush=True)

    print(
        "\n=== PLAYWRIGHT CODEGEN (Record / Stop) ===\n"
        "A Codegen window should open with:\n"
        "  • left: browser\n"
        "  • right: generated Python + Record / Stop / copy\n\n"
        "Click path (one video, private staging):\n"
        "  1. Age gate if shown\n"
        "  2. UPLOAD\n"
        "  3. One .mp4 from Downloads\n"
        "  4. Title + Tags if visible\n"
        "  5. Private checkbox\n"
        "  6. SAVE\n"
        "  7. Optional: Edit → Public → SAVE (for promote-to-public)\n"
        "  8. Stop recording, close Codegen when done\n\n"
        f"Output: {output}\n"
        "If the Record panel is missing, look for a second window titled Playwright Inspector / Codegen.\n",
        flush=True,
    )
    print("Running:", " ".join(cmd), flush=True)
    return int(subprocess.call(cmd, env=env))


def run_inspector_pause(*, url: str, use_profile: bool, skip_login: bool, save_storage: Path) -> int:
    """Legacy Inspector pause — Resume only (no Record button). Prefer --codegen."""
    print(
        "\nNOTE: Inspector mode has Resume, not Record/Stop.\n"
        "For the Record panel run:\n"
        "  py -3.13 scripts/erome_codegen.py --codegen\n",
        flush=True,
    )
    print(f"Browser: {browser_label()}  profile={default_brave_profile_name()}")
    handle = open_playwright_session(
        headed=True,
        slow_mo=80,
        storage_state=save_storage,
        force_ephemeral=not use_profile,
    )
    try:
        # Force Inspector UI even if auto-detect fails on some Windows setups
        os.environ.setdefault("PWDEBUG", "1")
        page = handle.get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page = _accept_age_gate(page, cfg := load_flow_config())
        if skip_login or _looks_logged_in(page, cfg):
            print("Session looks logged in — starting on home page.", flush=True)
        else:
            navigate_to_email_login(page, cfg)
            print(
                "Not logged in yet — use EMAIL + password (NOT Google), then click Resume.",
                flush=True,
            )
        print(
            "\n=== PLAYWRIGHT INSPECTOR (Resume) ===\n"
            "Look for a separate Inspector window (may be behind Brave).\n"
            "There is NO Record button here — walk the upload manually, then Resume.\n"
            "Prefer --codegen if you want auto-generated Python.\n",
            flush=True,
        )
        page.pause()
        if save_storage:
            save_storage.parent.mkdir(parents=True, exist_ok=True)
            handle.context.storage_state(path=str(save_storage))
            print(f"Saved session -> {save_storage}")
    finally:
        handle.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Record Erome upload flow (Codegen or Inspector)")
    p.add_argument(
        "--codegen",
        action="store_true",
        help="Open Playwright Codegen (Record/Stop panel) — recommended",
    )
    p.add_argument("--save-storage", type=Path, default=None, help="Export cookies on exit")
    p.add_argument(
        "--use-profile",
        action="store_true",
        help="Inspector only: use Brave automation profile",
    )
    p.add_argument(
        "--skip-login",
        action="store_true",
        help="Inspector only: start on home when cookies already work",
    )
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_RECORDING, help="Codegen output .py")
    p.add_argument("url", nargs="?", default=None, help="Start URL")
    args = p.parse_args()

    cfg = load_flow_config()
    url = (args.url or cfg.upload_url).strip()
    auth = args.save_storage or auth_state_path()

    if args.codegen or os.getenv("TBCC_EROME_CODEGEN", "").strip() in ("1", "true", "yes"):
        return run_codegen(url=url, output=args.output, load_storage=auth)

    return run_inspector_pause(
        url=url,
        use_profile=args.use_profile,
        skip_login=args.skip_login,
        save_storage=auth,
    )


if __name__ == "__main__":
    raise SystemExit(main())
