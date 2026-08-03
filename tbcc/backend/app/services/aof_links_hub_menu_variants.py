"""AOF LINK HUB menu variants — channel pipes + AI partnership boards (Telegram HTML)."""

from __future__ import annotations

import html
import os
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

MenuKind = Literal["channels", "ai", "loot"]
VariantId = Literal["v1", "v2", "v3", "v4", "v5", "v6", "v7"]

CHANNEL_VARIANTS: tuple[VariantId, ...] = ("v1", "v2", "v3", "v4", "v5", "v6", "v7")
AI_VARIANTS: tuple[VariantId, ...] = ("v1", "v2", "v3", "v4", "v5", "v6", "v7")
LOOT_VARIANTS: tuple[VariantId, ...] = ("v5", "v6", "v7")

# v5–v7: wide cards sized to match Telegram 2-col inline keyboard width (not tall 9:16).
BUTTON_TREE_FIT_VARIANTS: tuple[VariantId, ...] = ("v5", "v6", "v7")
MENU_IMAGE_WIDTH_PX = 1280
MENU_IMAGE_HEIGHT_PX = 960  # 4:3 — aligns with bubble + button-tree width on mobile/desktop
MENU_IMAGE_ASPECT = "4:3"


def _tbcc_root() -> Path:
    env = (os.getenv("TBCC_ROOT") or "").strip()
    if env:
        return Path(env)
    p = Path(__file__).resolve().parents[3]
    if (p / "docs" / "samples").is_dir():
        return p
    app = Path(__file__).resolve().parents[2]
    if (app / "docs" / "samples").is_dir():
        return app
    # Revenue island: docs copied to /docs/samples/...
    if Path("/docs/samples").is_dir():
        return Path("/docs")
    return p


def _menu_image_dir() -> Path:
    for base in (
        _tbcc_root() / "docs" / "samples" / "link_hub_menus" / "images",
        _tbcc_root() / "samples" / "link_hub_menus" / "images",
        Path("/docs/samples/link_hub_menus/images"),
    ):
        if base.is_dir():
            return base
    return _tbcc_root() / "docs" / "samples" / "link_hub_menus" / "images"


TBCC_ROOT = _tbcc_root()
MENU_IMAGE_DIR = _menu_image_dir()

MENU_IMAGE_FILES: dict[tuple[MenuKind, VariantId], str] = {
    ("channels", "v1"): "channels_v1_classic_orange_panel.png",
    ("channels", "v2"): "channels_v2_neon_grid.png",
    ("channels", "v3"): "channels_v3_vhs_broadcast.png",
    ("channels", "v4"): "channels_v4_uniform_rails.png",
    ("channels", "v5"): "channels_v5_network_reveal.png",
    ("channels", "v6"): "channels_v6_network_dark_panel.png",
    ("channels", "v7"): "channels_v7_network_matrix.png",
    ("ai", "v1"): "ai_v1_dark_panel.png",
    ("ai", "v2"): "ai_v2_reveal_board.png",
    ("ai", "v3"): "ai_v3_uniform_grid.png",
    ("ai", "v4"): "ai_v4_storage_matrix.png",
    ("ai", "v5"): "ai_v5_button_tree_reveal.png",
    ("ai", "v6"): "ai_v6_button_tree_dark_panel.png",
    ("ai", "v7"): "ai_v7_button_tree_matrix.png",
    ("loot", "v5"): "loot_v5_growth_reveal.png",
    ("loot", "v6"): "loot_v6_growth_dark_panel.png",
    ("loot", "v7"): "loot_v7_growth_matrix.png",
}

KIT_EMAIL_LIST_URL = "https://powercore.kit.com/"

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
    candidates = [
        MENU_IMAGE_DIR / name,
        TBCC_ROOT / "docs" / "samples" / "link_hub_menus" / "images" / name,
        Path("/docs/samples/link_hub_menus/images") / name,
        Path("/app/docs/samples/link_hub_menus/images") / name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


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


# Top lanes on Loot Room growth board (wrapped gates — outbound discovery).
LOOT_LANE_SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("ai", "AOF AI"),
    ("ass", "AOF ASS"),
    ("milf", "MILF / GILF"),
    ("taboo", "TABOO"),
    ("big_tits", "BIG TITS"),
    ("blowjob", "BLOWJOB"),
)


def _payment_bot_username() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def build_loot_inline_buttons(db: Session, *, columns: int = 2) -> list[list[dict[str, str]]]:
    """Loot Room growth board — monetization row + lane shortcuts + nav."""
    lv = lv_urls(db)
    pay = _payment_bot_username()
    rows: list[list[dict[str, str]]] = []
    monetize = [
        {"text": "🎲 Free roll", "url": "https://t.me/aof_lootgod_bot?start=loot_free"},
        {"text": "🗝 24h room key", "url": f"https://t.me/{pay}?start=loot"},
        {"text": "💎 VIP / subscribe", "url": f"https://t.me/{pay}?start=subscribe"},
    ]
    rows.append(monetize[:2])
    rows.append([monetize[2]])
    lane_btns: list[dict[str, str]] = []
    for key, label in LOOT_LANE_SHORTCUTS:
        url = _gate_href(lv, key)
        if not url:
            continue
        lane_btns.append({"text": _short_btn(label), "url": url})
    rows.extend(_chunk_buttons(lane_btns, columns=columns))
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    nav = [
        {"text": "🔗 Hub", "url": MAINHUB_RAW},
        {"text": "📌 Addlist", "url": addlist},
    ]
    rows.append(nav)
    return rows


def _interactive_menu_caption(kind: MenuKind, title: str, *, variant: VariantId = "v1") -> str:
    """Short caption under menu PNG — in-world copy only (no meta about buttons/attribution)."""
    fit = variant in BUTTON_TREE_FIT_VARIANTS
    if kind == "channels":
        sub = "lane index below · tap a pipe" if fit else "lane index below"
        return (
            f"<b>📌 AOF LINK HUB</b> · <i>{title}</i>\n"
            f"<b>AOF NETWORK · LINKS</b> · {sub}\n"
            "<i>Subscribe & enjoy.</i>"
        )
    if kind == "loot":
        invite = MAIN_GROUP_INVITE
        return (
            f"<b>🪙 AOF LOOT ROOM</b> · <i>{title}</i>\n"
            f"Keys · drops · network feed — the live hub.\n"
            f'🔞 <b>Adults only (18+).</b> NSFW content inside.\n'
            f'Invite (share): <a href="{_esc(invite)}">Loot Room</a>'
        )
    sub = "pick a lane below · buttons match art" if fit else "pick a lane below"
    return (
        f"<b>🧠 AOF AI PARTNERS</b> · <i>{title}</i>\n"
        f"<b>UNDRESS · GENERATOR</b> · {sub}\n"
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
        caption = _interactive_menu_caption("channels", menu.title, variant=variant)
    elif kind == "loot":
        menu = build_loot_menu_variant(db, variant)
        keyboard = build_loot_inline_buttons(db, columns=button_columns)
        caption = _interactive_menu_caption("loot", menu.title, variant=variant)
    else:
        menu = build_ai_menu_variant(db, variant)
        keyboard = build_ai_inline_buttons(db, columns=button_columns)
        caption = _interactive_menu_caption("ai", menu.title, variant=variant)
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


def _sales_blurb(row: Any) -> str:
    """Short sell line from copy_template or label — for menus + image prompts."""
    template = (getattr(row, "copy_template", None) or "").strip()
    for sep in ("—", " - ", " · "):
        if sep in template and "{link}" not in template.split(sep, 1)[-1]:
            tail = template.split(sep, 1)[-1].strip()
            if tail:
                return tail
    label = (row.label or "Partner").strip()
    if "(" in label:
        return label.split("(", 1)[0].strip()
    return label


def _ai_partner_rows(db: Session, *, limit: int = 18) -> list[Any]:
    rows = list_candidates(db, "links_hub_ai")[:limit]
    if not rows:
        rows = list_candidates(db, "links_hub", network_key="ai")[:limit]
    return rows


def _ai_rows(db: Session, *, limit: int = 18) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, row in enumerate(_ai_partner_rows(db, limit=limit), start=1):
        label = (row.label or "Partner").strip()
        blurb = _sales_blurb(row)
        line_html = build_sponsor_link_html(row)
        out.append((f"{i:02d}", f"{label} · {blurb} — {line_html}"))
    return out


def _ai_rows_reveal(db: Session, *, limit: int = 18) -> list[str]:
    """Reveal-board lines: linked name · blurb + dot trail."""
    lines: list[str] = []
    for i, row in enumerate(_ai_partner_rows(db, limit=limit), start=1):
        label = (row.label or "Partner").strip()
        blurb = _sales_blurb(row)
        link = build_sponsor_link_html(row, placement="links_hub_ai")
        pad = max(4, 36 - len(label) - len(blurb))
        lines.append(f"✓ {i:02d} {link} · {blurb}{'·' * pad}")
    return lines


def _two_col_plain(left: list[str], right: list[str]) -> str:
    """Pair rows for monospace 2-column button-tree layout."""
    rows: list[str] = []
    n = max(len(left), len(right))
    for i in range(n):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        rows.append(f"{l:<36}{r}")
    return "\n".join(rows)


def _split_two_col(items: list[str]) -> tuple[list[str], list[str]]:
    left = [items[i] for i in range(0, len(items), 2)]
    right = [items[i] for i in range(1, len(items), 2)]
    return left, right


def _ai_button_labels(db: Session, *, limit: int = 18) -> list[str]:
    out: list[str] = []
    for i, row in enumerate(_ai_partner_rows(db, limit=limit), start=1):
        label = (row.label or "Partner").strip()
        blurb = _sales_blurb(row)
        out.append(f"{i:02d} {label} · {blurb}")
    return out


def _support_block(lv: dict[str, str]) -> str:
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    return (
        "···· SUPPORT ····\n"
        "/loot · /subscribe · /refer\n"
        f'<a href="{_esc(addlist)}">All Channels</a> · Addlist\n'
        f'<a href="{_esc(KIT_EMAIL_LIST_URL)}">Email list</a> · drops first'
    )


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
    elif variant == "v3":
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
    elif variant == "v4":
        rails = "\n".join(
            f"—— {label} ——" for _, _, label in CHANNEL_PIPES
        )
        body = (
            f"<b>📌 AOF LINK HUB</b> · <i>UNIFORM RAILS</i>\n"
            f"<blockquote expandable>{rails}\n\n"
            f"== SUBSCRIBE &amp; ENJOY ==\n"
            f"<a href=\"{_esc(hub)}\">@aofmainhub</a> · "
            f"<a href=\"{_esc(loot)}\">Loot Room</a> · "
            f"<a href=\"{_esc(addlist)}\">Addlist</a></blockquote>"
        )
        title = "UNIFORM RAILS"
    elif variant == "v5":
        labels = [f"{num} {label}" for num, _, label in CHANNEL_PIPES]
        left, right = _split_two_col(labels)
        reveal = "\n".join(f"✓ {l}    ✓ {r}" if r else f"✓ {l}" for l, r in zip(left, right))
        body = (
            f"<b>🌐 AOF NETWORK · REVEAL BOARD</b> · <i>tap a lane</i>\n"
            f"<blockquote expandable>···· NETWORK · LINK INDEX ····\n{reveal}\n\n"
            f"···· ENTRY ····\n"
            f"<a href=\"{_esc(hub)}\">@aofmainhub</a> · "
            f"<a href=\"{_esc(loot)}\">Loot Room</a> · "
            f"<a href=\"{_esc(addlist)}\">Addlist</a></blockquote>"
        )
        title = "NETWORK REVEAL"
    elif variant == "v6":
        labels = [label for _, _, label in CHANNEL_PIPES]
        rows = "\n".join(
            f"▶ ⏺ ⏺  {labels[i]}  ◀ ◀    ▶ ⏺ ⏺  {labels[i+1]}  ◀ ◀"
            if i + 1 < len(labels)
            else f"▶ ⏺ ⏺  {labels[i]}  ◀ ◀"
            for i in range(0, len(labels), 2)
        )
        body = (
            f"<b>📌 AOF NETWORK · DARK PANEL</b> · <i>12 lanes</i>\n"
            f"<blockquote><pre>{html.escape(rows)}</pre></blockquote>\n"
            f"<a href=\"{_esc(addlist)}\">Addlist all channels</a>"
        )
        title = "NETWORK DARK PANEL"
    else:
        labels = [f"{num} {label}" for num, _, label in CHANNEL_PIPES]
        left, right = _split_two_col(labels)
        grid = _two_col_plain(
            [f">>> {x}" for x in left],
            [f">>> {x}" for x in right],
        )
        body = (
            f"<b>AOF NETWORK · CHANNEL MATRIX</b>\n"
            f"<blockquote><pre>{html.escape(grid)}</pre>\n"
            f"————| HUB |————\n"
            f"<a href=\"{_esc(hub)}\">@aofmainhub</a> · "
            f"<a href=\"{_esc(loot)}\">Loot</a> · "
            f"<a href=\"{_esc(addlist)}\">Addlist</a></blockquote>"
        )
        title = "NETWORK MATRIX"

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
        lanes = "\n".join(_ai_rows_reveal(db))
        body = (
            f"<b>✅ AOF AI REVEAL BOARD</b> · <i>tap a lane</i>\n"
            f"<b>UNDRESS · GENERATOR</b> · {header_links}\n"
            f"<blockquote expandable>{lanes}\n\n"
            f"···· MAINBOTS ····\n"
            f" Secretary · @aof_secretary_bot\n"
            f" Loot God · @aof_lootgod_bot\n"
            f" Spicy · @aof_spicybot_bot\n\n"
            f"{_support_block(lv)}</blockquote>"
        )
        title = "REVEAL BOARD"
    elif variant == "v3":
        grid = "\n".join(f"| {num} | {line} |" for num, line in ai_rows)
        body = (
            f"<b>▦ AOF AI GRID</b> · <i>UNIFORM PARTNER MATRIX</i>\n"
            f"<pre>{html.escape(grid)}</pre>\n"
            f"🔗 {header_links}"
        )
        title = "UNIFORM GRID"
    elif variant == "v4":
        matrix_lines: list[str] = []
        for i, row in enumerate(_ai_partner_rows(db), start=1):
            label = (row.label or "Partner").strip()
            blurb = _sales_blurb(row)
            matrix_lines.append(f"&gt;&gt;&gt; {i:02d} {html.escape(label)} · {html.escape(blurb)}")
        matrix = "\n".join(matrix_lines)
        body = (
            f"<b>STORAGE HUB / MAIN INTAKE</b>\n"
            f"<blockquote>"
            f"<b>AI - TOOLS</b>\n"
            f"UNDRESS · GENERATOR · LINKS\n"
            f"{matrix}\n"
            f"————|MAINBOTS|————\n"
            f" SEC @aof_secretary_bot\n"
            f" LOOT @aof_lootgod_bot\n"
            f" SPICY @aof_spicybot_bot\n"
            f"————| SUPPORT |————\n"
            f"/loot · /subscribe · /refer\n"
            f"<a href=\"{_esc(KIT_EMAIL_LIST_URL)}\">Email list</a> · drops first\n"
            f"————|| PARTNERS ||————\n"
            f"—||| Nutaku — Lust Goddess|||—"
            f"</blockquote>"
        )
        title = "STORAGE MATRIX"
    elif variant == "v5":
        labels = _ai_button_labels(db)
        left, right = _split_two_col(labels)
        reveal = "\n".join(
            f"✓ {l}    ✓ {r}" if r else f"✓ {l}" for l, r in zip(left, right)
        )
        body = (
            f"<b>✅ AOF AI · BUTTON-TREE REVEAL</b> · <i>tap a lane</i>\n"
            f"<blockquote expandable>···· UNDRESS · GENERATOR · LINKS ····\n{reveal}\n\n"
            f"{_support_block(lv)}</blockquote>"
        )
        title = "BUTTON-TREE REVEAL"
    elif variant == "v6":
        labels = _ai_button_labels(db)
        rows = "\n".join(
            f"▶ ⏺ ⏺  {labels[i]}  ◀ ◀    ▶ ⏺ ⏺  {labels[i+1]}  ◀ ◀"
            if i + 1 < len(labels)
            else f"▶ ⏺ ⏺  {labels[i]}  ◀ ◀"
            for i in range(0, len(labels), 2)
        )
        body = (
            f"<b>🧠 AOF AI · DARK PANEL</b> · <i>button-tree fit</i>\n"
            f"<blockquote><pre>{html.escape(rows)}</pre></blockquote>"
        )
        title = "BUTTON-TREE DARK PANEL"
    else:
        labels = _ai_button_labels(db)
        left, right = _split_two_col(labels)
        grid = _two_col_plain(
            [f">>> {x}" for x in left],
            [f">>> {x}" for x in right],
        )
        body = (
            f"<b>AI - TOOLS · BUTTON-TREE MATRIX</b>\n"
            f"<blockquote><pre>{html.escape(grid)}</pre>\n"
            f"————|MAINBOTS|———— @aof_secretary_bot · @aof_lootgod_bot · @aof_spicybot_bot</blockquote>"
        )
        title = "BUTTON-TREE MATRIX"

    return MenuVariant(kind="ai", variant=variant, title=title, html=body)


def build_loot_menu_variant(db: Session, variant: VariantId = "v5") -> MenuVariant:
    """Loot Room growth board HTML — v5–v7 button-tree styles."""
    lv = lv_urls(db)
    hub = MAINHUB_RAW
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    pay = _payment_bot_username()
    shortcuts = [label for _, label in LOOT_LANE_SHORTCUTS]
    entry_lines = [
        "FREE ROLL · @aof_lootgod_bot",
        f"24H KEY · @{pay} /loot",
        f"VIP · @{pay} /subscribe",
        f"HUB · {hub}",
    ]

    if variant == "v5":
        left, right = _split_two_col(shortcuts)
        reveal = "\n".join(f"✓ {l}    ✓ {r}" if r else f"✓ {l}" for l, r in zip(left, right))
        body = (
            f"<b>🪙 AOF LOOT ROOM · GROWTH BOARD</b> · <i>tap below</i>\n"
            f"<blockquote expandable>···· KEYS · DROPS · LANES ····\n"
            f"{' · '.join(entry_lines)}\n\n"
            f"{reveal}\n\n"
            f"···· NAV ····\n"
            f'<a href="{_esc(hub)}">@aofmainhub</a> · '
            f'<a href="{_esc(addlist)}">Addlist</a></blockquote>'
        )
        title = "GROWTH REVEAL"
    elif variant == "v6":
        rows = "\n".join(
            f"▶ ⏺ ⏺  {shortcuts[i]}  ◀ ◀    ▶ ⏺ ⏺  {shortcuts[i+1]}  ◀ ◀"
            if i + 1 < len(shortcuts)
            else f"▶ ⏺ ⏺  {shortcuts[i]}  ◀ ◀"
            for i in range(0, len(shortcuts), 2)
        )
        body = (
            f"<b>🪙 LOOT ROOM · DARK PANEL</b> · <i>keys &amp; lanes</i>\n"
            f"<blockquote><pre>{html.escape(rows)}</pre>\n"
            f"FREE · @aof_lootgod_bot · VIP · @{pay}</blockquote>"
        )
        title = "GROWTH DARK PANEL"
    else:
        left, right = _split_two_col(shortcuts)
        grid = _two_col_plain([f">>> {x}" for x in left], [f">>> {x}" for x in right])
        body = (
            f"<b>LOOT ROOM · GROWTH MATRIX</b>\n"
            f"<blockquote><pre>{html.escape(grid)}</pre>\n"
            f"————| ENTRY |————\n"
            f"Roll · Key · VIP · Hub</blockquote>"
        )
        title = "GROWTH MATRIX"

    return MenuVariant(kind="loot", variant=variant, title=title, html=body)


def build_all_menu_variants(db: Session) -> list[MenuVariant]:
    out: list[MenuVariant] = []
    for v in CHANNEL_VARIANTS:
        out.append(build_channel_menu_variant(db, v))
    for v in AI_VARIANTS:
        out.append(build_ai_menu_variant(db, v))
    for v in LOOT_VARIANTS:
        out.append(build_loot_menu_variant(db, v))
    return out
