#!/usr/bin/env python3
"""Probe Linkvertise Creator Dashboard posts table for retarget selectors."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.linkvertise_dashboard_provision import (
    _navigate_to_posts_list,
    auth_state_path,
    load_flow_config,
)
from app.services.playwright_browser import open_playwright_session

SLUG = "dl1P4gLUfX0L"


def main() -> int:
    cfg = load_flow_config()
    auth = auth_state_path()
    out: dict = {"slug": SLUG, "url": "", "buttons": [], "links": [], "inputs": []}
    handle = open_playwright_session(headed=False, slow_mo=0, storage_state=auth)
    try:
        page = handle.get_page()
        _navigate_to_posts_list(page, cfg)
        out["url"] = page.url
        # search
        for getter_name, getter in [
            ("placeholder", lambda: page.get_by_placeholder(re.compile("Search", re.I)).first),
            ("textbox_search", lambda: page.get_by_role("textbox", name=re.compile("Search", re.I)).first),
        ]:
            try:
                loc = getter()
                if loc.count():
                    loc.fill(SLUG)
                    page.wait_for_timeout(2000)
                    out["search_via"] = getter_name
                    break
            except Exception as e:
                out.setdefault("search_errors", []).append(f"{getter_name}: {e}")

        out["url_after_search"] = page.url
        rows = page.evaluate(
            """() => {
            const out = { buttons: [], links: [], inputs: [] };
            for (const el of document.querySelectorAll('button,a,[role=button],input,textarea')) {
              const t = (el.innerText || el.placeholder || el.getAttribute('aria-label') || '').trim();
              if (!t && el.tagName !== 'INPUT') continue;
              const tag = el.tagName.toLowerCase();
              const role = el.getAttribute('role') || '';
              const href = el.getAttribute('href') || '';
              const row = { tag, text: t.slice(0, 120), role, href: href.slice(0, 120) };
              if (tag === 'button' || role === 'button') out.buttons.push(row);
              else if (tag === 'a') out.links.push(row);
              else if (tag === 'input' || tag === 'textarea') out.inputs.push(row);
            }
            return out;
        }"""
        )
        out.update(rows)
        # count edit-ish
        out["edit_candidates"] = [
            b for b in out.get("buttons", []) if re.search(r"edit", b.get("text", ""), re.I)
        ]
        path = Path(__file__).resolve().parents[1] / "lv_posts_probe.json"
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(path.read_text(encoding="utf-8"))
    finally:
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
