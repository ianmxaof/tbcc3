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


def bundle_zip_path(plan_id: int) -> Path:
    return bundle_root() / f"{int(plan_id)}.zip"


def ensure_bundle_dir() -> Path:
    root = bundle_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_zip_magic(header: bytes) -> bool:
    return len(header) >= 4 and header[:2] == b"PK"


MAX_BUNDLE_ZIP_BYTES = 52 * 1024 * 1024  # ~50 MiB (Telegram Bot API sendDocument limit)
