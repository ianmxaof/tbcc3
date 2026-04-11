"""On-disk storage for digital-pack .zip files (dashboard upload → payment bot send_document)."""

from __future__ import annotations

import os
from pathlib import Path

# tbcc/uploads/bundles — override with TBCC_BUNDLE_DIR
def bundle_root() -> Path:
    env = (os.getenv("TBCC_BUNDLE_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # Default: repo tbcc/uploads/bundles (backend/app/services → parents → tbcc)
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent
    return (tbcc / "uploads" / "bundles").resolve()


MAX_BUNDLE_PARTS = 20  # practical cap (each part is one Telegram sendDocument)


def bundle_zip_nth_path(plan_id: int, index: int) -> Path:
    """
    index 0 -> {id}.zip, index 1 -> {id}_2.zip, index 2 -> {id}_3.zip, ...
    """
    if index < 0:
        raise ValueError("index must be >= 0")
    if index == 0:
        return bundle_root() / f"{int(plan_id)}.zip"
    return bundle_root() / f"{int(plan_id)}_{index + 1}.zip"


def bundle_zip_path(plan_id: int) -> Path:
    return bundle_zip_nth_path(plan_id, 0)


def bundle_zip2_path(plan_id: int) -> Path:
    """Second part of a split pack (same ~50 MB cap per file)."""
    return bundle_zip_nth_path(plan_id, 1)


def ensure_bundle_dir() -> Path:
    root = bundle_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_zip_magic(header: bytes) -> bool:
    return len(header) >= 4 and header[:2] == b"PK"


MAX_BUNDLE_ZIP_BYTES = 52 * 1024 * 1024  # ~50 MiB per part (Telegram Bot API sendDocument limit)
