#!/usr/bin/env python3
"""Everyday Playwright Codegen recorder for TBCC.

Opens Playwright's Record/Stop panel for ANY site. Saves a Python workflow
file you can re-run or turn into flow locators later.

  cd tbcc/backend
  py -3.13 scripts/playwright_record.py
  py -3.13 scripts/playwright_record.py https://www.erome.com/
  py -3.13 scripts/playwright_record.py https://x.com/ --name x-promo
  py -3.13 scripts/playwright_record.py --load-auth .erome-auth.json https://www.erome.com/

Notes:
  • Records in a Playwright-controlled Brave/Chromium window — not your
    already-open daily browser tab.
  • Never type passwords into recordings you will paste/share; prefer
    --load-auth with a saved storage_state from a prior --login.
  • Output defaults under playwright-recordings/ (gitignored).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.playwright_browser import resolve_browser_executable

BACKEND = Path(__file__).resolve().parents[1]
RECORDINGS = BACKEND / "playwright-recordings"


def _slug(raw: str) -> str:
    s = re.sub(r"[^\w.-]+", "-", (raw or "").strip().lower()).strip("-")
    return (s[:48] or "session")


def main() -> int:
    p = argparse.ArgumentParser(description="Record any click/keyboard workflow with Playwright Codegen")
    p.add_argument("url", nargs="?", default="about:blank", help="Start URL (default about:blank)")
    p.add_argument("--name", "-n", type=str, default=None, help="Recording basename (default timestamp)")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .py path (default playwright-recordings/<name>.py)",
    )
    p.add_argument(
        "--load-auth",
        type=Path,
        default=None,
        help="Load storage_state JSON (cookies) so you skip login",
    )
    p.add_argument(
        "--save-auth",
        type=Path,
        default=None,
        help="Save storage_state when Codegen exits (defaults to --load-auth if set)",
    )
    p.add_argument(
        "--chromium",
        action="store_true",
        help="Force bundled Chromium instead of Brave",
    )
    p.add_argument(
        "--target",
        default="python",
        choices=("python", "python-async", "javascript", "playwright-test"),
        help="Codegen language (default python)",
    )
    args = p.parse_args()

    RECORDINGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    name = _slug(args.name or stamp)
    out = args.output or (RECORDINGS / f"{name}.py")
    if out.suffix.lower() != ".py":
        out = out.with_suffix(".py")
    out.parent.mkdir(parents=True, exist_ok=True)

    load_auth = args.load_auth
    save_auth = args.save_auth or load_auth

    cmd = [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--target",
        args.target,
        "-o",
        str(out.resolve()),
        "--browser",
        "chromium",
    ]
    if load_auth and load_auth.is_file():
        cmd.extend(["--load-storage", str(load_auth.resolve())])
    if save_auth:
        save_auth.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--save-storage", str(save_auth.resolve())])
    cmd.append(args.url)

    env = os.environ.copy()
    if not args.chromium:
        exe = resolve_browser_executable()
        if exe and exe.is_file():
            env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = str(exe)
            print(f"Browser: Brave ({exe.name})", flush=True)
        else:
            print("Browser: Playwright Chromium (Brave not found)", flush=True)
    else:
        print("Browser: Playwright Chromium (--chromium)", flush=True)

    print(
        f"\n=== TBCC PLAYWRIGHT RECORD ===\n"
        f"URL:     {args.url}\n"
        f"Output:  {out}\n"
        f"Auth in: {load_auth or '(none)'}\n\n"
        "Use the Codegen side panel:\n"
        "  Record → click / type anything → Stop → close when done\n"
        "Re-run later:  py <output.py>\n"
        "Or paste selectors into a flow.local.json for automation.\n",
        flush=True,
    )
    print("Running:", " ".join(cmd), flush=True)
    code = int(subprocess.call(cmd, env=env))
    if out.is_file() and out.stat().st_size > 20:
        print(f"\nSaved workflow -> {out}", flush=True)
        # Soft scrub reminder if password-ish fills appear
        text = out.read_text(encoding="utf-8", errors="replace")
        if ".fill(\"" in text and ("password" in text.lower() or "Password" in text):
            print(
                "WARNING: recording may contain secrets — redact before sharing/committing.",
                flush=True,
            )
    else:
        print(f"\nNo script written (or empty): {out}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
