"""Emergency session lock storm remediation — run from tbcc/backend with PYTHONPATH=."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure backend on path when run as script
_backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend))
_tbcc_root = _backend.parent
_dotenv = _tbcc_root / ".env"
if _dotenv.is_file():
    for line in _dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        k, _, v = t.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from app.database.session import SessionLocal
from app.models.import_job import ImportJob
from app.services.focus_profile import (
    REDIS_KEY_LOCK_EVENTS,
    get_focus_state,
    restore_focus_profile,
)
from app.services.import_pipeline import TERMINAL_STATUSES, cancel_import_job
from app.utils.telethon_session import (
    import_session_stem,
    import_sessions_share_admin_file,
    poster_session_stem,
    telethon_sessions_share_file,
)


def clear_redis_locks() -> dict:
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    r = redis.from_url(url, decode_responses=True, socket_connect_timeout=3)
    keys = [
        "tbcc:lock:admin_telegram_session",
        "tbcc:lock:import_telegram_session",
        "tbcc:lock:poster_telegram_session",
        "tbcc:lock:telegram_account_mtproto",
    ]
    deleted = {}
    for k in keys:
        deleted[k] = int(r.delete(k) or 0)
    deleted[REDIS_KEY_LOCK_EVENTS] = int(r.delete(REDIS_KEY_LOCK_EVENTS) or 0)
    return deleted


def cancel_active_imports() -> list[str]:
    db = SessionLocal()
    cancelled: list[str] = []
    try:
        rows = (
            db.query(ImportJob)
            .filter(ImportJob.status.notin_(list(TERMINAL_STATUSES)))
            .order_by(ImportJob.created_at.asc())
            .all()
        )
        for job in rows:
            out = cancel_import_job(db, job.id)
            if out.get("ok"):
                cancelled.append(str(job.id))
    except Exception as e:
        print(f"  (skip cancel imports: {e})")
    finally:
        db.close()
    return cancelled


def main() -> int:
    print("=== Session config ===")
    print("  poster_session:", poster_session_stem())
    print("  import_session:", import_session_stem())
    print("  poster_shares_admin:", telethon_sessions_share_file())
    print("  import_shares_admin:", import_sessions_share_admin_file())

    print("\n=== Focus before ===")
    before = get_focus_state()
    print(json.dumps(before, indent=2))

    print("\n=== Clear Redis locks ===")
    print(clear_redis_locks())

    print("\n=== Cancel non-terminal import jobs ===")
    cancelled = cancel_active_imports()
    print(f"  cancelled {len(cancelled)} job(s)")
    for jid in cancelled[:20]:
        print("   ", jid)
    if len(cancelled) > 20:
        print(f"   ... and {len(cancelled) - 20} more")

    print("\n=== Restore focus (unpause Beat) ===")
    restored = restore_focus_profile(reason="Session lock storm remediation script")
    print(json.dumps(restored, indent=2)[:800])

    print("\n=== Focus after ===")
    after = get_focus_state()
    print(json.dumps(after, indent=2))

    if telethon_sessions_share_file() or import_sessions_share_admin_file():
        print(
            "\nWARNING: Poster or import still shares admin.session — set "
            "TBCC_POSTER_TELEGRAM_SESSION=admin_poster and TBCC_IMPORT_TELEGRAM_SESSION=admin_import in tbcc/.env"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
