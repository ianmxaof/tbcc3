#!/usr/bin/env python3
"""Erome upload recorder — Playwright Inspector using Brave automation profile.

Usage:
  py -3.13 scripts/erome_codegen.py
  py -3.13 scripts/erome_codegen.py --output erome_recording.py

Close other Brave windows using the automation profile first. Default: new (Profile 5).
"""
from __future__ import annotations

import argparse
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
from app.services.playwright_browser import browser_label, default_brave_profile_name, open_playwright_session

DEFAULT_RECORDING = Path(__file__).resolve().parents[1] / "erome_recording.py"


def main() -> int:
    p = argparse.ArgumentParser(description="Record Erome upload flow in Brave profile")
    p.add_argument("--save-storage", type=Path, default=None, help="Export cookies on exit")
    p.add_argument(
        "--use-profile",
        action="store_true",
        help="Use Brave automation profile (close other Profile 5 windows first)",
    )
    p.add_argument(
        "--skip-login",
        action="store_true",
        help="Start on home/upload page (use when already logged in via saved cookies)",
    )
    p.add_argument("--output", type=Path, default=DEFAULT_RECORDING, help="Hint path for pasted recording")
    p.add_argument("url", nargs="?", default=None, help="Start URL")
    args = p.parse_args()

    cfg = load_flow_config()
    url = (args.url or cfg.upload_url).strip()
    auth = args.save_storage or auth_state_path()

    print(f"Browser: {browser_label()}  profile={default_brave_profile_name()}")
    handle = open_playwright_session(
        headed=True,
        slow_mo=80,
        storage_state=auth,
        force_ephemeral=not args.use_profile,
    )
    try:
        page = handle.get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page = _accept_age_gate(page, cfg)
        if args.skip_login or _looks_logged_in(page, cfg):
            print("Session looks logged in — starting on home page.", flush=True)
        else:
            navigate_to_email_login(page, cfg)
            print(
                "Not logged in yet — use EMAIL + password (NOT Google), then continue recording.",
                flush=True,
            )
        print(
            "\n=== RECORD EROME UPLOAD ===\n"
            "Playwright Inspector opens below — click Record if needed.\n"
            "Flow: Upload -> select files -> title -> Publish -> note album URL.\n"
            f"Paste recording to {args.output} or erome_upload_flow.local.json locators.\n"
            "Press Resume when done.\n",
            flush=True,
        )
        page.pause()
        if auth:
            auth.parent.mkdir(parents=True, exist_ok=True)
            handle.context.storage_state(path=str(auth))
            print(f"Saved session -> {auth}")
    finally:
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
