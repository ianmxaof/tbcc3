"""Opt-in Zeus co-host: secretary + macro_search on one event loop (Phase 2).

Tray-wired when ``TBCC_ZEUS_COHOST_SPIKE=1`` (secretary service runs this module).
Keep tray ``macro_search`` Off while co-hosted — same token → Telegram 409.

  set TBCC_ZEUS_COHOST_SPIKE=1
  cd tbcc/backend
  python -m bots.zeus_cohost_spike

Stop with Ctrl+C. Or enable via tray secretary after setting the env flag.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from bots import __init__ as _bots_env  # noqa: F401 — loads tbcc/.env

from bots.macro_search_bot import build_application as build_macro_search
from bots.secretary_bot import build_application as build_secretary
from bots.zeus_multi_app import run_applications_sync

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    flag = (os.getenv("TBCC_ZEUS_COHOST_SPIKE") or "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        print(
            "Refusing to start: set TBCC_ZEUS_COHOST_SPIKE=1 to run the co-host.\n"
            "Stop tray macro_search (standalone) first to avoid 409."
        )
        raise SystemExit(2)

    secretary = build_secretary()
    macro = build_macro_search()
    if secretary is None:
        print("Missing TBCC_SECRETARY_BOT_TOKEN")
        raise SystemExit(2)
    if macro is None:
        print("Missing TBCC_MACRO_SEARCH_BOT_TOKEN — co-host needs macro_search token")
        raise SystemExit(2)

    logger.info(
        "Zeus co-host: secretary + macro_search on one process "
        "(tray: keep macro_search Off)"
    )
    print("Co-host running (secretary + macro_search). Ctrl+C to stop.")
    run_applications_sync([secretary, macro])


if __name__ == "__main__":
    main()
