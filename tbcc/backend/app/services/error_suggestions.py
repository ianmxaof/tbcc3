"""Human-readable impact + fix hints for TBCC error-hub patterns."""

from __future__ import annotations

import re
from typing import Any

# Friendly service labels for toast copy.
_SERVICE_LABELS: dict[str, str] = {
    "tbcc-celery-post": "Celery-Post (scheduled posting)",
    "tbcc-celery": "Celery (background jobs)",
    "tbcc-beat": "Beat (scheduler timers)",
    "tbcc-backend": "API / dashboard",
    "tbcc-paymentbot": "Payment bot",
    "tbcc-lootbot": "Loot bot",
    "tbcc-companionbot": "Companion bot",
    "tbcc-scraper": "Scraper",
}

_POST_ID_RE = re.compile(r"post[_\s-]*id[=:\s]+(\d+)", re.I)
_POST_ID_ALT_RE = re.compile(r"(?:for|post)\s+(\d+)\s+failed", re.I)
_POOL_ID_RE = re.compile(r"pool[_\s-]*id[=:\s]+(\d+)", re.I)
_SCHEDULER_NAME_IN_BODY_RE = re.compile(
    r"scheduled text post\s+([^|\n]+?)(?:\s+not found|\s+failed|\s+skipped)",
    re.I,
)
_FAILED_FOR_SCHEDULER_RE = re.compile(
    r"post scheduled text failed for\s+([^:\n]+)",
    re.I,
)
_FAILED_FOR_POOL_RE = re.compile(
    r"post pool failed for\s+([^:\n]+)",
    re.I,
)
_POSTING_POOL_RE = re.compile(r"posting pool\s+(\d+)\s+to", re.I)


def _service_label(service: str) -> str:
    key = (service or "").strip().lower()
    return _SERVICE_LABELS.get(key, service or "TBCC service")


def _unique_ints(values: list[int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _lookup_scheduled_post_names(post_ids: list[int]) -> list[str]:
    ids = _unique_ints(post_ids)
    if not ids:
        return []
    try:
        from app.database.session import SessionLocal
        from app.models.scheduled_text_post import ScheduledTextPost

        db = SessionLocal()
        try:
            rows = db.query(ScheduledTextPost).filter(ScheduledTextPost.id.in_(ids)).all()
            by_id = {int(r.id): (r.name or "").strip() for r in rows}
            return [by_id[i] for i in ids if by_id.get(i)]
        finally:
            db.close()
    except Exception:
        return []


def _lookup_pool_names(pool_ids: list[int]) -> list[str]:
    ids = _unique_ints(pool_ids)
    if not ids:
        return []
    try:
        from app.database.session import SessionLocal
        from app.models.content_pool import ContentPool

        db = SessionLocal()
        try:
            rows = db.query(ContentPool).filter(ContentPool.id.in_(ids)).all()
            by_id = {int(r.id): (r.name or "").strip() for r in rows}
            return [by_id[i] for i in ids if by_id.get(i)]
        finally:
            db.close()
    except Exception:
        return []


def _lookup_inflight_post_ids() -> list[int]:
    """Post ids with an active enqueue lock (currently sending or retrying)."""
    try:
        import os

        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        ids: list[int] = []
        for key in r.scan_iter(match="tbcc:post:enqueued:*", count=50):
            try:
                ids.append(int(str(key).rsplit(":", 1)[-1]))
            except ValueError:
                continue
        return _unique_ints(ids)
    except Exception:
        return []


def resolve_hub_alert_context(code: str, body: str, service: str = "") -> dict[str, Any]:
    """Extract scheduler/pool names and ids from a hub line for user-facing alerts."""
    blob = body or ""
    post_ids = [int(m.group(1)) for m in _POST_ID_RE.finditer(blob)]
    post_ids += [int(m.group(1)) for m in _POST_ID_ALT_RE.finditer(blob)]
    post_ids = _unique_ints(post_ids)
    pool_ids = _unique_ints([int(m.group(1)) for m in _POOL_ID_RE.finditer(blob)])

    scheduler_names = _lookup_scheduled_post_names(post_ids)
    pool_names = _lookup_pool_names(pool_ids)
    m = _SCHEDULER_NAME_IN_BODY_RE.search(blob)
    if m:
        inline = (m.group(1) or "").strip()
        if inline and inline not in scheduler_names:
            scheduler_names.insert(0, inline)
    m_fail = _FAILED_FOR_SCHEDULER_RE.search(blob)
    if m_fail:
        inline = (m_fail.group(1) or "").strip()
        if inline and not inline.startswith("post_id=") and inline not in scheduler_names:
            scheduler_names.insert(0, inline)
    m_pool_fail = _FAILED_FOR_POOL_RE.search(blob)
    if m_pool_fail:
        inline = (m_pool_fail.group(1) or "").strip()
        if inline and not inline.startswith("pool_id=") and inline not in pool_names:
            pool_names.insert(0, inline)
    if not pool_ids:
        pool_ids = _unique_ints([int(m.group(1)) for m in _POSTING_POOL_RE.finditer(blob)])
        if pool_ids and not pool_names:
            pool_names = _lookup_pool_names(pool_ids)

    c = (code or "").strip().lower()
    blob_l = blob.lower()
    svc_l = (service or "").lower()
    if not post_ids and (
        c == "session_sqlite_lock"
        or "database is locked" in blob_l
        or "post scheduled text" in blob_l
    ) and "celery-post" in svc_l:
        post_ids = _lookup_inflight_post_ids()
        if post_ids:
            scheduler_names = _lookup_scheduled_post_names(post_ids)

    if not pool_ids and (
        "post pool failed" in blob_l or "post_pool" in blob_l
    ) and "celery-post" in svc_l:
        m_posting = _POSTING_POOL_RE.search(blob)
        if m_posting:
            pool_ids = _unique_ints([int(m_posting.group(1))])
            if pool_ids and not pool_names:
                pool_names = _lookup_pool_names(pool_ids)

    primary = scheduler_names[0] if scheduler_names else (pool_names[0] if pool_names else None)

    return {
        "post_ids": post_ids,
        "pool_ids": pool_ids,
        "scheduler_names": scheduler_names,
        "pool_names": pool_names,
        "primary_name": primary,
        "service": (service or "").strip(),
        "code": (code or "").strip().lower(),
    }


def _subject_title(context: dict[str, Any], *, fallback: str) -> str:
    names: list[str] = list(context.get("scheduler_names") or []) + list(context.get("pool_names") or [])
    if not names:
        return fallback
    if len(names) == 1:
        return str(names[0])
    return f"{names[0]} (+{len(names) - 1} more)"


def hub_alert_user_copy(
    code: str,
    body: str,
    service: str = "",
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """
    User-facing toast copy: impact (what broke) + action (what to do).
    No script paths, tracebacks, or log dumps.
    """
    ctx = context if context is not None else resolve_hub_alert_context(code, body, service)
    subject = _subject_title(ctx, fallback="Scheduled posting")
    names_line = ""
    schedulers = list(ctx.get("scheduler_names") or [])
    pools = list(ctx.get("pool_names") or [])
    if schedulers:
        if len(schedulers) == 1:
            names_line = f"Scheduler: {schedulers[0]}"
        else:
            names_line = "Schedulers: " + ", ".join(schedulers[:4]) + (
                f" (+{len(schedulers) - 4} more)" if len(schedulers) > 4 else ""
            )
    elif pools:
        names_line = f"Pool: {pools[0]}" if len(pools) == 1 else "Pools: " + ", ".join(pools[:3])

    t = (body or "").lower()
    svc = (service or "").strip()
    label = _service_label(svc)
    c = (code or "").strip().lower()

    if c == "session_sqlite_lock" or "database is locked" in t:
        if pools and not schedulers:
            subject = _subject_title(ctx, fallback="Content pool")
            impact = (
                f"{subject} could not post — Telegram poster session is locked by another TBCC process. "
                "Pool timers will stall until this clears."
            )
            if names_line:
                impact = f"{names_line}\n{impact}"
            return {
                "title": f"{subject} pool blocked",
                "impact": impact,
                "action": (
                    "1) Dashboard → health banner → «Trim duplicate workers»\n"
                    "2) If still stalled → restart TBCC-Celery-Post only\n"
                    "3) Avoid Telegram sends from other tabs while Celery-Post is posting"
                ),
            }
        impact = (
            f"{subject} could not send — Telegram poster session is locked by another TBCC process. "
            "Its timer will show Stalled until this clears."
        )
        if names_line:
            impact = f"{names_line}\n{impact}"
        return {
            "title": f"{subject} blocked",
            "impact": impact,
            "action": (
                "1) Dashboard → health banner → «Trim duplicate workers»\n"
                "2) If still stalled → restart TBCC-Celery-Post only\n"
                "3) Avoid editing posts in Telegram while Celery-Post is sending"
            ),
        }

    if c == "telegram_409_conflict" or ("conflict" in t and ("getupdates" in t or "409" in t)):
        bot = "Telegram bot"
        if "loot" in svc.lower():
            bot = "Loot bot"
        elif "payment" in svc.lower():
            bot = "Payment bot"
        elif "secretary" in svc.lower():
            bot = "Secretary bot"
        return {
            "title": f"Duplicate {bot}",
            "impact": (
                f"Two copies of the {bot} are polling the same token. "
                "Commands, checkouts, and webhook delivery may fail or behave randomly."
            ),
            "action": f"Stop the extra {bot} tab and keep only one instance running.",
        }

    if c == "redis_unreachable" or re.search(r"redis.*(not available|unreachable|cannot connect)", t):
        return {
            "title": "Redis unreachable",
            "impact": (
                "Redis is down. Task queues, session locks, and ops alerts will not work — "
                "scheduled posts and imports cannot enqueue."
            ),
            "action": "Start Redis from the health banner or Docker, then restart the TBCC stack.",
        }

    if c == "api_port_bind" or ("address already in use" in t and "8000" in t):
        return {
            "title": "API port conflict",
            "impact": "Something else is using port 8000 — the dashboard and API may be unreachable or unstable.",
            "action": "Use the health banner to clear orphan API workers, then restart TBCC-Backend.",
        }

    if "econnrefused" in t and "8000" in t:
        return {
            "title": "API offline",
            "impact": "Workers cannot reach the TBCC API on port 8000 — dashboard actions and webhooks may fail.",
            "action": "Start TBCC-Backend (or cold-restart the stack from start.ps1).",
        }

    if c == "worker_crash" or "process exited with code" in t:
        return {
            "title": f"{label} stopped",
            "impact": _worker_down_impact(svc, t),
            "action": f"Check the {svc or 'service'} tab in Windows Terminal; use «Fix all» in the health banner if it will not restart.",
        }

    if c == "service_traceback":
        if "post pool failed" in t or ("post_pool" in t and "failed" in t):
            impact = (
                f"{subject} failed to post its next album. "
                "The pool timer will stay Stalled until Celery-Post succeeds."
            )
            if names_line:
                impact = f"{names_line}\n{impact}"
            return {
                "title": f"{subject} pool post failed" if pools else f"{subject} send failed",
                "impact": impact,
                "action": (
                    "1) Open TBCC-Celery-Post in Windows Terminal for the exact error\n"
                    "2) Session lock → «Trim duplicate workers» in the dashboard health banner\n"
                    "3) Empty pool queue → check pool has eligible media in the dashboard"
                ),
            }
        if "database is locked" in t:
            impact = (
                f"{subject} hit a Telegram session lock while sending. "
                "The post did not go out; the scheduler timer will stay Stalled."
            )
        elif "post scheduled text" in t or "celery-post" in (service or "").lower():
            impact = (
                f"{subject} failed to send this cycle. "
                "Check TBCC-Celery-Post for the error; the scheduler will stay Stalled until it succeeds."
            )
        else:
            impact = f"{label} hit an error — related automation may not work until it recovers."
        if names_line:
            impact = f"{names_line}\n{impact}"
        return {
            "title": f"{subject} send failed" if schedulers or pools else f"{label} error",
            "impact": impact,
            "action": (
                "Open TBCC-Celery-Post in Windows Terminal for the exact error. "
                "If you see session locks, use «Trim duplicate workers» in the dashboard health banner."
            ),
        }

    if c == "telethon_session_invalid" or "wrong session id" in t:
        return {
            "title": "Telegram session invalid",
            "impact": (
                "A Telethon session file is corrupt or out of date — "
                "posting and Telegram API calls from that worker will fail."
            ),
            "action": "Re-auth the affected session (poster or admin) and restart the worker.",
        }

    if "duplicate processes" in t:
        return {
            "title": "Duplicate TBCC workers",
            "impact": (
                "Multiple processes are running for the same service — "
                "this often causes session locks and stalled schedulers."
            ),
            "action": "Use «Trim duplicate workers» or «Fix all» in the dashboard health banner.",
        }

    return {
        "title": None,
        "impact": _generic_impact(svc, body),
        "action": None,
    }


def _worker_down_impact(service: str, text: str) -> str:
    svc = (service or "").lower()
    if "celery-post" in svc:
        return (
            "TBCC-Celery-Post crashed or exited. "
            "Scheduled posts, pool auto-posts, and growth-hub syncs will not send."
        )
    if "beat" in svc:
        return "TBCC-Beat stopped — pool intervals and recurring posts will not enqueue."
    if "celery" in svc:
        return "TBCC-Celery stopped — imports, scraping, and background tasks will stall."
    if "backend" in svc:
        return "TBCC-Backend stopped — dashboard, API, and webhooks are down."
    return f"{_service_label(service)} crashed — related automation will not run until it restarts."


def _traceback_impact(service: str, text: str) -> str:
    if "database is locked" in text:
        return (
            "Telegram session is locked by another process. "
            "Scheduled posts and channel sends will fail until the lock clears."
        )
    if "post scheduled text" in text or "celery-post" in (service or "").lower():
        return (
            "A scheduled post failed to send. "
            "Timers on affected schedulers will stall until Celery-Post recovers."
        )
    if "poster" in text or "telethon" in text:
        return "Telegram posting failed — channel posts and pool timers may stall."
    return f"{_service_label(service)} hit an error — related features may not work until it recovers."


def _generic_impact(service: str, body: str) -> str:
    short = _strip_technical_noise(body)
    if short and len(short) > 20:
        return f"{_service_label(service)} reported a problem: {short[:160]}"
    return f"{_service_label(service)} reported an error — check the service tab for details."


def _strip_technical_noise(text: str) -> str:
    t = re.sub(r"[\r\n]+", " ", (text or "").strip())
    t = re.sub(r'Traceback \(most recent call last\):.*', "", t, flags=re.I)
    t = re.sub(r'File "[^"]+", line \d+, in \w+', "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def format_hub_alert_message(copy: dict[str, str | None]) -> str:
    """Single toast body from hub_alert_user_copy()."""
    impact = (copy.get("impact") or "").strip()
    action = (copy.get("action") or "").strip()
    if impact and action:
        return f"{impact}\n\nWhat to do:\n{action}"
    if impact:
        return impact
    if action:
        return f"What to do:\n{action}"
    return "TBCC reported an operational error."


def format_hub_alert_instant_line(copy: dict[str, str | None], *, title: str = "") -> str:
    """One-line summary for Secretary batch digests."""
    head = (title or copy.get("title") or "TBCC alert").strip()
    impact = (copy.get("impact") or "").strip().split("\n")[0]
    action_first = (copy.get("action") or "").strip().split("\n")[0]
    if impact and action_first:
        return f"{head} — {impact} Fix: {action_first}"
    return head if not impact else f"{head} — {impact}"


def suggest_fix_for_hub_line(body: str, service: str = "") -> str | None:
    """Plain-language fix line for Secretary digests (no script paths)."""
    ctx = resolve_hub_alert_context("", body, service)
    copy = hub_alert_user_copy("", body, service, context=ctx)
    line = format_hub_alert_instant_line(copy, title=str(copy.get("title") or ""))
    return line[:480] if line else None


def conflict_alert_user_copy(code: str, raw_message: str) -> dict[str, str]:
    """Friendlier titles + bodies for system_health conflict toasts."""
    c = (code or "").strip().lower()
    msg = (raw_message or "").strip()
    presets: dict[str, dict[str, str]] = {
        "redis_down": {
            "title": "Redis down",
            "impact": (
                "Redis is not running. Task queues, caching, and worker coordination stop — "
                "scheduled posts and imports cannot enqueue."
            ),
            "action": "Start Redis from the health banner, then restart Beat and Celery.",
        },
        "api_port_duplicate": {
            "title": "API port conflict",
            "impact": "Multiple processes are fighting for port 8000 — the dashboard may be flaky or offline.",
            "action": "Use «Fix orphan workers» in the health banner, then restart TBCC-Backend.",
        },
        "uvicorn_orphans": {
            "title": "Orphan API workers",
            "impact": "Stale API processes are still bound to port 8000 — new requests may hit the wrong worker.",
            "action": "Clear orphan workers from the health banner.",
        },
        "session_lock_storm": {
            "title": "Telegram session lock storm",
            "impact": (
                "Many session-lock errors in a short window. "
                "Scheduled posts, imports, and Telegram sends are likely stalling."
            ),
            "action": "Run «Telegram relief focus» or «Trim duplicate workers» from the health banner.",
        },
    }
    preset = presets.get(c)
    if preset:
        return {
            "title": preset["title"],
            "message": format_hub_alert_message(preset),
        }
    return {
        "title": "TBCC service conflict",
        "message": msg[:280] if msg else c,
    }
