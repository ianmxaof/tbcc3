#!/usr/bin/env python3
"""Linkvertise recorder — Playwright Inspector using your real Brave profile (password manager).

Usage:
  py -3.13 scripts/linkvertise_codegen.py
  py -3.13 scripts/linkvertise_codegen.py --output lv_recording.py

Close all Brave windows using the automation profile first. Default: new (Profile 5), not freeusegod (TBCC_BRAVE_PROFILE_NAME).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.linkvertise_dashboard_provision import auth_state_path, load_flow_config
from app.services.playwright_browser import browser_label, default_brave_profile_name, open_playwright_session

DEFAULT_RECORDING = Path(__file__).resolve().parents[1] / "lv_recording.py"


def _dismiss_banners(page) -> None:
    for name in ("CONFIRM", "OK", "Accept", "Accept all"):
        try:
            page.get_by_role("button", name=name).click(timeout=1500)
            page.wait_for_timeout(400)
        except Exception:
            continue


def _prompt_save_recording(out_path: Path) -> None:
    if out_path.is_file() and out_path.stat().st_size > 20:
        print(f"Recording file already exists: {out_path}")
        return
    print(
        "\n=== SAVE RECORDING ===\n"
        "Copy ALL Python from the Playwright Inspector panel.\n"
        "Paste here, then press Ctrl+Z and Enter (Windows) or Ctrl+D (Unix):\n"
    )
    pasted = sys.stdin.read().strip()
    if not pasted or "page." not in pasted:
        print("WARN: no page.* calls pasted — save manually to lv_recording.py")
        return
    out_path.write_text(pasted + "\n", encoding="utf-8")
    print(f"Saved recording -> {out_path}")


def main() -> int:
    p = argparse.ArgumentParser(description="Record Linkvertise flow in your Brave profile")
    p.add_argument("--save-storage", type=Path, default=None, help="Export cookies on exit (optional)")
    p.add_argument("--blank-profile", action="store_true", help="Ignore Brave profile; use .linkvertise-auth.json")
    p.add_argument("--output", type=Path, default=DEFAULT_RECORDING, help="Save pasted Inspector Python here")
    p.add_argument("--skip-paste", action="store_true", help="Do not prompt for Inspector paste after Resume")
    p.add_argument("url", nargs="?", default=None, help="Start URL")
    args = p.parse_args()

    cfg = load_flow_config()
    url = (args.url or cfg.post_earn_url).strip()
    save_path = args.save_storage or auth_state_path()

    print(f"Browser: {browser_label()}")
    print(f"URL:     {url}")
    print(f"Output:  {args.output}")
    if not args.blank_profile:
        print("Tip: close every Brave window before starting (same profile cannot run twice).")
    print(
        "\n1. Record: create link -> 2 ads -> submit -> create new link\n"
        "2. Copy Python from Playwright Inspector\n"
        "3. Click Resume in Inspector (stay in this terminal — do NOT Ctrl+C)\n"
    )

    session = open_playwright_session(
        headed=True,
        slow_mo=80,
        storage_state=save_path if args.blank_profile else None,
        force_ephemeral=args.blank_profile,
    )
    export_auth = args.blank_profile or not session.persistent
    used_profile = session.persistent
    try:
        page = session.get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        _dismiss_banners(page)
        page.pause()
        if export_auth and save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                session.context.storage_state(path=str(save_path))
            except Exception as e:
                print(f"WARN: could not export storage_state ({e}) — OK when using Brave profile.")
    finally:
        session.close()

    if export_auth and save_path and save_path.is_file():
        print(f"\nSaved session export -> {save_path}")
    elif used_profile:
        print(f"\nSession kept in Brave profile ({default_brave_profile_name()}) — no cookie export needed.")
    if not args.skip_paste:
        _prompt_save_recording(args.output)
        if args.output.is_file():
            print(f"Import: py scripts/import_linkvertise_codegen.py {args.output.name} --ad-tasks 2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
