#!/usr/bin/env python3
"""Convert Playwright codegen output → linkvertise_dashboard_flow.local.json locators."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "linkvertise_dashboard_flow.local.json"
)
DEFAULT_BASE = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "linkvertise_dashboard_flow.json"
)

_PAGE_CALL = re.compile(
    r"page\.((?:get_by_\w+|locator))\((.+)\)\.(click|fill|press)\((.*)\)",
    re.MULTILINE,
)


def _parse_call_args(raw: str) -> tuple[list[Any], dict[str, Any]]:
    raw = raw.strip()
    if not raw:
        return [], {}
    try:
        node = ast.parse(f"f({raw})", mode="eval")
        assert isinstance(node.body, ast.Call)
        args: list[Any] = []
        for a in node.body.args:
            args.append(ast.literal_eval(a))
        kwargs: dict[str, Any] = {}
        for kw in node.body.keywords:
            kwargs[kw.arg or ""] = ast.literal_eval(kw.value)
        return args, kwargs
    except Exception:
        return [raw.strip("\"'")], {}


def _method_from_playwright(name: str) -> str:
    return name if name.startswith("get_by_") else "locator"


def _guess_key(method: str, args: list[Any], action: str) -> str | None:
    text_blob = " ".join(str(a).lower() for a in args)
    if action == "fill":
        return "destination_input"
    if "create new link" in text_blob:
        return "create_new_link_button"
    if "create link" in text_blob or "new link" in text_blob:
        return "create_link_button"
    if action == "click" and ("2 ad" in text_blob or text_blob.strip() == "2"):
        return "ad_tasks_option"
    if "submit" in text_blob or "create" in text_blob or "save" in text_blob:
        if "create new link" not in text_blob:
            return "submit_button"
    if method == "locator" and action == "click":
        return "submit_button"
    return None


def parse_codegen(source: str) -> dict[str, Any]:
    locators: dict[str, Any] = {}
    for m in _PAGE_CALL.finditer(source):
        pw_method, args_raw, action, _extra = m.groups()
        args, kwargs = _parse_call_args(args_raw)
        key = _guess_key(pw_method, args, action)
        if not key or key in locators:
            continue
        spec: dict[str, Any] = {"method": _method_from_playwright(pw_method), "args": args}
        if kwargs:
            spec["kwargs"] = kwargs
        locators[key] = spec
    return locators


def main() -> int:
    p = argparse.ArgumentParser(description="Import Playwright codegen into LV flow config")
    p.add_argument("input", nargs="?", help="Codegen .py file (default: stdin)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--ad-tasks", type=int, default=2, help="Ads to require (default 2)")
    args = p.parse_args()

    if args.input:
        source = Path(args.input).read_text(encoding="utf-8")
    else:
        print("Paste Playwright codegen, then Ctrl+Z Enter (Windows) or Ctrl+D (Unix):", file=sys.stderr)
        source = sys.stdin.read()

    locators = parse_codegen(source)
    if not locators:
        print("No page.* calls parsed. Paste the full codegen panel output.", file=sys.stderr)
        return 1

    base = json.loads(DEFAULT_BASE.read_text(encoding="utf-8"))
    base["locators"] = locators
    base["ad_tasks_count"] = args.ad_tasks
    base["reuse_create_new_link_loop"] = True
    base["notes"] = "Imported from Playwright codegen — review locators before --execute"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print("Parsed locators:", ", ".join(sorted(locators)))
    missing = [k for k in ("create_link_button", "destination_input", "submit_button") if k not in locators]
    if missing:
        print("WARN: still missing keys:", ", ".join(missing), "— add manually to locators{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
