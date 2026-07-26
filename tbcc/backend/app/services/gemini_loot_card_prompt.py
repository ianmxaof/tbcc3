"""Build Gemini prompts for AOF Loot rarity card images (tiers 1–10)."""

from __future__ import annotations

import json
from pathlib import Path

_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "aof_loot_card_presets.json"
_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "samples"
    / "gemini_loot_card_layout_lock.txt"
)

FORMAT_SPECS: dict[str, dict[str, str]] = {
    "card-1x1": {
        "aspect_ratio": "1:1",
        "output_block": (
            "OUTPUT: ONE image. Aspect ratio 1:1 square. Single complete AOF LOOT trading card. No grid."
        ),
        "scene_slots": ("scene",),
    },
    "card-4x5": {
        "aspect_ratio": "3:4",
        "output_block": (
            "OUTPUT: ONE image. Aspect ratio 4:5 portrait trading card. Single complete AOF LOOT card. No grid."
        ),
        "scene_slots": ("scene",),
    },
    "filmstrip-5-cards": {
        "aspect_ratio": "9:16",
        "output_block": (
            "OUTPUT: ONE tall image. FIVE complete AOF LOOT cards stacked top to bottom "
            "(Telegram scroll filmstrip).\n"
            "Each panel: full card UI. Overall composite: tall portrait strip.\n"
            "NOT 2×2 grid. Panels full width, stacked vertically."
        ),
        "scene_slots": ("panel-1", "panel-2", "panel-3", "panel-4", "panel-5"),
    },
}


def _load_json() -> dict:
    return json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))


def layout_lock_block() -> str:
    if _TEMPLATE_PATH.is_file():
        return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    return (
        "LAYOUT LOCK — AOF LOOT CARD: distressed AOF LOOT wordmark, TIER N + world label, "
        "explicit adult center, light ASCII HUD, bottom NAME + tagline. No QR. No t.me."
    )


def resolve_preset(name: str) -> tuple[str, list[str], str]:
    data = _load_json()
    preset = (data.get("presets") or {}).get(name)
    if not preset:
        raise KeyError(f"Unknown loot card preset: {name}")
    fmt = str(preset.get("format") or "card-1x1")
    scenes = [str(s).lower() for s in (preset.get("scenes") or [])]
    style = str(preset.get("style") or "").strip()
    return fmt, scenes, style


def scene_text(scene_id: str) -> tuple[str, str]:
    data = _load_json()
    row = (data.get("scenes") or {}).get(scene_id.lower())
    if not row:
        raise KeyError(f"Unknown loot card scene: {scene_id}")
    label = str(row.get("label") or scene_id)
    text = str(row.get("text") or "").strip()
    return label, text


def scene_meta(scene_id: str) -> dict:
    data = _load_json()
    row = (data.get("scenes") or {}).get(scene_id.lower())
    if not row:
        raise KeyError(f"Unknown loot card scene: {scene_id}")
    return dict(row)


def list_presets() -> list[str]:
    data = _load_json()
    return sorted((data.get("presets") or {}).keys())


def list_scenes() -> list[str]:
    data = _load_json()
    return sorted((data.get("scenes") or {}).keys())


def tier_scene_id(tier: int) -> str:
    t = max(1, min(10, int(tier)))
    return f"tier-{t:02d}"


def build_prompt(
    *,
    format_key: str,
    scene_ids: list[str],
    style: str = "",
    extra_avoid: str = "",
) -> tuple[str, str]:
    """Returns (prompt_text, aspect_ratio for API)."""
    spec = FORMAT_SPECS.get(format_key)
    if not spec:
        raise KeyError(f"Unknown format: {format_key}. Choose from: {', '.join(FORMAT_SPECS)}")

    slots = spec["scene_slots"]
    if len(scene_ids) != len(slots):
        raise ValueError(f"Format {format_key} needs {len(slots)} scene(s), got {len(scene_ids)}")

    scene_blocks: list[str] = []
    for slot, sid in zip(slots, scene_ids):
        label, text = scene_text(sid)
        meta = scene_meta(sid)
        name = str(meta.get("name") or "").upper()
        world = str(meta.get("world") or "")
        tier_n = meta.get("tier")
        tagline = str(meta.get("tagline") or "")
        ui = (
            f"UI TEXT (exact): TOP-RIGHT = TIER {tier_n} · {world} ; "
            f"BOTTOM NAME = {name} ; TAGLINE = {tagline}"
        )
        if format_key.startswith("card"):
            scene_blocks.append(f"BACKGROUND SCENE:\n{text}\n{ui}")
        else:
            scene_blocks.append(f"{slot.upper()} — {label} ({sid}):\n{text}\n{ui}")

    style_line = style.strip() or (
        "Photoreal trading-card UI: wet vinyl, neon accent, light ASCII HUD residue, "
        "gritty film grain, after-hours adult club atmosphere. "
        "EXPLICIT erotic center art (nudity/sex OK). No cartoon. No minors."
    )

    parts = [
        spec["output_block"],
        "",
        layout_lock_block(),
        "",
        "SCENES:",
        "\n\n".join(scene_blocks),
        "",
        f"STYLE: {style_line}",
        "",
        "Generate now. Same locked card UI. Vary only the center erotic motif + neon intensity by tier.",
        "",
        "AVOID: minors, childlike subjects, cartoon, cute/wholesome tone, "
        "QR codes, t.me links, misspelled tier names, "
        "ASCII covering important UI text, watermark, wrong aspect ratio, "
        "duplicate identical scenes, softcore-only tease when explicit sex is requested.",
    ]
    if extra_avoid.strip():
        parts.append(extra_avoid.strip())

    return "\n".join(parts), str(spec["aspect_ratio"])


def build_prompt_for_tier(tier: int, *, format_key: str = "card-1x1", style: str = "") -> tuple[str, str]:
    return build_prompt(format_key=format_key, scene_ids=[tier_scene_id(tier)], style=style)
