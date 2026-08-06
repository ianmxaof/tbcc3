"""Companion UI assets — pose tiles and preset cards (PIL placeholders until operator art ships)."""

from __future__ import annotations

import re
from pathlib import Path

_UI_ROOT = Path(__file__).resolve().parent.parent / "data" / "companion_ui"
POSE_DIR = _UI_ROOT / "poses"
PRESET_DIR = _UI_ROOT / "presets"

_GRADIENTS = {
    "natural": ((40, 55, 90), (70, 120, 160)),
    "curvy": ((90, 40, 80), (180, 70, 120)),
    "bimbo": ((120, 30, 60), (255, 100, 140)),
}
_DEFAULT_POSE_GRADIENT = ((30, 30, 45), (90, 50, 110))


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s[:48] or "pose"


def _draw_tile(path: Path, *, title: str, subtitle: str, gradient: tuple[tuple[int, int, int], tuple[int, int, int]]) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 512, 512
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    (r1, g1, b1), (r2, g2, b2) = gradient
    for y in range(h):
        t = y / max(h - 1, 1)
        color = (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        draw.line([(0, y), (w, y)], fill=color)
    draw.rectangle([(0, h - 140), (w, h)], fill=(0, 0, 0, 180))
    try:
        font_lg = ImageFont.truetype("arial.ttf", 36)
        font_sm = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
    draw.text((24, h - 120), title[:28], fill=(255, 255, 255), font=font_lg)
    draw.text((24, h - 70), subtitle[:40], fill=(255, 180, 200), font=font_sm)
    draw.text((24, 24), "AOF SPICY", fill=(255, 120, 80))
    img.save(path, format="JPEG", quality=88)
    return path


def ensure_pose_tile(pose_name: str) -> Path:
    path = POSE_DIR / f"{_slug(pose_name)}.jpg"
    if not path.is_file():
        _draw_tile(
            path,
            title=pose_name,
            subtitle="Tap to select pose",
            gradient=_DEFAULT_POSE_GRADIENT,
        )
    return path


def ensure_preset_card(preset_id: str) -> Path:
    path = PRESET_DIR / f"{preset_id}.jpg"
    if not path.is_file():
        labels = {
            "natural": ("Natural", "Subtle, true-to-photo"),
            "curvy": ("Curvy", "Fuller shape · best effort"),
            "bimbo": ("Bimbo max", "Max volume + pose chain"),
        }
        title, sub = labels.get(preset_id, (preset_id, ""))
        _draw_tile(path, title=title, subtitle=sub, gradient=_GRADIENTS.get(preset_id, _DEFAULT_POSE_GRADIENT))
    return path


def list_pose_tile_paths(poses: list[str]) -> list[Path]:
    return [ensure_pose_tile(p) for p in poses[:10]]
