"""Build Gemini border animation prompts from template + variant catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.services.loot_tier_card_assets import loot_tier_card_dir

BORDER_PROMPTS_DIR = loot_tier_card_dir() / "border-prompts"
TEMPLATE_PATH = BORDER_PROMPTS_DIR / "GEMINI_BORDER_ANIMATION_TEMPLATE.md"
VARIANTS_PATH = BORDER_PROMPTS_DIR / "GEMINI_BORDER_25_VARIANTS.md"


@dataclass(frozen=True)
class BorderVariant:
    number: int
    name: str
    stem: str
    top_left: str
    top_right: str
    bottom: str
    chrome: str
    style: str
    open_anim: str
    stasis: str


def _strip_md_cell(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def load_border_template() -> str:
    raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    m = re.search(r"```\n([\s\S]*?)\n```", raw)
    if not m:
        raise ValueError(f"No fenced prompt block in {TEMPLATE_PATH}")
    return m.group(1).strip()


def parse_border_variants() -> list[BorderVariant]:
    text = VARIANTS_PATH.read_text(encoding="utf-8")
    chunks = re.split(r"\n##\s+", text)
    out: list[BorderVariant] = []
    for chunk in chunks[1:]:
        header = chunk.split("\n", 1)[0]
        hm = re.match(r"(\d+)\s+—\s+(.+)", header.strip())
        if not hm:
            continue
        num = int(hm.group(1))
        name = hm.group(2).strip()
        stem_m = re.search(r"\*\*Stem:\*\*\s*`([^`]+)`", chunk)
        if not stem_m:
            continue
        stem = stem_m.group(1).strip()

        def _slot(label: str) -> str:
            pat = rf"\|\s*{re.escape(label)}\s*\|\s*([^|]+)\|"
            m = re.search(pat, chunk, re.I)
            return _strip_md_cell(m.group(1)) if m else ""

        out.append(
            BorderVariant(
                number=num,
                name=name,
                stem=stem,
                top_left=_slot("Top-left"),
                top_right=_slot("Top-right"),
                bottom=_slot("Bottom"),
                chrome=_slot("Chrome"),
                style=_slot("Style"),
                open_anim=_slot("Open"),
                stasis=_slot("Stasis"),
            )
        )
    out.sort(key=lambda v: v.number)
    return out


def resolve_border_variant(key: str) -> BorderVariant:
    key = (key or "").strip().lower()
    variants = parse_border_variants()
    if not key:
        raise ValueError("variant key required (stem, number, or name substring)")
    if key.isdigit():
        for v in variants:
            if v.number == int(key):
                return v
    for v in variants:
        if v.stem.lower() == key:
            return v
    for v in variants:
        if key in v.name.lower() or key in v.stem.lower():
            return v
    raise ValueError(f"Unknown border variant: {key}")


def build_border_animation_prompt(variant: BorderVariant | str) -> str:
    v = resolve_border_variant(variant) if isinstance(variant, str) else variant
    tpl = load_border_template()
    replacements = {
        "[VARIANT NAME]": v.name,
        "[VARIANT: top-left plate description]": v.top_left,
        "[VARIANT: top-right plate description]": v.top_right,
        "[VARIANT: bottom nameplate description]": v.bottom,
        "[VARIANT: frame material + accent colors + aesthetic keywords]": v.chrome,
        "[VARIANT: style paragraph — materials, mood, lighting, TCG energy]": v.style,
        "[VARIANT: opening mechanic — what blocks the center at frame 0]": v.open_anim,
        "[VARIANT: how the center opens — smooth ease-out, vault precision]": v.open_anim,
        "[VARIANT: primary pulse/glow — ~1.5s period, on chrome only]": v.stasis,
        "[VARIANT: sparkle behavior — 2–3 blinks per loop, ON rivets/corners only]": v.stasis,
        "[VARIANT: optional subtle sweep — metal surface only, low amplitude]": "optional subtle specular sweep on metal only",
    }
    out = tpl
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def border_preview_still_prompt(variant: BorderVariant | str) -> str:
    """Single-frame still for QA before video export in Gemini UI."""
    v = resolve_border_variant(variant) if isinstance(variant, str) else variant
    return (
        f"AOF LOOT GOD card border chrome ONLY — variant {v.name} ({v.stem}). "
        f"1024x1024 square, full-bleed metal frame touching all canvas edges. "
        f"Center window: flat solid magenta #FF00FF empty hole (~68% width). "
        f"Plates: top-left {v.top_left}; top-right {v.top_right}; bottom {v.bottom}. "
        f"Chrome: {v.chrome}. Style: {v.style}. "
        f"No text, no logos, no people, no art in center. "
        f"Every pixel outside chrome is uniform #FF00FF matte. Photoreal 3D TCG UI asset."
    )
