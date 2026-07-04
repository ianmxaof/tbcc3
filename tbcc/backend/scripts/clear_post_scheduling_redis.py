#!/usr/bin/env python3
"""Clear TBCC post-scheduler Redis locks (tray/orchestrator post-restart hook)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND.parent / ".env")

from app.services.post_scheduler import clear_post_scheduling_redis_state  # noqa: E402


def main() -> int:
    cleared = clear_post_scheduling_redis_state()
    print(json.dumps({"ok": True, "cleared": cleared}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
