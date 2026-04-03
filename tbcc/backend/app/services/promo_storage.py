"""On-disk storage for shop promo images (dashboard upload → public /static/promo/ URL)."""

from __future__ import annotations

import os
from pathlib import Path

# tbcc/uploads/promo — override with TBCC_PROMO_DIR
def promo_root() -> Path:
    env = (os.getenv("TBCC_PROMO_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    tbcc = here.parent.parent.parent.parent
    return (tbcc / "uploads" / "promo").resolve()


def ensure_promo_dir() -> Path:
    root = promo_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


MAX_PROMO_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB
