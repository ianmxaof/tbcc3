"""Resolve AOF logo images for Mega pack root promo uploads."""

from __future__ import annotations

import os
from pathlib import Path

_LOGO_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})


def aof_logos_dir_from_env() -> Path:
    raw = (
        os.getenv("TBCC_AOF_LOGOS_DIR")
        or r"C:\Users\ianmp\Documents\AOF RESOURCES (ZIPS)\AOF LOGOS"
    ).strip()
    return Path(raw)


def all_logo_files(*, root: Path | None = None) -> list[Path]:
    """All logo images under TBCC_AOF_LOGOS_DIR (recursive)."""
    base = root or aof_logos_dir_from_env()
    if not base.is_dir():
        return []
    out: list[Path] = []
    for p in base.rglob("*"):
        if is_logo_file(p):
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def local_logo_files() -> list[Path]:
    """Logos in the logos root only (non-recursive). Prefer all_logo_files() for carousels."""
    root = aof_logos_dir_from_env()
    if not root.is_dir():
        return []
    direct = sorted(p for p in root.iterdir() if is_logo_file(p))
    if direct:
        return direct
    return all_logo_files(root=root)


def aof_logos_mega_folder_from_env() -> str:
    return (os.getenv("TBCC_AOF_LOGOS_MEGA_FOLDER") or "AOF LOGOS").strip()


def is_logo_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _LOGO_EXTS


def pick_logo_for_pack(logos: list, pack_name: str):
    """Stable per-pack logo rotation."""
    if not logos:
        return None
    idx = abs(hash(pack_name)) % len(logos)
    return logos[idx]


def logo_keep_filenames(logos: list) -> set[str]:
    names: set[str] = set()
    for item in logos:
        if isinstance(item, Path):
            names.add(item.name.lower())
        elif isinstance(item, str):
            names.add(Path(item).name.lower())
    return names
