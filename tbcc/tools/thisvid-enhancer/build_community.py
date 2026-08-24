#!/usr/bin/env python3
"""Wrap extension thisvid-enhancer.js as a Sleazy Fork community userscript."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent.parent / "extension" / "thisvid-enhancer.js"
OUT = ROOT / "thisvid-enhancer-community.user.js"
VERSION = "1.0.0"

HEADER = f"""// ==UserScript==
// @name         ThisVid Enhancer
// @namespace    https://sleazyfork.org/users/1618643-ianmxaof
// @homepageURL  https://telegram.me/aofsubscriptions_bot
// @version      {VERSION}
// @license      MIT
// @author       AOF community fork
// @description  ThisVid browsing: title filters, privacy/duration/views sort, infinite scroll, download buttons, mass-friend helpers. Community build — no analytics, no upload library.
// Privacy: settings stay in localStorage; fetches go to thisvid.com.
// @match        https://thisvid.com/*
// @match        https://www.thisvid.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==
"""

STUBS = r"""
(function (global) {
  'use strict';
  function tbccWaitForModule(_id, fn) { fn(); }
  function tbccBindModuleDisableListener() {}
  global.tbccWaitForModule = tbccWaitForModule;
  global.tbccBindModuleDisableListener = tbccBindModuleDisableListener;
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
"""


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source: {SRC}")
    body = SRC.read_text(encoding="utf-8")
    if "const COMMUNITY = typeof GM_info !== 'undefined'" not in body:
        raise SystemExit("thisvid-enhancer.js missing COMMUNITY gate")
    for needle, repl in (
        ("http://127.0.0.1:8000/analytics/erome-browse-intel", ""),
        ("https://media.powercore.app", ""),
        ("media.powercore.app", ""),
    ):
        body = body.replace(needle, repl)
    OUT.write_text(HEADER + "\n" + STUBS + "\n" + body, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes) version {VERSION}")


if __name__ == "__main__":
    main()
