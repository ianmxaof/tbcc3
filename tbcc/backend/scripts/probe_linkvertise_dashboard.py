#!/usr/bin/env python3
"""Probe Linkvertise Dashboard -> create link UI for locators."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.linkvertise_dashboard_provision import auth_state_path
from app.services.playwright_browser import launch_kwargs


def _confirm_cookies(page) -> None:
    for name in ("CONFIRM", "Accept", "Accept all"):
        try:
            page.get_by_role("button", name=name).click(timeout=2000)
            page.wait_for_timeout(500)
            return
        except Exception:
            continue


def _dump(page, label: str) -> list[dict]:
    rows = page.evaluate(
        """() => {
        const out = [];
        for (const el of document.querySelectorAll('button,a,input,textarea,[role=button]')) {
          const t = (el.innerText || el.placeholder || el.getAttribute('aria-label') || '').trim();
          if (!t) continue;
          out.push({ tag: el.tagName.toLowerCase(), text: t.slice(0,100) });
        }
        return out;
    }"""
    )
    print(f"\n=== {label} url={page.url} ===")
    for r in rows[:50]:
        print(f"  {r['tag']}: {r['text'][:80]}")
    return rows


def main() -> int:
    auth = str(auth_state_path())
    out: dict = {}
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs(headless=False))
        ctx = browser.new_context(storage_state=auth)
        page = ctx.new_page()
        page.goto("https://linkvertise.com/", wait_until="networkidle", timeout=90000)
        _confirm_cookies(page)
        out["home"] = _dump(page, "home")

        for nav in ("Dashboard", "Post & earn"):
            try:
                page.get_by_role("link", name=nav, exact=True).click(timeout=8000)
                page.wait_for_timeout(2500)
                out[nav] = _dump(page, nav)
            except Exception as e:
                print(f"nav {nav} failed: {e}")

        for create_label in ("Create new link", "Create link", "Create Link", "New link", "Get Started"):
            try:
                page.get_by_role("button", name=create_label).click(timeout=3000)
                page.wait_for_timeout(2000)
                out[f"after_{create_label}"] = _dump(page, f"after {create_label}")
                break
            except Exception:
                try:
                    page.get_by_role("link", name=create_label).click(timeout=3000)
                    page.wait_for_timeout(2000)
                    out[f"after_{create_label}"] = _dump(page, f"after {create_label}")
                    break
                except Exception:
                    continue

        path = Path(__file__).resolve().parents[1] / "lv_dashboard_probe.json"
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nWrote {path}")
        ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
