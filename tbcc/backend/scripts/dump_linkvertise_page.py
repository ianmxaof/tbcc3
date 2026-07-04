#!/usr/bin/env python3
"""Dump interactive elements from Linkvertise Post & earn (auth required)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.linkvertise_dashboard_provision import auth_state_path, load_flow_config
from app.services.playwright_browser import browser_label, launch_kwargs


def main() -> int:
    cfg = load_flow_config()
    auth = auth_state_path()
    if not auth.is_file():
        print(f"Missing {auth}", file=sys.stderr)
        return 1

    from playwright.sync_api import sync_playwright

    out_path = Path(__file__).resolve().parents[1] / "lv_page_snapshot.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs(headless=False))
        context = browser.new_context(storage_state=str(auth))
        page = context.new_page()
        page.goto(cfg.post_earn_url, wait_until="networkidle", timeout=60000)

        snapshot = page.evaluate(
            """() => {
            const items = [];
            const push = (el, kind) => {
              const r = el.getBoundingClientRect();
              if (r.width < 2 || r.height < 2) return;
              items.push({
                kind,
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute('type') || '',
                role: el.getAttribute('role') || '',
                name: (el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || '').trim().slice(0,120),
                href: el.getAttribute('href') || '',
                id: el.id || '',
                classes: (el.className || '').toString().slice(0,120),
              });
            };
            document.querySelectorAll('button, a, input, textarea, [role=button]').forEach(el => push(el, 'interactive'));
            return items;
        }"""
        )
        browser.close()

    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Browser: {browser_label()}")
    print(f"Wrote {len(snapshot)} elements -> {out_path}")
    for row in snapshot[:40]:
        print(f"  {row.get('kind')} {row.get('tag')} name={row.get('name')!r} type={row.get('type')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
