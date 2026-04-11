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


def promo_path_from_public_url(url: str) -> Path | None:
    """
    Resolve a dashboard/API URL like https://host/static/promo/<file> or /static/promo/<file>
    to a local file under promo_root(). Used when sending scheduled posts from uploaded promo images.
    """
    u = (url or "").strip()
    if not u or "/static/promo/" not in u:
        return None
    tail = u.split("/static/promo/", 1)[-1]
    tail = tail.split("?")[0].split("#")[0]
    if not tail or ".." in tail or "/" in tail:
        return None
    p = ensure_promo_dir() / tail
    if p.is_file():
        return p
    return None


MAX_PROMO_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB
