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
from app.services.companion_monetize_cta import companion_exhaustion_inline_keyboard_rows

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
    rows.append([InlineKeyboardButton("🌐 Explore AOF", callback_data="aof_net:home")])
    return InlineKeyboardMarkup(rows)


def main_menu_markup_dict(*, age_confirmed: bool = True, video_enabled: bool = True) -> dict[str, Any]:
    return main_menu_keyboard(age_confirmed=age_confirmed, video_enabled=video_enabled).to_dict()


def submenu_nav_row(*, include_reveal: bool = True, video_enabled: bool = True) -> list[InlineKeyboardButton]:
    """Bottom nav row for sub-menus — keeps users from getting stuck."""
    row: list[InlineKeyboardButton] = [
        InlineKeyboardButton("🏠 Main menu", callback_data="comp_menu:home"),
    ]
    if include_reveal:
        row.append(InlineKeyboardButton("📸 Photo reveal", callback_data="comp_menu:reveal"))
    if video_enabled:
        row.append(InlineKeyboardButton("🎬 Video", callback_data="comp_menu:video"))
    return row


def append_submenu_nav(
    rows: list[list[InlineKeyboardButton]],
    *,
    include_reveal: bool = True,
    video_enabled: bool = True,
) -> None:
    nav = submenu_nav_row(include_reveal=include_reveal, video_enabled=video_enabled)
    if nav:
        rows.append(nav)

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
    append_submenu_nav(rows)
    return InlineKeyboardMarkup(rows)


def pose_keyboard(
    poses: list[str],
    *,
    selected: str | None = None,
    buttons_per_row: int = 3,
) -> InlineKeyboardMarkup | None:
    if not poses:
        return None
    per_row = max(1, min(3, int(buttons_per_row)))
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, pose in enumerate(poses[:24]):
        prefix = "✓ " if selected and pose == selected else ""
        label = f"{prefix}{pose}" if len(pose) <= 18 else f"{prefix}{pose[:15]}…"
        row.append(InlineKeyboardButton(label, callback_data=f"comp_pose:{i}"))
        if len(row) >= per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    clear_label = "✓ Default" if not selected else "Default"
    rows.append(
        [
            InlineKeyboardButton(clear_label, callback_data="comp_pose:clear"),
            InlineKeyboardButton("🏠 Main menu", callback_data="comp_menu:home"),
            InlineKeyboardButton("📸 Reveal", callback_data="comp_menu:reveal"),
        ]
    )
    return InlineKeyboardMarkup(rows)


VIDEO_POSES_PER_PAGE = 15


def video_pose_page_count(poses: list[dict[str, str]], *, per_page: int = VIDEO_POSES_PER_PAGE) -> int:
    if not poses:
        return 0
    per = max(1, int(per_page))
    return (len(poses) + per - 1) // per


def video_pose_keyboard(
    poses: list[dict[str, str]],
    *,
    page: int = 0,
    per_page: int = VIDEO_POSES_PER_PAGE,
    selected_id: str | None = None,
) -> InlineKeyboardMarkup | None:
    if not poses:
        return None
    per = max(1, int(per_page))
    total_pages = video_pose_page_count(poses, per_page=per)
    page = max(0, min(page, max(0, total_pages - 1)))
    start = page * per
    chunk = poses[start : start + per]

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for offset, pose in enumerate(chunk):
        global_idx = start + offset
        pid = str(pose.get("id") or "")
        name = str(pose.get("name") or pid or f"Pose {global_idx}")
        prefix = "✓ " if selected_id and pid == selected_id else ""
        label = f"{prefix}{name}" if len(name) <= 20 else f"{prefix}{name[:17]}…"
        row.append(InlineKeyboardButton(label, callback_data=f"comp_vpose:{global_idx}"))
        if len(row) >= 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"comp_vpage:{page - 1}"))
        nav.append(InlineKeyboardButton(f"· {page + 1}/{total_pages} ·", callback_data="comp_vpage:stay"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"comp_vpage:{page + 1}"))
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("Default video", callback_data="comp_vpose:clear"),
            InlineKeyboardButton("🏠 Main menu", callback_data="comp_menu:home"),
            InlineKeyboardButton("📸 Reveal", callback_data="comp_menu:reveal"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def repeat_menu_hint_text() -> str:
    return "Want another? Pick an option below or send a new photo."


def delivery_navigation_keyboard(*, video_enabled: bool = True) -> InlineKeyboardMarkup:
    """Compact QoL nav attached to reveal photo/video captions."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🏠 Main menu", callback_data="comp_menu:home"),
            InlineKeyboardButton("🔁 Try again", callback_data="comp_menu:redo"),
        ],
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
    for monetize_row in companion_exhaustion_inline_keyboard_rows():
        rows.append(
            [InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in monetize_row]
        )
    return InlineKeyboardMarkup(rows)


def delivery_navigation_markup_dict(*, video_enabled: bool = True) -> dict[str, Any]:
    return delivery_navigation_keyboard(video_enabled=video_enabled).to_dict()
