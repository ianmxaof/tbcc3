"""Load tbcc/.env into os.environ (last assignment wins per key)."""

from __future__ import annotations

import os
from pathlib import Path


def load_tbcc_dotenv() -> Path | None:
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env"
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
    return env_path
