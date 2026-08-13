"""Companion UI assets — pose tiles and preset cards."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.services.companion_poses import POSE_SOURCE_FILES

_UI_ROOT = Path(__file__).resolve().parent.parent / "data" / "companion_ui"
POSE_DIR = _UI_ROOT / "poses"
PRESET_DIR = _UI_ROOT / "presets"
# Telegram albums: 10 square tiles → native 2+2+3+3 grid; overflow in a second album.
POSE_TELEGRAM_TILE_PX = 512
POSE_ALBUM_PRIMARY_COUNT = 10
POSE_KEYBOARD_COLUMNS = 3
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


def pose_tile_path(pose_name: str) -> Path:
    return POSE_DIR / f"{_slug(pose_name)}.jpg"


def pose_tile_available(pose_name: str) -> bool:
    return pose_tile_path(pose_name).is_file()


def import_operator_pose_tile(pose_name: str, source_dir: Path) -> Path | None:
    """Copy operator composite into poses/ if source file exists."""
    src_name = POSE_SOURCE_FILES.get(pose_name)
    if not src_name:
        return None
    src = source_dir / src_name
    if not src.is_file():
        return None
    dest = pose_tile_path(pose_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def ensure_pose_tile(pose_name: str) -> Path:
    path = pose_tile_path(pose_name)
    if path.is_file():
        return path
    _draw_tile(
        path,
        title=pose_name,
        subtitle="Tap to select pose",
        gradient=_DEFAULT_POSE_GRADIENT,
    )
    return path


def list_pose_tile_paths(poses: list[str], *, require_real: bool = True) -> list[Path]:
    out: list[Path] = []
    for pose in poses:
        if require_real and pose_tile_available(pose):
            out.append(pose_tile_path(pose))
        elif not require_real:
            out.append(ensure_pose_tile(pose))
    return out


def chunk_pose_albums(poses: list[str], *, columns: int = 3) -> list[list[str]]:
    """Group poses for media albums — multiples of `columns` keep a uniform grid width."""
    if not poses:
        return []
    size = max(1, int(columns))
    chunks: list[list[str]] = []
    for i in range(0, len(poses), size):
        chunks.append(poses[i : i + size])
    return chunks


def _square_thumbnail(path: Path, size: int):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side))
    return im.resize((size, size), Image.Resampling.LANCZOS)


def _tile_overlay_fonts():
    from PIL import ImageFont

    try:
        return ImageFont.truetype("arial.ttf", 36), ImageFont.truetype("arial.ttf", 22)
    except OSError:
        default = ImageFont.load_default()
        return default, default


def labeled_pose_tile_bytes(pose_name: str) -> bytes | None:
    """512×512 pose preview with title + subtitle baked in (first-iteration style)."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    path = pose_tile_path(pose_name)
    if not path.is_file():
        path = ensure_pose_tile(pose_name)

    size = POSE_TELEGRAM_TILE_PX
    img = _square_thumbnail(path, size).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([(0, size - 140), (size, size)], fill=(0, 0, 0, 180))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    font_lg, font_sm = _tile_overlay_fonts()
    draw.text((24, size - 120), pose_name[:28], fill=(255, 255, 255), font=font_lg)
    draw.text((24, size - 70), "Tap to select pose", fill=(255, 180, 200), font=font_sm)
    draw.text((24, 24), "AOF SPICY", fill=(255, 120, 80))
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def split_pose_album_batches(poses: list[str], *, primary: int = POSE_ALBUM_PRIMARY_COUNT) -> list[list[str]]:
    """First batch fills the 2+2+3+3 album; remainder goes in a follow-up album."""
    if not poses:
        return []
    primary = max(1, int(primary))
    if len(poses) <= primary:
        return [poses]
    return [poses[:primary], poses[primary:]]


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
