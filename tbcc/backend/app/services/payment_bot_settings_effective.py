from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.payment_bot_settings import PaymentBotSettings

ROW_ID = 1

DEFAULT_MAIN_MENU: list[list[dict[str, str]]] = [
    [{"label": "🗝 Loot Room (24h key)", "action": "menu_loot"}],
    [
        {"label": "💎 Premium (group)", "action": "menu_subscribe"},
        {"label": "📦 Digital packs", "action": "menu_packs"},
    ],
    [
        {"label": "🔗 Referral", "action": "menu_referral"},
        {"label": "📋 Status", "action": "menu_status"},
    ],
]

ALLOWED_MENU_ACTIONS = {
    "menu_shop",
    "menu_loot",
    "menu_loot_subscribe",
    "menu_subscribe",
    "menu_packs",
    "menu_referral",
    "menu_status",
}


def _row(db: Session) -> PaymentBotSettings | None:
    return db.query(PaymentBotSettings).filter(PaymentBotSettings.id == ROW_ID).first()


def _str_or_default(db_val: object | None, default: str) -> str:
    if db_val is not None and str(db_val).strip():
        return str(db_val).strip()
    return default


def _int_or_default(db_val: object | None, default: int, *, min_v: int, max_v: int) -> int:
    try:
        if db_val is not None:
            return max(min_v, min(max_v, int(db_val)))
    except (TypeError, ValueError):
        pass
    return max(min_v, min(max_v, default))


def _normalize_main_menu(raw_json: str | None) -> list[list[dict[str, str]]]:
    if not raw_json or not raw_json.strip():
        return DEFAULT_MAIN_MENU
    try:
        data = json.loads(raw_json)
    except Exception:
        return DEFAULT_MAIN_MENU
    if not isinstance(data, list):
        return DEFAULT_MAIN_MENU
    rows: list[list[dict[str, str]]] = []
    for row in data[:8]:
        if not isinstance(row, list):
            continue
        out_row: list[dict[str, str]] = []
        for btn in row[:4]:
            if not isinstance(btn, dict):
                continue
            label = str(btn.get("label") or "").strip()
            action = str(btn.get("action") or "").strip()
            if not label or action not in ALLOWED_MENU_ACTIONS:
                continue
            out_row.append({"label": label[:64], "action": action})
        if out_row:
            rows.append(out_row)
    return rows or DEFAULT_MAIN_MENU


def get_effective_payment_bot_settings(db: Session) -> dict[str, Any]:
    r = _row(db)
    return {
        "main_menu": _normalize_main_menu(getattr(r, "main_menu_json", None) if r else None),
        "welcome_html": _str_or_default(
            getattr(r, "welcome_html", None) if r else None,
            "",
        ),
        "loot_intro_html": _str_or_default(
            getattr(r, "loot_intro_html", None) if r else None,
            "",
        ),
        "subscribe_title_main": _str_or_default(
            getattr(r, "subscribe_title_main", None) if r else None,
            "💎 **Premium Access**",
        ),
        "subscribe_title_loot": _str_or_default(
            getattr(r, "subscribe_title_loot", None) if r else None,
            "🗝 **Loot Room Access**",
        ),
        "subscription_catalog_columns": _int_or_default(
            getattr(r, "subscription_catalog_columns", None) if r else None,
            2,
            min_v=1,
            max_v=4,
        ),
        "min_subscription_stars": _int_or_default(
            getattr(r, "min_subscription_stars", None) if r else None,
            0,
            min_v=0,
            max_v=1000000,
        ),
        "runtime_adapter": _str_or_default(
            getattr(r, "runtime_adapter", None) if r else None,
            "",
        ).lower()
        or None,
        "runtime_cmd_start": _str_or_default(
            getattr(r, "runtime_cmd_start", None) if r else None,
            "",
        )
        or None,
        "runtime_cmd_stop": _str_or_default(
            getattr(r, "runtime_cmd_stop", None) if r else None,
            "",
        )
        or None,
        "runtime_cmd_restart": _str_or_default(
            getattr(r, "runtime_cmd_restart", None) if r else None,
            "",
        )
        or None,
        "runtime_cmd_reload": _str_or_default(
            getattr(r, "runtime_cmd_reload", None) if r else None,
            "",
        )
        or None,
        "runtime_cmd_status": _str_or_default(
            getattr(r, "runtime_cmd_status", None) if r else None,
            "",
        )
        or None,
    }
