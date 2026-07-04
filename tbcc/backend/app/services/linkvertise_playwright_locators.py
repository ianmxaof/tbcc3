"""Resolve Playwright locators from flow config (codegen-friendly JSON)."""

from __future__ import annotations

import re
from typing import Any


def locator_from_spec(page: Any, spec: dict[str, Any] | str | None) -> Any:
    """Build a Playwright locator from a string CSS selector or structured spec."""
    if spec is None:
        raise ValueError("missing_locator_spec")
    if isinstance(spec, str):
        s = spec.strip()
        if not s:
            raise ValueError("empty_locator_string")
        return page.locator(s)

    method = str(spec.get("method") or "locator").strip()
    args = spec.get("args") or []
    kwargs = dict(spec.get("kwargs") or {})
    filter_has_text = spec.get("filter_has_text")
    child_role = spec.get("child_role")
    name_pattern = spec.get("name_pattern")

    loc: Any
    if method == "locator":
        if not args:
            raise ValueError("locator requires args[0] selector string")
        loc = page.locator(str(args[0]), **kwargs)
    elif method == "get_by_role":
        if not args:
            raise ValueError("get_by_role requires role in args[0]")
        role = str(args[0])
        opts = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        opts.update(kwargs)
        if name_pattern:
            opts["name"] = re.compile(str(name_pattern), re.I)
        loc = page.get_by_role(role, **opts)
    elif method == "get_by_label":
        if not args:
            raise ValueError("get_by_label requires label in args[0]")
        label = str(args[0])
        opts = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        opts.update(kwargs)
        loc = page.get_by_label(label, **opts)
    elif method == "get_by_text":
        if not args:
            raise ValueError("get_by_text requires text in args[0]")
        text = str(args[0])
        opts = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        opts.update(kwargs)
        loc = page.get_by_text(text, **opts)
    elif method == "get_by_placeholder":
        if not args:
            raise ValueError("get_by_placeholder requires text in args[0]")
        text = str(args[0])
        opts = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        opts.update(kwargs)
        loc = page.get_by_placeholder(text, **opts)
    else:
        raise ValueError(f"unsupported_locator_method:{method}")

    if child_role:
        loc = loc.get_by_role(str(child_role))
    child_text = spec.get("child_text")
    if child_text:
        loc = loc.get_by_text(str(child_text))
    if filter_has_text:
        loc = loc.filter(has_text=str(filter_has_text))
    return loc


def click_spec(page: Any, spec: dict[str, Any] | str | None, *, timeout_ms: int = 60000) -> None:
    locator_from_spec(page, spec).first.click(timeout=timeout_ms)


def fill_spec(page: Any, spec: dict[str, Any] | str | None, value: str) -> None:
    locator_from_spec(page, spec).fill(value)
