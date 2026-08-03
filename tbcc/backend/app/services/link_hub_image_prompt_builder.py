"""Build image prompts for link hub menus — exact button-tree order from live DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.aof_links_hub_menu_variants import (
    AI_VARIANTS,
    BUTTON_TREE_FIT_VARIANTS,
    CHANNEL_PIPES,
    CHANNEL_VARIANTS,
    LOOT_LANE_SHORTCUTS,
    LOOT_VARIANTS,
    MENU_IMAGE_ASPECT,
    MENU_IMAGE_FILES,
    MENU_IMAGE_HEIGHT_PX,
    MENU_IMAGE_WIDTH_PX,
    MenuKind,
    VariantId,
    _ai_partner_rows,
    _sales_blurb,
    _split_two_col,
    build_ai_inline_buttons,
    build_channel_inline_buttons,
    build_loot_inline_buttons,
)


def _flatten_keyboard(keyboard: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in keyboard:
        for btn in row:
            text = str(btn.get("text") or "").strip()
            if text[:2].isdigit() or (text and text[0].isdigit()):
                out.append(btn)
    return out


def _channel_rows_spec() -> list[tuple[str, str, str]]:
    return [(num, key, label) for num, key, label in CHANNEL_PIPES]


def _size_block(variant: VariantId) -> str:
    if variant in BUTTON_TREE_FIT_VARIANTS:
        return (
            f"CRITICAL LAYOUT: {MENU_IMAGE_WIDTH_PX}×{MENU_IMAGE_HEIGHT_PX}px ({MENU_IMAGE_ASPECT}) "
            "wide card — edge-to-edge full width, NO side margins, NO tall 9:16 portrait. "
            "Artwork width must match Telegram inline keyboard button-tree width exactly. "
            "Render items in a visible TWO-COLUMN grid (left col = odd rows, right col = even rows) "
            "mirroring the 2-wide inline keyboard below the image."
        )
    return (
        f"Telegram menu card for {image_file_placeholder()}. "
        "Prefer readable list; v1–v4 may use taller portrait if needed."
    )


def image_file_placeholder() -> str:
    return "menu.png"


def _two_col_item_block(lines: list[str]) -> str:
    left, right = _split_two_col(lines)
    rows: list[str] = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        rows.append(f"  L: {l}  |  R: {r}")
    return "\n".join(rows)


def build_image_prompt(
    db: Session,
    kind: MenuKind,
    variant: VariantId,
    *,
    columns: int = 2,
) -> str:
    """Gemini/image-gen prompt listing partners in exact top→bottom, left→right order."""
    image_file = MENU_IMAGE_FILES.get((kind, variant), f"{kind}_{variant}.png")
    style = _variant_style_hint(kind, variant)
    size = _size_block(variant).replace(image_file_placeholder(), image_file)

    if kind == "channels":
        items = _channel_rows_spec()
        lines = [f"{num} {label}" for num, _, label in items]
        tree_note = (
            f"Render exactly {len(lines)} channel lanes numbered 01–12 in "
            f"row-major {columns}-column order (matches inline keyboard)."
        )
        header = "AOF NETWORK · LINK INDEX"
    elif kind == "loot":
        lines = [label for _, label in LOOT_LANE_SHORTCUTS]
        tree_note = (
            f"Render exactly {len(lines)} lane shortcuts in 2-column order. "
            "Top row: FREE ROLL · 24H KEY · VIP. Loot coin / key motifs."
        )
        header = "AOF LOOT ROOM · GROWTH BOARD"
    else:
        rows = _ai_partner_rows(db)
        lines = []
        for i, row in enumerate(rows, start=1):
            label = (row.label or "Partner").strip()
            blurb = _sales_blurb(row)
            lines.append(f"{i:02d} {label} · {blurb}")
        tree_note = (
            f"Render exactly {len(lines)} AI partner rows numbered 01–{len(lines):02d} "
            f"in row-major {columns}-column order (matches inline keyboard)."
        )
        header = "UNDRESS · GENERATOR · LINKS"

    if variant in BUTTON_TREE_FIT_VARIANTS:
        item_block = _two_col_item_block(lines)
        layout_note = "Use the L/R pairs as left column | right column in the artwork."
    else:
        item_block = "\n".join(f"  - {line}" for line in lines)
        layout_note = "Single-column or decorative layout OK."

    footer = (
        "Footer sections (compact strip at bottom): MAINBOTS — Secretary, Loot God, Spicy Bot; "
        "SUPPORT — /loot /subscribe /refer, Email list powercore.kit.com; "
        "PARTNERS — Nutaku Lust Goddess."
    )

    return (
        f"{size}\n"
        f"Style: {style}\n"
        f"Header: {header}\n"
        f"{tree_note}\n"
        f"{layout_note}\n"
        f"Each row: number, name, short sell blurb — readable at phone scale:\n"
        f"{item_block}\n"
        f"{footer}\n"
        "No explicit nudity. Abstract app icons only. No gibberish — labels must match list exactly."
    )


def _variant_style_hint(kind: MenuKind, variant: VariantId) -> str:
    hints: dict[tuple[MenuKind, VariantId], str] = {
        ("channels", "v1"): "Dark charcoal, burnt-orange monospace box frame, soft glow.",
        ("channels", "v2"): "Cyberpunk neon grid, cyan/magenta tiles, holographic UI.",
        ("channels", "v3"): "Retro VHS TV guide, scanlines, cream/amber CRT text.",
        ("channels", "v4"): "Uniform centered rails — each lane as —— LABEL —— amber on dark panel.",
        ("channels", "v5"): "Reveal board: orange checkmarks, dot rails, 2-col grid, full bubble width.",
        ("channels", "v6"): "Dark panel mechanical ▶ ⏺ ⏺ symmetry, 2-col rows, amber on charcoal.",
        ("channels", "v7"): "Matrix green >>> arrows, 2-col channel grid, digital rain header strip.",
        ("ai", "v1"): "Dark noir orange panel, box-drawing frame, mechanical symmetry.",
        ("ai", "v2"): "Reveal board: green checkmarks, dot trails, purple gradient cards.",
        ("ai", "v3"): "Gold grid matrix, 3-column catalog, architectural alignment.",
        ("ai", "v4"): "Matrix green STORAGE HUB style, >>> arrows, digital rain behind AI-TOOLS header.",
        ("ai", "v5"): "Orange reveal board, ✓ checkmarks, 2-col partner grid, full keyboard width.",
        ("ai", "v6"): "Dark panel ▶ ◀ symmetry, 2-col affiliate rows, burnt orange monospace.",
        ("ai", "v7"): "Green matrix >>> 2-col grid, compact STORAGE HUB header, edge-to-edge.",
        ("loot", "v5"): "Loot Room reveal board: gold coin accents, orange checkmarks, 2-col lane grid.",
        ("loot", "v6"): "Loot Room dark panel ▶ ◀ symmetry, amber keys and dice motifs.",
        ("loot", "v7"): "Loot matrix green >>> 2-col shortcuts, LOOT ROOM header strip.",
    }
    return hints.get((kind, variant), "Dark mode, high contrast, mechanical emoji accents.")


def export_all_prompts(db: Session, *, columns: int = 2) -> dict[str, Any]:
    prompts: dict[str, str] = {}
    for kind in ("channels", "ai", "loot"):
        variants = CHANNEL_VARIANTS if kind == "channels" else (AI_VARIANTS if kind == "ai" else LOOT_VARIANTS)
        for variant in variants:
            key = f"{kind}_{variant}"
            prompts[key] = build_image_prompt(db, kind, variant, columns=columns)  # type: ignore[arg-type]
    return {
        "columns": columns,
        "image_spec": {
            "button_tree_fit_variants": list(BUTTON_TREE_FIT_VARIANTS),
            "width_px": MENU_IMAGE_WIDTH_PX,
            "height_px": MENU_IMAGE_HEIGHT_PX,
            "aspect": MENU_IMAGE_ASPECT,
        },
        "prompts": prompts,
        "button_tree": {
            "channels": [
                {"num": n, "key": k, "label": lbl}
                for n, k, lbl in _channel_rows_spec()
            ],
            "ai": [
                {
                    "num": f"{i:02d}",
                    "label": (r.label or "").strip(),
                    "blurb": _sales_blurb(r),
                }
                for i, r in enumerate(_ai_partner_rows(db), start=1)
            ],
        },
    }
