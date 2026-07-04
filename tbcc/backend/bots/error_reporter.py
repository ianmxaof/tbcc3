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
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_BODY = 600
_conflict_log_at: dict[str, float] = {}
_retry_after_log_at: dict[str, float] = {}
_CONFLICT_LOG_COOLDOWN_S = 120.0
_RETRY_AFTER_LOG_COOLDOWN_S = 60.0


def _hub_log_path() -> Path:
    # bots/ -> backend/ -> tbcc/
    return Path(__file__).resolve().parent.parent.parent / ".tbcc-run" / "error-hub.log"


def _error_detail(error: BaseException | str) -> str:
    if isinstance(error, BaseException):
        detail = f"{type(error).__name__}: {error}"
        if error.__traceback__:
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tail = " | ".join(
                re.sub(r"[\r\n]+", " ", line).strip()
                for line in tb[-4:]
                if line.strip()
            )
            if tail:
                detail = f"{detail} | {tail}"
    else:
        detail = str(error)
    return re.sub(r"[\r\n]+", " | ", detail).strip()[:_MAX_BODY]


def report_bot_error(service: str, feature: str, error: BaseException | str) -> None:
    """Append one hub-formatted line; ops_alerts classifies, dedups, and toasts it."""
    detail = _error_detail(error)
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{service}] [ERROR] ERROR: {feature}: {detail or 'unknown error'}"
    try:
        path = _hub_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line + "\n")
    except Exception as e:  # reporting must never take a bot down
        logger.debug("error-hub write failed: %s", e)


def _conflict_script_hint(service: str) -> str:
    s = (service or "").lower()
    if "payment" in s:
        return ".\\tbcc\\scripts\\kill-payment-bot-strays.ps1"
    if "loot" in s:
        return ".\\tbcc\\scripts\\tbcc-service-control.ps1 -Action Stop -Service loot"
    if "secretary" in s:
        return ".\\tbcc\\scripts\\tbcc-service-control.ps1 -Action Stop -Service secretary"
    return ".\\tbcc\\scripts\\kill-payment-bot-strays.ps1"


def log_telegram_conflict_once(service: str, err: BaseException) -> None:
    """Log duplicate-bot Conflict with fix steps; do not spam error hub."""
    now = time.monotonic()
    last = _conflict_log_at.get(service, 0.0)
    if now - last < _CONFLICT_LOG_COOLDOWN_S:
        return
    _conflict_log_at[service] = now
    script = _conflict_script_hint(service)
    logger.error(
        "%s Telegram 409 Conflict — another instance polls the same token (%s). "
        "Run %s, then restart ONE bot process.",
        service,
        err,
        script,
    )


def _log_conflict_once(service: str, err: BaseException) -> None:
    log_telegram_conflict_once(service, err)


def log_retry_after_once(service: str, err: BaseException) -> None:
    """Telegram rate limit — transient; python-telegram-bot retries after retry_after seconds."""
    now = time.monotonic()
    last = _retry_after_log_at.get(service, 0.0)
    if now - last < _RETRY_AFTER_LOG_COOLDOWN_S:
        return
    _retry_after_log_at[service] = now
    retry_s = getattr(err, "retry_after", None)
    suffix = f" (retry in {retry_s}s)" if retry_s is not None else ""
    logger.warning(
        "%s Telegram RetryAfter flood control%s — backing off (usually transient; "
        "check for duplicate bot processes if this persists).",
        service,
        suffix,
    )


def make_error_handler(service: str):
    """python-telegram-bot global error handler: log, report to hub, tell the chat."""

    async def _handler(update: object, context) -> None:
        err = context.error
        try:
            from telegram.error import Conflict, Forbidden, NetworkError, RetryAfter

            if isinstance(err, Conflict):
                _log_conflict_once(service, err)
                return
            if isinstance(err, Forbidden):
                logger.info("%s Forbidden (blocked chat): %s", service, err)
                return
            if isinstance(err, RetryAfter):
                log_retry_after_once(service, err)
                return
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
