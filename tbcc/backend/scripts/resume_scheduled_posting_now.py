"""One-shot: purge post queue, clear enqueue locks, re-run check_and_schedule."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend))
_dotenv = _backend.parent / ".env"
if _dotenv.is_file():
    for line in _dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        k, _, v = t.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from app.services.celery_queue_ops import celery_queue_snapshot
from app.services.post_scheduler import resume_scheduled_posting

if __name__ == "__main__":
    before = celery_queue_snapshot().get("queues", {}).get("post")
    print("before:", before)
    result = resume_scheduled_posting(purge_post_queue=True)
    after = celery_queue_snapshot().get("queues", {}).get("post")
    print("result:", result)
    print("after:", after)
