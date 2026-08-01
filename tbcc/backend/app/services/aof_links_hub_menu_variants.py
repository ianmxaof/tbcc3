"""AOF LINK HUB menu variants — channel pipes + AI partnership boards (Telegram HTML)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.data.aof_network import ADDLIST_RAW, MAINHUB_RAW, MAIN_GROUP_INVITE
from app.services.aof_growth_hub import gate_urls, lv_urls
from app.services.promo_affiliate_rotation import (
    affiliate_outbound_url,
    build_sponsor_link_html,
    list_candidates,
)

MenuKind = Literal["channels", "ai"]
VariantId = Literal["v1", "v2", "v3"]

CHANNEL_VARIANTS: tuple[VariantId, ...] = ("v1", "v2", "v3")
AI_VARIANTS: tuple[VariantId, ...] = ("v1", "v2", "v3")

TBCC_ROOT = Path(__file__).resolve().parents[3]
MENU_IMAGE_DIR = TBCC_ROOT / "docs" / "samples" / "link_hub_menus" / "images"

MENU_IMAGE_FILES: dict[tuple[MenuKind, VariantId], str] = {
    ("channels", "v1"): "channels_v1_classic_orange_panel.png",
    ("channels", "v2"): "channels_v2_neon_grid.png",
    ("channels", "v3"): "channels_v3_vhs_broadcast.png",
    ("ai", "v1"): "ai_v1_dark_panel.png",
    ("ai", "v2"): "ai_v2_reveal_board.png",
    ("ai", "v3"): "ai_v3_uniform_grid.png",
}

CHANNEL_PIPES: tuple[tuple[str, str, str], ...] = (
    ("01", "addlist", "ADDLIST · ALL CHANNELS"),
    ("02", "ai", "AOF AI"),
    ("03", "ass", "AOF ASS"),
    ("04", "bop", "AOF BOP"),
    ("05", "big_tits", "AOF BIG TITS"),
    ("06", "packs", "AOF PACKS"),
    ("07", "taboo", "AOF TABOO"),
    ("08", "milf", "AOF MILF / GILF"),
    ("09", "abg", "AOF ABG / LBFM"),
    ("10", "goon", "AOF GOON"),
    ("11", "blowjob", "AOF BLOWJOB"),
    ("12", "loot", "AOF LOOT ROOM"),
)


@dataclass(frozen=True)
class MenuVariant:
    kind: MenuKind
    variant: VariantId
    title: str
    html: str


@dataclass(frozen=True)
class InteractiveMenuPost:
    """Photo menu for Telegram: decorative PNG + clickable inline URL buttons.

    Telegram cannot attach hotspots inside an image — each item must be an
  inline keyboard URL button (or an HTML link in the caption/text).
    """

    kind: MenuKind
    variant: VariantId
    title: str
    image_path: Path
    caption_html: str
    inline_keyboard: list[list[dict[str, str]]]


def menu_image_path(kind: MenuKind, variant: VariantId) -> Path:
    name = MENU_IMAGE_FILES.get((kind, variant))
    if not name:
        raise KeyError(f"no menu image for {kind}/{variant}")
    return MENU_IMAGE_DIR / name


def _short_btn(text: str, *, max_len: int = 64) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _chunk_buttons(buttons: list[dict[str, str]], *, columns: int = 2) -> list[list[dict[str, str]]]:
    cols = max(1, min(int(columns or 2), 3))
    rows: list[list[dict[str, str]]] = []
    for i in range(0, len(buttons), cols):
        row = buttons[i : i + cols]
        if row:
            rows.append(row)
    return rows


def build_channel_inline_buttons(db: Session, *, columns: int = 2) -> list[list[dict[str, str]]]:
    """One URL button per content pipe — opens gate/invite for that lane."""
    lv = lv_urls(db)
    buttons: list[dict[str, str]] = []
    for num, key, label in CHANNEL_PIPES:
        url = _gate_href(lv, key)
        if not url:
            continue
        short = label.split("·")[0].strip() if "·" in label else label
        buttons.append({"text": _short_btn(f"{num} {short}"), "url": url})
    hub = MAINHUB_RAW
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    nav = [
        {"text": "🔗 HUB", "url": hub},
        {"text": "🪙 LOOT", "url": loot},
        {"text": "📌 ADDLIST", "url": addlist},
    ]
    return _chunk_buttons(buttons, columns=columns) + [nav]


def build_ai_inline_buttons(db: Session, *, columns: int = 2, limit: int = 18) -> list[list[dict[str, str]]]:
    """One URL button per links_hub_ai affiliate — your referral/beacon outbound URL."""
    rows = list_candidates(db, "links_hub_ai")[:limit]
    if not rows:
        rows = list_candidates(db, "links_hub", network_key="ai")[:limit]
    buttons: list[dict[str, str]] = []
    for i, row in enumerate(rows, start=1):
        url = affiliate_outbound_url(row, db=db, placement="links_hub_ai")
        if not url.startswith(("http://", "https://", "tg://")):
            continue
        label = (row.label or "Partner").strip()
        buttons.append({"text": _short_btn(f"{i:02d} {label}"), "url": url})
    footer = [
        {"text": "📋 Secretary", "url": "https://t.me/aof_secretary_bot"},
        {"text": "🎲 Loot God", "url": "https://t.me/aof_lootgod_bot?start=loot_free"},
        {"text": "🌶 Spicy", "url": "https://t.me/aof_spicybot_bot"},
    ]
    lv = gate_urls(db)
    hub = MAINHUB_RAW
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    nav = [
        {"text": "🔗 HUB", "url": hub},
        {"text": "🪙 LOOT", "url": loot},
    ]
    return _chunk_buttons(buttons, columns=columns) + [footer, nav]


def _interactive_menu_caption(kind: MenuKind, title: str) -> str:
    """Short caption under menu PNG — in-world copy only (no meta about buttons/attribution)."""
    if kind == "channels":
        return (
            f"<b>📌 AOF LINK HUB</b> · <i>{title}</i>\n"
            "<b>MAIN · COMM · UNITY</b> · lane index below\n"
            "<i>Subscribe & enjoy.</i>"
        )
    return (
        f"<b>🧠 AOF AI PARTNERS</b> · <i>{title}</i>\n"
        "<b>UNDRESS · GENERATOR</b> · pick a lane below\n"
        "<i>Eighteen partners · unlimited possibilities.</i>"
    )


def build_interactive_menu_post(
    db: Session,
    kind: MenuKind,
    variant: VariantId = "v1",
    *,
    button_columns: int = 2,
) -> InteractiveMenuPost:
    """Combine variant artwork + short caption + per-item inline URL buttons."""
    if kind == "channels":
        menu = build_channel_menu_variant(db, variant)
        keyboard = build_channel_inline_buttons(db, columns=button_columns)
        caption = _interactive_menu_caption("channels", menu.title)
    else:
        menu = build_ai_menu_variant(db, variant)
        keyboard = build_ai_inline_buttons(db, columns=button_columns)
        caption = _interactive_menu_caption("ai", menu.title)
    return InteractiveMenuPost(
        kind=kind,
        variant=variant,
        title=menu.title,
        image_path=menu_image_path(kind, variant),
        caption_html=caption,
        inline_keyboard=keyboard,
    )


def interactive_post_as_bot_api(post: InteractiveMenuPost) -> dict[str, Any]:
    """Payload shape for sendPhoto + reply_markup via payment bot."""
    return {
        "caption": post.caption_html,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": post.inline_keyboard},
        "photo_path": str(post.image_path),
    }


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _gate_href(lv: dict[str, str], key: str) -> str:
    from app.data.aof_manual_gate_links import manual_gate_url
    from app.data.aof_network import network_channel_by_key

    url = (lv.get(key) or manual_gate_url(key) or "").strip()
    if not url:
        ch = network_channel_by_key(key)
        url = (ch.invite if ch else "").strip()
    return url


def _gate_plain_line(lv: dict[str, str], num: str, key: str, label: str) -> str:
    url = _gate_href(lv, key)
    if not url:
        return f"{num} {label}"
    return f"{num} {label} · {url}"


def _gate_line(lv: dict[str, str], num: str, key: str, label: str) -> str:
    url = _gate_href(lv, key)
    if not url:
        return f"{num} {label}"
    return f'{num} <a href="{_esc(url)}">{_esc(label)}</a>'


def _pre_block(lines: list[str]) -> str:
    body = "\n".join(lines)
    return f"<pre>{html.escape(body)}</pre>"


def _ai_rows(db: Session, *, limit: int = 18) -> list[tuple[str, str]]:
    rows = list_candidates(db, "links_hub_ai")[:limit]
    if not rows:
        rows = list_candidates(db, "links_hub", network_key="ai")[:limit]
    out: list[tuple[str, str]] = []
    for i, row in enumerate(rows, start=1):
        label = (row.label or "Partner").strip()
        line_html = build_sponsor_link_html(row)
        out.append((f"{i:02d}", f"{label} — {line_html}"))
    return out


def build_channel_menu_variant(db: Session, variant: VariantId = "v1") -> MenuVariant:
    lv = lv_urls(db)
    hub = MAINHUB_RAW
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    pipes_html = [_gate_line(lv, num, key, label) for num, key, label in CHANNEL_PIPES]
    pipes_plain = [_gate_plain_line(lv, num, key, label) for num, key, label in CHANNEL_PIPES]

    if variant == "v1":
        frame = _pre_block(
            [
                "╭──────────────────────────────╮",
                "│      —— AOF LINK HUB ——      │",
                "╰──────────────────────────────╯",
                " MAIN · COMM · UNITY",
                " MAIN · AOF · LINK · REPO",
                "",
                f" HUB  {hub}",
                f" FREE LOOT · COMM AREA",
                "",
                " ——— CONTENT PIPES ———",
                *[f" {p}" for p in pipes_plain],
                "",
                " ——— SUBSCRIBE & ENJOY ———",
            ]
        )
        title = "CLASSIC ORANGE PANEL"
        body = (
            f"<b>📌 AOF LINK HUB</b> · <i>{title}</i>\n"
            f"{frame}\n"
            f"🔗 <a href=\"{_esc(hub)}\">@aofmainhub</a> · "
            f"📌 <a href=\"{_esc(addlist)}\">addlist</a>"
        )
    elif variant == "v2":
        grid = "\n".join(
            f"▸ {p}" for p in pipes_html
        )
        body = (
            f"<b>🌐 AOF CHANNEL MATRIX</b> · <i>NEON GRID</i>\n"
            f"<blockquote>{grid}</blockquote>\n"
            f"⚡ <b>ENTRY</b> · "
            f"<a href=\"{_esc(loot)}\">LOOT ROOM</a> · "
            f"<a href=\"{_esc(hub)}\">LINK HUB</a> · "
            f"<a href=\"{_esc(addlist)}\">ADDLIST</a>"
        )
        title = "NEON GRID"
    else:
        scan = _pre_block(
            [
                "┏━ AOF BROADCAST GUIDE ━━━━━━━┓",
                "┃ 12 LANES · 1 NETWORK       ┃",
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
                *[f"┃ {num} {label:<22}┃" for (num, _, label), _ in zip(CHANNEL_PIPES, pipes_plain)],
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
            ]
        )
        body = (
            f"<b>📺 AOF CHANNEL GUIDE</b> · <i>VHS BROADCAST</i>\n"
            f"{scan}\n"
            f"📡 <a href=\"{_esc(addlist)}\">TUNE ALL CHANNELS</a> · "
            f"<a href=\"{_esc(hub)}\">RETURN TO HUB</a>"
        )
        title = "VHS BROADCAST"

    return MenuVariant(kind="channels", variant=variant, title=title, html=body)


def build_ai_menu_variant(db: Session, variant: VariantId = "v1") -> MenuVariant:
    lv = gate_urls(db)
    hub = MAINHUB_RAW
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    ai_rows = _ai_rows(db)
    ai_plain = [(num, line.split(" — ")[0]) for num, line in ai_rows]
    ai_lines = "\n".join(f"→ {num} {line}" for num, line in ai_rows)

    header_links = (
        f"TOP · <a href=\"{_esc(loot)}\">LOOT</a> · "
        f"FUNNEL · <a href=\"{_esc(hub)}\">HUB</a> · "
        f"<a href=\"{_esc(hub)}\">AOFMAINHUB</a>"
    )

    if variant == "v1":
        panel = _pre_block(
            [
                "╭ UNDRESS · GENERATOR LINKS ╮",
                "│ TOP · FUNNEL · AOFMAINHUB │",
                "╰───────────────────────────╯",
                "",
                " AI TOOLS / PARTNERS",
            ]
            + [f" {num} {label}" for num, label in ai_plain]
            + [
                "",
                " MAINBOTS",
                " SEC @aof_secretary_bot",
                " LOOT @aof_lootgod_bot",
                " SPICY @aof_spicybot_bot",
            ]
        )
        body = (
            f"<b>🧠 AOF AI PARTNERS</b> · <i>DARK PANEL</i>\n"
            f"{panel}\n"
            f"{ai_lines}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>MAINBOTS</b> · @aof_secretary_bot · @aof_lootgod_bot · @aof_spicybot_bot\n"
            f"🚀 <b>SUPPORT</b> · /loot · /subscribe · /refer · "
            f"<a href=\"{_esc(_gate_href(lv, 'addlist') or ADDLIST_RAW)}\">ADDLIST</a>"
        )
        title = "DARK PANEL"
    elif variant == "v2":
        lanes = "\n".join(f"✓ {num} {line}" for num, line in ai_rows)
        body = (
            f"<b>✅ AOF AI REVEAL BOARD</b> · <i>tap a lane</i>\n"
            f"<b>UNDRESS · GENERATOR</b> · {header_links}\n"
            f"<blockquote>{lanes}</blockquote>\n"
            f"🤖 @aof_secretary_bot · @aof_lootgod_bot · @aof_spicybot_bot"
        )
        title = "REVEAL BOARD"
    else:
        grid = "\n".join(f"| {num} | {line} |" for num, line in ai_rows)
        body = (
            f"<b>▦ AOF AI GRID</b> · <i>UNIFORM PARTNER MATRIX</i>\n"
            f"<pre>{html.escape(grid)}</pre>\n"
            f"🔗 {header_links}"
        )
        title = "UNIFORM GRID"

    return MenuVariant(kind="ai", variant=variant, title=title, html=body)


def build_all_menu_variants(db: Session) -> list[MenuVariant]:
    out: list[MenuVariant] = []
    for v in CHANNEL_VARIANTS:
        out.append(build_channel_menu_variant(db, v))
    for v in AI_VARIANTS:
        out.append(build_ai_menu_variant(db, v))
    return out
