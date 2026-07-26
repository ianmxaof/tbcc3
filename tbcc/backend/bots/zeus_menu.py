"""Zeus Phase 1 — secretary hub menu IA (Network | Inbox | Ops | More).

Callback contract:
  - New buttons use ``zeus:…`` prefixes.
  - Legacy ``sec:menu:…`` callbacks remain valid (aliases).
  - ``normalize_menu_callback`` maps both into the existing ``sec:menu:`` handler path.
"""
from __future__ import annotations

import html
import os
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_DEFAULT_PAYMENT_BOT_USERNAME = "aofsubscriptions_bot"
_DEFAULT_LOOT_BOT_USERNAME = "aof_lootgod_bot"
_DEFAULT_COMPANION_BOT_USERNAME = "aof_spicybot_bot"

# zeus:… → sec:menu:… (empty string = handled specially / no remap needed beyond home)
_ZEUS_TO_SEC: dict[str, str] = {
    "zeus:home": "sec:menu:home",
    "zeus:net:home": "sec:menu:cat:net",
    "zeus:inbox:home": "sec:menu:cat:inbox",
    "zeus:ops:home": "sec:menu:cat:ops",
    "zeus:more:home": "sec:menu:cat:more",
    "zeus:inbox:full": "sec:menu:run:inbox",
    "zeus:inbox:now": "sec:menu:run:now",
    "zeus:inbox:pay": "sec:menu:run:payment",
    "zeus:inbox:loot": "sec:menu:run:loot",
    "zeus:inbox:crit": "sec:menu:run:critical",
    "zeus:inbox:read": "sec:menu:run:read",
    "zeus:inbox:status": "sec:menu:run:status",
    "zeus:ops:stack": "sec:menu:run:stack",
    "zeus:ops:relief": "sec:menu:run:relief",
    "zeus:ops:focus": "sec:menu:run:focus",
    "zeus:ops:triage": "sec:menu:run:triage",
    "zeus:ops:flywheel": "sec:menu:run:flywheel",
    "zeus:ops:feed": "sec:menu:run:ops",
    "zeus:ops:toasts": "sec:menu:cat:toasts",
    "zeus:ops:skipbacklog": "sec:menu:run:skipbacklog",
    "zeus:more:faq": "sec:menu:cat:faq",
    "zeus:more:pay": "sec:menu:cat:pay",
    "zeus:more:hubcopy": "sec:menu:hubcopy",
    "zeus:more:config": "sec:menu:run:config",
    "zeus:more:commands": "sec:menu:run:commands",
    "zeus:net:mystatus": "sec:menu:mystatus",
    "zeus:net:reset": "sec:menu:reset",
}


def payment_bot_username() -> str:
    """Checkout links must never resolve to the secretary bot."""
    sec = (os.getenv("TBCC_SECRETARY_BOT_USERNAME") or "").strip().lstrip("@")
    u = (
        os.getenv("TBCC_PAYMENT_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or _DEFAULT_PAYMENT_BOT_USERNAME
    ).strip().lstrip("@")
    if sec and u.lower() == sec.lower():
        return _DEFAULT_PAYMENT_BOT_USERNAME
    return u or _DEFAULT_PAYMENT_BOT_USERNAME


def loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or _DEFAULT_LOOT_BOT_USERNAME).strip().lstrip("@")


def companion_bot_username() -> str:
    return (
        os.getenv("TBCC_COMPANION_BOT_USERNAME") or _DEFAULT_COMPANION_BOT_USERNAME
    ).strip().lstrip("@")


def normalize_menu_callback(data: str | None) -> str | None:
    """Map ``zeus:`` / ``sec:menu:`` into a ``sec:menu:`` path for the shared handler."""
    raw = (data or "").strip()
    if not raw:
        return None
    if raw.startswith("sec:menu:"):
        return raw
    if raw.startswith("zeus:"):
        mapped = _ZEUS_TO_SEC.get(raw)
        if mapped:
            return mapped
        # Prefix rewrite: zeus:X → sec:menu:X for forward-compat
        rest = raw[len("zeus:") :]
        if rest:
            return f"sec:menu:{rest}"
    return None


def format_stack_status_html(data: dict[str, Any] | None) -> str:
    """Render GET /ops/stack-status (or tray CLI Status) for Telegram HTML."""
    if not data:
        return "🖥 <b>Stack status</b>\n\n<code>unavailable</code> — empty response."
    if data.get("available") is False or (data.get("ok") is False and data.get("error")):
        err = html.escape(str(data.get("error") or "stack control unavailable"))
        return (
            "🖥 <b>Stack status</b>\n\n"
            f"<code>{err}</code>\n"
            "<i>Tray supervisor / tbcc-stack-cli.ps1 required on Windows.</i>"
        )
    enabled_up = data.get("enabled_up")
    enabled = data.get("enabled")
    up = data.get("up")
    total = data.get("total")
    profile = html.escape(str(data.get("profile") or "—"))
    summary = f"{enabled_up}/{enabled}" if enabled_up is not None and enabled is not None else "—"
    lines = [
        "🖥 <b>Stack status</b>",
        "",
        f"Enabled up: <b>{html.escape(str(summary))}</b>",
        f"All up/total: <code>{html.escape(str(up))}/{html.escape(str(total))}</code>",
        f"Profile: <code>{profile}</code>",
        "",
    ]
    services = data.get("services")
    if isinstance(services, list) and services:
        lines.append("<b>Services</b>")
        for row in services:
            if not isinstance(row, dict):
                continue
            sid = html.escape(str(row.get("id") or "?"))
            st = str(row.get("status") or ("up" if row.get("running") else "down"))
            mark = "●" if st == "up" or row.get("running") else "○"
            user_on = row.get("user_enabled")
            flag = "" if user_on is None else (" · on" if user_on else " · off")
            lines.append(f"{mark} <code>{sid}</code> {html.escape(st)}{flag}")
    else:
        lines.append("<i>No per-service rows (CLI may be unavailable).</i>")
    lines.append("")
    lines.append("<i>Restarts: tray Services menu or tbcc-stack-cli.ps1 — not this bot.</i>")
    return "\n".join(lines)


def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌐 Network", callback_data="zeus:net:home"),
                InlineKeyboardButton("📬 Inbox", callback_data="zeus:inbox:home"),
            ],
            [
                InlineKeyboardButton("🔧 Ops", callback_data="zeus:ops:home"),
                InlineKeyboardButton("⋯ More", callback_data="zeus:more:home"),
            ],
        ]
    )


def user_main_menu_keyboard() -> InlineKeyboardMarkup:
    pay = payment_bot_username()
    loot = loot_bot_username()
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⭐ Subscribe", url=f"https://t.me/{pay}?start=subscribe"),
            InlineKeyboardButton("🛒 Shop", url=f"https://t.me/{pay}?start=shop"),
        ],
        [
            InlineKeyboardButton("🎲 Loot Room", url=f"https://telegram.me/{loot}"),
            InlineKeyboardButton("💳 Payment bot", url=f"https://t.me/{pay}"),
        ],
        [
            InlineKeyboardButton("ℹ️ My status", callback_data="zeus:net:mystatus"),
            InlineKeyboardButton("🔄 Reset context", callback_data="zeus:net:reset"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def network_submenu_keyboard() -> InlineKeyboardMarkup:
    pay = payment_bot_username()
    loot = loot_bot_username()
    companion = companion_bot_username()
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⭐ Subscribe", url=f"https://t.me/{pay}?start=subscribe"),
            InlineKeyboardButton("🛒 Shop", url=f"https://t.me/{pay}?start=shop"),
        ],
        [
            InlineKeyboardButton("🎲 Loot Room", url=f"https://telegram.me/{loot}"),
            InlineKeyboardButton("🔥 Companion", url=f"https://t.me/{companion}"),
        ],
        [
            InlineKeyboardButton("ℹ️ My status", callback_data="zeus:net:mystatus"),
            InlineKeyboardButton("⭐ FAQ shortcuts", callback_data="zeus:more:faq"),
        ],
        [InlineKeyboardButton("◀ Main menu", callback_data="zeus:home")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_inbox_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📥 Full inbox", callback_data="zeus:inbox:full"),
                InlineKeyboardButton("🔔 Unread", callback_data="zeus:inbox:now"),
            ],
            [
                InlineKeyboardButton("💰 Payment", callback_data="zeus:inbox:pay"),
                InlineKeyboardButton("🎮 Loot", callback_data="zeus:inbox:loot"),
            ],
            [
                InlineKeyboardButton("🔴 Critical", callback_data="zeus:inbox:crit"),
                InlineKeyboardButton("✅ Mark read", callback_data="zeus:inbox:read"),
            ],
            [InlineKeyboardButton("📊 Status", callback_data="zeus:inbox:status")],
            [InlineKeyboardButton("◀ Main menu", callback_data="zeus:home")],
        ]
    )


def admin_ops_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🖥 Stack status", callback_data="zeus:ops:stack"),
                InlineKeyboardButton("🎯 Focus state", callback_data="zeus:ops:focus"),
            ],
            [
                InlineKeyboardButton("⚡ Telegram relief", callback_data="zeus:ops:relief"),
                InlineKeyboardButton("🔄 Flywheel", callback_data="zeus:ops:flywheel"),
            ],
            [
                InlineKeyboardButton("🧰 Triage bundle", callback_data="zeus:ops:triage"),
                InlineKeyboardButton("📋 Ops feed", callback_data="zeus:ops:feed"),
            ],
            [
                InlineKeyboardButton("🔔 Toast budget", callback_data="zeus:ops:toasts"),
                InlineKeyboardButton("🔕 Skip backlog", callback_data="zeus:ops:skipbacklog"),
            ],
            [
                InlineKeyboardButton("📋 Copy hub tail", callback_data="zeus:more:hubcopy"),
            ],
            [InlineKeyboardButton("◀ Main menu", callback_data="zeus:home")],
        ]
    )


def admin_more_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ FAQ shortcuts", callback_data="zeus:more:faq"),
                InlineKeyboardButton("💳 Payment links", callback_data="zeus:more:pay"),
            ],
            [InlineKeyboardButton("📋 Copy hub tail", callback_data="zeus:more:hubcopy")],
            [
                InlineKeyboardButton("🤖 LLM config", callback_data="zeus:more:config"),
                InlineKeyboardButton("📖 All commands", callback_data="zeus:more:commands"),
            ],
            [InlineKeyboardButton("◀ Main menu", callback_data="zeus:home")],
        ]
    )


def payment_inline_keyboard() -> InlineKeyboardMarkup | None:
    pay = payment_bot_username()
    if not pay:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ Subscribe", url=f"https://t.me/{pay}?start=subscribe"),
                InlineKeyboardButton("🛒 Shop", url=f"https://t.me/{pay}?start=shop"),
            ],
            [InlineKeyboardButton("📋 Payment bot chat", url=f"https://t.me/{pay}")],
        ]
    )
