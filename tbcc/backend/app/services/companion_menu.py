"""Shared companion bot menus — usable from PTB bot and webhook dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.companion_body_prefs import (
    BODY_PRESET_IDS,
    active_preset_id,
    load_body_prefs,
    preset_label,
)

_UI_ROOT = Path(__file__).resolve().parent.parent / "data" / "companion_ui"
HERO_IMAGE = _UI_ROOT / "main_menu_hero_v1.png"


def hero_image_path() -> Path | None:
    if HERO_IMAGE.is_file():
        return HERO_IMAGE
    return None


def welcome_caption(*, allowance: str, character_name: str | None = None, vip_line: str = "") -> str:
    lines = [
        "<b>AOF Spicy Talk</b> — your private AI companion.",
        "",
        "Upload a photo · pick her look · chat in first person.",
        "",
        f"<b>Reveals left:</b> {allowance}{vip_line}",
    ]
    if character_name:
        lines.extend(["", f"✨ <b>{character_name}</b> is live — message her anytime."])
    else:
        lines.extend(["", "<i>Send a photo to bring her to life.</i>"])
    return "\n".join(lines)


def start_menu_text(*, allowance: str, character_name: str | None = None, vip_line: str = "", op_line: str = "") -> str:
    """Text-only fallback when hero image is unavailable."""
    head = welcome_caption(allowance=allowance, character_name=character_name, vip_line=vip_line)
    if op_line:
        head += f"\n\n<i>{op_line}</i>"
    return head


def main_menu_keyboard(*, age_confirmed: bool = True, video_enabled: bool = True) -> InlineKeyboardMarkup:
    row1: list[InlineKeyboardButton] = []
    if not age_confirmed:
        row1.append(InlineKeyboardButton("✅ I'm 18+", callback_data="comp_menu:age"))
    row1.append(InlineKeyboardButton("📸 Photo reveal", callback_data="comp_menu:reveal"))
    if video_enabled:
        row1.append(InlineKeyboardButton("🎬 Video reveal", callback_data="comp_menu:video"))
    rows: list[list[InlineKeyboardButton]] = [row1]
    rows.append(
        [
            InlineKeyboardButton("💃 Body preset", callback_data="comp_menu:styles"),
            InlineKeyboardButton("🔥 Pick pose", callback_data="comp_menu:poses"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("💬 Chat", callback_data="comp_menu:chat_hint"),
            InlineKeyboardButton("✏️ Rename", callback_data="comp_menu:name"),
            InlineKeyboardButton("⭐ Balance", callback_data="comp_menu:balance"),
        ]
    )
    rows.append([InlineKeyboardButton("🗑 Clear chat memory", callback_data="comp_menu:reset")])
    return InlineKeyboardMarkup(rows)


def main_menu_markup_dict(*, age_confirmed: bool = True, video_enabled: bool = True) -> dict[str, Any]:
    return main_menu_keyboard(age_confirmed=age_confirmed, video_enabled=video_enabled).to_dict()


def body_preset_keyboard(user_data: dict | None = None) -> InlineKeyboardMarkup:
    prefs = load_body_prefs(user_data or {})
    active = active_preset_id(prefs)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for preset_id in BODY_PRESET_IDS:
        label = preset_label(preset_id, selected=(active == preset_id))
        row.append(InlineKeyboardButton(label, callback_data=f"comp_preset:{preset_id}"))
    rows.append(row)
    rows.append(
        [
            InlineKeyboardButton("Clear preset", callback_data="comp_preset:clear"),
            InlineKeyboardButton("Done ✓", callback_data="comp_preset:done"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def pose_keyboard(poses: list[str], *, selected: str | None = None) -> InlineKeyboardMarkup | None:
    if not poses:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, pose in enumerate(poses[:16]):
        prefix = "✓ " if selected and pose == selected else ""
        label = f"{prefix}{pose}" if len(pose) <= 20 else f"{prefix}{pose[:17]}…"
        row.append(InlineKeyboardButton(label, callback_data=f"comp_pose:{i}"))
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    clear_label = "✓ Default (no pose)" if not selected else "Default (no pose)"
    rows.append([InlineKeyboardButton(clear_label, callback_data="comp_pose:clear")])
    return InlineKeyboardMarkup(rows)


def video_pose_keyboard(poses: list[dict[str, str]], *, selected_id: str | None = None) -> InlineKeyboardMarkup | None:
    if not poses:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, pose in enumerate(poses[:12]):
        pid = str(pose.get("id") or "")
        name = str(pose.get("name") or pid or f"Pose {i}")
        prefix = "✓ " if selected_id and pid == selected_id else ""
        label = f"{prefix}{name}" if len(name) <= 20 else f"{prefix}{name[:17]}…"
        row.append(InlineKeyboardButton(label, callback_data=f"comp_vpose:{i}"))
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Default video (no pose)", callback_data="comp_vpose:clear")])
    return InlineKeyboardMarkup(rows)


def repeat_menu_hint_text() -> str:
    return "Want another? Pick an option below or send a new photo."


def delivery_navigation_keyboard(*, video_enabled: bool = True) -> InlineKeyboardMarkup:
    """Compact QoL nav attached to reveal photo/video captions."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🏠 Main menu", callback_data="comp_menu:home")],
        [
            InlineKeyboardButton("📸 Another photo", callback_data="comp_menu:reveal"),
            InlineKeyboardButton("🔥 Change pose", callback_data="comp_menu:poses"),
        ],
    ]
    row2: list[InlineKeyboardButton] = [
        InlineKeyboardButton("💃 Body preset", callback_data="comp_menu:styles"),
    ]
    if video_enabled:
        row2.append(InlineKeyboardButton("🎬 Video", callback_data="comp_menu:video"))
    row2.append(InlineKeyboardButton("⭐ Balance", callback_data="comp_menu:balance"))
    rows.append(row2)
    rows.append(
        [
            InlineKeyboardButton("✏️ Rename", callback_data="comp_menu:name"),
            InlineKeyboardButton("💬 Chat tips", callback_data="comp_menu:chat_hint"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def delivery_navigation_markup_dict(*, video_enabled: bool = True) -> dict[str, Any]:
    return delivery_navigation_keyboard(video_enabled=video_enabled).to_dict()
