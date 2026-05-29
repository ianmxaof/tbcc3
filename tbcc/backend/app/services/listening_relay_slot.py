"""Per-slot copy-panel options (scheduler parity) for listening relay."""

from __future__ import annotations

import json
from typing import Any

from app.models.listening_relay_settings import ListeningRelaySettings

DEFAULT_SLOT_EXTRA: dict[str, Any] = {
    "copy_buttons": [],
    "copy_media_ids": [],
    "copy_attachment_urls": [],
    "copy_album_order_mode": "static",
    "copy_pin_after_send": False,
    "copy_checkout_stars_enabled": False,
    "copy_checkout_stars_plan_id": None,
    "copy_checkout_button_label": None,
    "copy_checkout_referral_code": None,
}


def _normalize_button(btn: Any) -> dict[str, str] | None:
    if not isinstance(btn, dict):
        return None
    text = str(btn.get("text") or "").strip()
    url = str(btn.get("url") or "").strip()
    if text and url:
        return {"text": text[:64], "url": url[:2048]}
    return None


def normalize_slot_extra(raw: Any) -> dict[str, Any]:
    out = dict(DEFAULT_SLOT_EXTRA)
    if not isinstance(raw, dict):
        return out
    btns = raw.get("copy_buttons")
    if isinstance(btns, list):
        out["copy_buttons"] = [b for x in btns if (b := _normalize_button(x))]
    mids = raw.get("copy_media_ids")
    if isinstance(mids, list):
        cleaned: list[int] = []
        for x in mids:
            try:
                cleaned.append(int(x))
            except (TypeError, ValueError):
                pass
        out["copy_media_ids"] = cleaned[:10]
    urls = raw.get("copy_attachment_urls")
    if isinstance(urls, list):
        out["copy_attachment_urls"] = [str(u).strip() for u in urls if str(u).strip()][:10]
    mode = str(raw.get("copy_album_order_mode") or "static").strip().lower()
    if mode in ("static", "shuffle", "carousel"):
        out["copy_album_order_mode"] = mode
    out["copy_pin_after_send"] = bool(raw.get("copy_pin_after_send"))
    out["copy_checkout_stars_enabled"] = bool(raw.get("copy_checkout_stars_enabled"))
    pid = raw.get("copy_checkout_stars_plan_id")
    try:
        out["copy_checkout_stars_plan_id"] = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        out["copy_checkout_stars_plan_id"] = None
    lbl = raw.get("copy_checkout_button_label")
    out["copy_checkout_button_label"] = str(lbl).strip()[:64] if lbl else None
    ref = raw.get("copy_checkout_referral_code")
    out["copy_checkout_referral_code"] = (
        "".join(c for c in str(ref) if c.isalnum())[:16] if ref else None
    )
    return out


def slot_extras_raw(row: ListeningRelaySettings) -> list[Any]:
    raw_json = getattr(row, "message_slot_extras_json", None)
    if not raw_json:
        return []
    try:
        arr = json.loads(raw_json)
        return arr if isinstance(arr, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def resolve_slot_extra(row: ListeningRelaySettings, slot_idx: int, n_templates: int) -> dict[str, Any]:
    slots = slot_extras_raw(row)
    if not slots:
        return dict(DEFAULT_SLOT_EXTRA)
    nt = max(1, n_templates)
    if len(slots) == 1:
        return normalize_slot_extra(slots[0])
    padded = list(slots)
    while len(padded) < nt:
        padded.append({})
    if slot_idx < 0 or slot_idx >= len(padded):
        return dict(DEFAULT_SLOT_EXTRA)
    return normalize_slot_extra(padded[slot_idx])


def slot_extras_for_api(row: ListeningRelaySettings, n_templates: int) -> list[dict[str, Any]]:
    from app.services.listening_relay_templates import get_template_variations_list

    n = len(get_template_variations_list(row)) if n_templates <= 0 else n_templates
    if n == 0:
        return []
    slots = slot_extras_raw(row)
    if not slots:
        return [dict(DEFAULT_SLOT_EXTRA) for _ in range(n)]
    if len(slots) == 1:
        return [normalize_slot_extra(slots[0]) for _ in range(n)]
    padded = [normalize_slot_extra(x) for x in slots]
    while len(padded) < n:
        padded.append(dict(DEFAULT_SLOT_EXTRA))
    return padded[:n]
