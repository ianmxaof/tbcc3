"""Extension in-page / gallery context menu visibility (JSON on disk, synced to chrome.storage)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SETTINGS_PATH = _TBCC_ROOT / "data" / "extension-context-menu.json"

DEFAULT_PAGE_MENU_ITEMS: dict[str, bool] = {
    "save-archive": True,
    "save-archive-all": True,
    "send-pack-pool": True,
    "save-pool": True,
    "save-saved": True,
    "download-url": True,
    "download-frame": True,
    "toggle-select": True,
    "copy-url": True,
    "open-url": True,
    "reverse-image": True,
    "lookup-username": True,
}

PAGE_MENU_LABELS: dict[str, str] = {
    "save-archive": "Save URL to master archive",
    "save-archive-all": "Save all video URLs to master archive",
    "send-pack-pool": "Send to AOF pack / loot pool",
    "save-pool": "Save to pool",
    "save-saved": "Save to Saved Messages",
    "download-url": "Download media",
    "download-frame": "Download frame",
    "toggle-select": "Toggle overlay select",
    "copy-url": "Copy media URL",
    "open-url": "Open media URL",
    "reverse-image": "Reverse image search",
    "lookup-username": "Look up username",
}


def _default_payload() -> dict[str, Any]:
    return {"pageMenu": dict(DEFAULT_PAGE_MENU_ITEMS)}


def _read_raw() -> dict[str, Any]:
    if not _SETTINGS_PATH.is_file():
        return _default_payload()
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_payload()
        return data
    except (OSError, json.JSONDecodeError):
        return _default_payload()


def _write_raw(data: dict[str, Any]) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def effective_page_menu_items(raw: dict[str, Any] | None = None) -> dict[str, bool]:
    src = raw if raw is not None else _read_raw()
    page = src.get("pageMenu") if isinstance(src.get("pageMenu"), dict) else {}
    out = dict(DEFAULT_PAGE_MENU_ITEMS)
    for key in DEFAULT_PAGE_MENU_ITEMS:
        if key in page:
            out[key] = bool(page[key])
    return out


def get_extension_context_menu_settings() -> dict[str, Any]:
    raw = _read_raw()
    items = effective_page_menu_items(raw)
    return {
        "pageMenu": items,
        "labels": PAGE_MENU_LABELS,
    }


def patch_extension_context_menu_settings(page_menu: dict[str, bool] | None) -> dict[str, Any]:
    raw = _read_raw()
    if page_menu:
        cur = effective_page_menu_items(raw)
        for key, val in page_menu.items():
            if key in DEFAULT_PAGE_MENU_ITEMS:
                cur[key] = bool(val)
        raw["pageMenu"] = cur
    _write_raw(raw)
    return get_extension_context_menu_settings()
