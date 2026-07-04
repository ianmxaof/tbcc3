#!/usr/bin/env python3
"""Quick Erome upload UI diagnostic (no file upload)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.erome_upload_provision import (
    _accept_age_gate,
    _click_if_spec,
    _editor_media_count,
    _looks_logged_in,
    _navigate_to_upload,
    _spec,
    load_flow_config,
    open_upload_session,
)
from app.services.linkvertise_playwright_locators import locator_from_spec


def _page_snapshot(page) -> dict:
    try:
        snap = page.evaluate(
            """() => ({
              url: location.href,
              title: document.title,
              fileInputs: document.querySelectorAll('input[type=file]').length,
              mediasUpload: document.querySelectorAll('#medias .upload').length,
              mediasGroups: document.querySelectorAll('#medias .media-group, .media-group[data-id]').length,
              mediasRoot: !!document.querySelector('#medias'),
              dragText: (document.body.innerText || '').includes('Click to add or drag file'),
              bodySnippet: (document.body.innerText || '').slice(0, 400),
            })"""
        )
        return snap
    except Exception as e:
        return {"error": str(e), "url": getattr(page, "url", "")}


def main() -> int:
    cfg = load_flow_config()
    print(f"flow_mode={cfg.flow_mode} age_gate_popup={cfg.age_gate_use_popup}")
    session = open_upload_session(headed=False, keep_open=False)
    try:
        page = session.page
        print("after open:", json.dumps(_page_snapshot(page), indent=2))
        print("logged_in:", _looks_logged_in(page, cfg))
        page = _navigate_to_upload(page, cfg)
        session.page = page
        print("after navigate:", json.dumps(_page_snapshot(page), indent=2))
        file_spec = _spec(cfg, "file_input")
        if file_spec:
            loc = locator_from_spec(page, file_spec).first
            print("file_input count:", loc.count())
            print("file_input attached:", end=" ")
            try:
                loc.wait_for(state="attached", timeout=5000)
                print("yes")
            except Exception as e:
                print(f"no ({e})")
        test_dir = Path(__file__).resolve().parents[1] / "erome_test_staging"
        valid = test_dir / "valid_test.png"
        if not valid.is_file() or valid.stat().st_size < 100:
            import base64

            valid.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                )
            )
        files = [valid]
        if files:
            paths = [str(p.resolve()) for p in files]
            print(f"trying set_input_files: {paths}")
            drag = _spec(cfg, "drag_drop_zone")
            if drag:
                _click_if_spec(page, cfg, "drag_drop_zone")
                page.wait_for_timeout(500)
            loc = page.locator('input[type="file"]').first
            loc.set_input_files(paths)
            for i in range(8):
                page.wait_for_timeout(2000)
                count = _editor_media_count(page)
                snap = _page_snapshot(page)
                snap["editor_count"] = count
                try:
                    snap["medias_html"] = page.evaluate(
                        """() => {
                          const el = document.querySelector('#medias');
                          return el ? el.innerHTML.slice(0, 1200) : null;
                        }"""
                    )
                except Exception:
                    pass
                print(f"  t+{(i+1)*2}s:", json.dumps(snap, indent=2))
                if count > 0:
                    break
        else:
            print("no test png in erome_test_staging")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
