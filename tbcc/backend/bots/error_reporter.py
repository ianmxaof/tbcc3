"""
Shared bot error reporting — feeds the TBCC ops-alerts pipeline.

Errors are appended to .tbcc-run/error-hub.log in the hub line format
([ts] [service] [LEVEL] body) that app.services.ops_alerts tails, so every
reported bot error surfaces as a dashboard toast via GET /ops/alerts/poll
with server-side dedup. No HTTP dependency: reporting works even when the
TBCC API is the thing that's down.

Usage:
    from bots.error_reporter import report_bot_error, make_error_handler

    report_bot_error("album-composer-bot", "preview", exc)      # ad-hoc
    app.add_error_handler(make_error_handler("album-composer-bot"))
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_BODY = 600


def _hub_log_path() -> Path:
    # bots/ -> backend/ -> tbcc/
    return Path(__file__).resolve().parent.parent.parent / ".tbcc-run" / "error-hub.log"


def report_bot_error(service: str, feature: str, error: BaseException | str) -> None:
    """Append one hub-formatted line; ops_alerts classifies, dedups, and toasts it."""
    detail = re.sub(r"[\r\n]+", " | ", str(error)).strip()[:_MAX_BODY]
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{service}] [ERROR] ERROR: {feature}: {detail or 'unknown error'}"
    try:
        path = _hub_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line + "\n")
    except Exception as e:  # reporting must never take a bot down
        logger.debug("error-hub write failed: %s", e)


def make_error_handler(service: str):
    """python-telegram-bot global error handler: log, report to hub, tell the chat."""

    async def _handler(update: object, context) -> None:
        err = context.error
        try:
            from telegram.error import NetworkError

            if isinstance(err, NetworkError):
                logger.warning("%s NetworkError (usually transient): %s", service, err)
                return
        except ImportError:
            pass
        logger.error("%s unhandled error", service, exc_info=err)
        report_bot_error(service, "unhandled", err if err is not None else "unknown")
        msg = getattr(update, "effective_message", None)
        if msg is not None:
            try:
                await msg.reply_text(
                    f"⚠️ Something went wrong: {str(err)[:180]}\n"
                    "Reported to the TBCC error hub."
                )
            except Exception:
                pass

    return _handler
