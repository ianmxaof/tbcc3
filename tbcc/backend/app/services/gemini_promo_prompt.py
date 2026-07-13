"""Build Gemini prompts for AOF MEGA PACKS promo images."""

from __future__ import annotations

import json
from pathlib import Path

_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "aof_promo_scene_presets.json"
_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "docs" / "samples" / "gemini_aof_promo_layout_lock.txt"
)

FORMAT_SPECS: dict[str, dict[str, str]] = {
    "single-9x16": {
        "aspect_ratio": "9:16",
        "output_block": (
            "OUTPUT: ONE image. Aspect ratio 9:16 portrait. Single complete AOF MEGA PACKS poster. No grid."
        ),
        "scene_slots": ("scene",),
    },
    "single-1x1": {
        "aspect_ratio": "1:1",
        "output_block": "OUTPUT: ONE image. Aspect ratio 1:1 square. Single complete poster.",
        "scene_slots": ("scene",),
    },
    "single-4x5": {
        "aspect_ratio": "3:4",
        "output_block": "OUTPUT: ONE image. Aspect ratio 4:5 portrait (IG feed). Single complete poster.",
        "scene_slots": ("scene",),
    },
    "grid-2x2-9x16": {
        "aspect_ratio": "9:16",
        "output_block": (
            "OUTPUT: ONE composite image. 2×2 grid of FOUR complete AOF MEGA PACKS posters.\n"
            "Each cell: 9:16 portrait. Overall composite: 9:16.\n"
            "NOT horizontal strips. NOT one panel. Thin gutter OK.\n"
            "Quadrant map:\n"
            "  TOP-LEFT | TOP-RIGHT\n"
            "  BOTTOM-LEFT | BOTTOM-RIGHT"
        ),
        "scene_slots": ("top-left", "top-right", "bottom-left", "bottom-right"),
    },
    "filmstrip-4x16x9": {
        "aspect_ratio": "9:16",
        "output_block": (
            "OUTPUT: ONE tall image. FOUR complete posters stacked top to bottom (Telegram scroll filmstrip).\n"
            "Each panel: 16:9 landscape banner with full UI. Overall composite: tall portrait strip.\n"
            "NOT 2×2 grid. Panels full width, stacked vertically."
        ),
        "scene_slots": ("panel-1", "panel-2", "panel-3", "panel-4"),
    },
}


def _load_json() -> dict:
    return json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))


def layout_lock_block() -> str:
    if _TEMPLATE_PATH.is_file():
        return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    return _default_layout_lock()


def _default_layout_lock() -> str:
    return """LAYOUT LOCK — identical in every cell/panel:
TOP: distressed white "AOF" + red brush-stroke "MEGA PACKS"
SUBHEAD: "MASSIVE COLLECTIONS • UNLIMITED POSSIBILITIES"
CENTER: large QR code with Telegram paper-plane logo inside
LEFT PILLS: NICHE LANES | FULL LENGTH | AI & DEEPFAKES | MEGA PACKS | DAILY DROPS
RIGHT PILLS: LOOT ROOM | VIP ACCESS | VOYEUR & TABOO | ONE-TAP ADDLIST | 15+ CHANNELS
BELOW QR: "DAILY DROPS · ARCHIVED LANES" / "UPDATED DAILY · 15+ CURATED LANES"
LINK BAR: red bar, paper-plane icons, exact text "t.me/aofmainhub"
BOTTOM: NO LIMITS | DIRECT DOWNLOADS | EXCLUSIVE CONTENT | SECURE & PRIVATE | ENDLESS LIBRARY
UI priority #1. Text sharp, spelled exactly."""


def resolve_preset(name: str) -> tuple[str, list[str], str]:
    data = _load_json()
    preset = (data.get("presets") or {}).get(name)
    if not preset:
        raise KeyError(f"Unknown preset: {name}")
    fmt = str(preset.get("format") or "single-9x16")
    scenes = [str(s).lower() for s in (preset.get("scenes") or [])]
    style = str(preset.get("style") or "").strip()
    return fmt, scenes, style


def scene_text(scene_id: str) -> tuple[str, str]:
    data = _load_json()
    row = (data.get("scenes") or {}).get(scene_id.lower())
    if not row:
        raise KeyError(f"Unknown scene: {scene_id}")
    label = str(row.get("label") or scene_id)
    text = str(row.get("text") or "").strip()
    return label, text


def list_presets() -> list[str]:
    data = _load_json()
    return sorted((data.get("presets") or {}).keys())


def list_scenes() -> list[str]:
    data = _load_json()
    return sorted((data.get("scenes") or {}).keys())


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
        if format_key.startswith("single"):
            scene_blocks.append(f"BACKGROUND SCENE:\n{text}")
        else:
            scene_blocks.append(f"{slot.upper()} — {label} ({sid}):\n{text}")

    style_line = style.strip() or (
        "Analog horror film still: VHS grain, scan lines, chromatic bleed, gritty photoreal, cinematic. "
        "No cartoon. No bright cheerful palette."
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
        "Generate now. Same locked UI on every panel/cell. Vary only background per slot.",
        "",
        "AVOID: wrong aspect ratio, horizontal filmstrip when 2×2 requested, wrong labels "
        "(Movies/Series/Anime/Software/Books), misspelled text, watermark, random URLs, "
        "QR without Telegram logo, missing pills, cropped link bar, duplicate identical scenes, "
        "scenes bleeding across borders.",
    ]
    if extra_avoid.strip():
        parts.append(extra_avoid.strip())

    return "\n".join(parts), str(spec["aspect_ratio"])
