#!/usr/bin/env python3
"""Assemble public Sleazy Fork build from v3.3 base — no browse-intel / TBCC hooks."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "erome-enhancer-v3.3-base.user.js"
OUT = ROOT / "erome-enhancer-community.user.js"

# Keep in sync with SLEAZY_FORK_PUBLISH.md
# @namespace + @name MUST match the live Sleazy Fork listing or TM treats it as a new script.
VERSION = "4.3.0"
HEADER = f"""// ==UserScript==
// @name         Erome Enhancer extended sort options
// @namespace    http://violentmonkey.net/
// @homepageURL  https://telegram.me/aofsubscriptions_bot
// @version      {VERSION}
// @license      MIT
// @author       LisaTurtlesCuck + AOF community fork
// @description  Enhanced Erome browsing: Sort albums by views/videos/duration, filter by content type & duration, infinite scroll with auto-load, like counts display, hide watched albums, duration badges, deleted album display, and more!
// Privacy: @grant none — settings and viewed history stay in localStorage; fetches go to erome.com only.
// @match        https://www.erome.com/*
// @grant        none
// ==/UserScript==
"""


def main() -> None:
    if not BASE.is_file():
        raise SystemExit(f"Missing base file: {BASE}")

    src = BASE.read_text(encoding="utf-8")
    idx = src.find("// ==/UserScript==")
    if idx < 0:
        raise SystemExit("Invalid base userscript")
    body = src[idx + len("// ==/UserScript==") :].lstrip("\n")

    for bad in ("INTEL_KEY", "recordBrowseSnapshot", "tbccApiUrl", "Browse Intel"):
        if bad in body:
            raise SystemExit(f"Base leaked operator intel marker: {bad}")

    OUT.write_text(HEADER + "\n" + body, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes) version {VERSION}")


if __name__ == "__main__":
    main()
