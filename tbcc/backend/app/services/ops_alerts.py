"""
TBCC operational alerts — breaking service conflicts and irregular error-hub lines.

Poll via GET /ops/alerts/poll; clients show toast / OS notifications with server-side dedup.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.error_suggestions import (
    conflict_alert_user_copy,
    format_hub_alert_message,
    hub_alert_user_copy,
    resolve_hub_alert_context,
    suggest_fix_for_hub_line,
)

logger = logging.getLogger(__name__)

REDIS_KEY_HUB_OFFSET = "tbcc:alerts:hub_offset"
REDIS_KEY_CONFLICT_CODES = "tbcc:alerts:conflict_codes"
REDIS_KEY_COMPANION_GATE = "tbcc:alerts:companion_gate_admin_ok"
REDIS_KEY_INBOX_TOAST_CURSOR = "tbcc:alerts:inbox_toast:last_ts"
REDIS_KEY_CLIENT_TOAST_LAST = "tbcc:alerts:client_toast_last_ts"
REDIS_KEY_CLIENT_TOAST_WINDOW = "tbcc:alerts:client_toast_window"
REDIS_KEY_MAX_TOASTS_PER_2MIN = "tbcc:alerts:max_toasts_per_2min"
REDIS_DEDUP_PREFIX = "tbcc:alerts:dedup:"
TOAST_WINDOW_SECONDS = 120

# Confirmed breaking / cross-service conflicts (critical only).
BREAKING_CONFLICT_CODES: frozenset[str] = frozenset(
    {
        "redis_down",
        "api_port_duplicate",
        "uvicorn_orphans",
        "session_lock_storm",
    }
)

# Extra high-signal hub patterns (always alert even if generic ERROR matcher missed).
HIGH_SIGNAL_HUB: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"terminated by other getUpdates|Conflict:.*getUpdates", re.I), "telegram_409_conflict", "critical", "Duplicate Telegram bot"),
    (re.compile(r"database is locked", re.I), "session_sqlite_lock", "critical", "Scheduled posting blocked"),
    (re.compile(r"wrong session id|session id", re.I), "telethon_session_invalid", "critical", "Telethon session invalid"),
    (re.compile(r"address already in use.*8000|:8000.*already in use", re.I), "api_port_bind", "critical", "API port 8000 conflict"),
    (re.compile(r"child process died|worker exited|process exited with code [1-9]", re.I), "worker_crash", "critical", "TBCC worker crashed"),
    (re.compile(r"redis.*not available|redis.*unreachable|cannot connect to redis", re.I), "redis_unreachable", "critical", "Redis unreachable"),
    (re.compile(r"connection refused.*(8001|8002|6379|5432)", re.I), "sidecar_down", "warning", "Sidecar/infra connection refused"),
]

HUB_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.I)
    for p in (
        r"Traceback \(most recent call last\)",
        r"\s-\s(ERROR|CRITICAL|FATAL)\s-",
        r":\s*(ERROR|CRITICAL|FATAL)\b",
        r"\[(ERROR|CRITICAL|FATAL)\]",
        r"\b(FATAL|ERROR)\s*:",
        r"npm ERR!",
        r"Failed to compile",
        r"UnhandledPromiseRejection",
        r"ECONNREFUSED|EADDRINUSE",
        r"WinError \d+",
        r"ModuleNotFoundError",
        r"OperationalError",
        r"sqlalchemy\.exc\.",
        r"Process exited with code [1-9]\d*",
        r"Worker exited",
        r"500 Internal Server Error",
        r"Connection refused(?!.*retry\s+\d+/\d+)",
        r"Address already in use",
        r"Permission denied",
    )
]

HUB_BENIGN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.I)
    for p in (
        r"^\[notice\]",
        r"new release of pip is available",
        r"pkg_resources is deprecated",
        r"WARNING:tensorflow:",
        r"oneDNN custom operations are on",
        r"QuickGELU mismatch",
        r"unauthenticated requests to the HF Hub",
        r"actively refused it\),\s*retry\s+\d+/\d+",
        r"failed \(.*\),\s*retry\s+\d+/\d+\s+in\s+\d+s",
        r"^\s*I\d{4}\s",
        r"\s-\sWARNING\s-",
        # Recurring / low-signal — log only, no toast or instant DM
        r"waiting for the Telegram poster session",
        r"refresh_post_views",
        r"http proxy error:.*ECONNREFUSED 127\.0\.0\.1:8000",
        r"bypass_vip_client request error.*10054",
        r"Could not find the input entity for PeerUser\(user_id=999888777\)",
        r"ConnectionResetError.*10054",
        r"_ProactorBasePipeTransport\._call_connection_lost",
        r"Task was destroyed but it is pending",
        r"cannot reuse already awaited coroutine",
        # Expected while TBCC-Backend is restarting (grace window also suppresses toasts)
        r"ECONNREFUSED.*127\.0\.0\.1:8000",
        r"Connection refused.*127\.0\.0\.1:8000",
        r"Failed to establish a new connection.*8000",
        r"Max retries exceeded.*8000",
        r"ConnectError.*8000",
        r"TBCC API not reachable",
        r"API not reachable",
        r"Public URL looks offline",
        # TBCC-Errors monitor re-ingesting nested hub lines (run-tbcc-service guard; belt-and-suspenders)
        r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] \[TBCC-Errors\] \[ERROR\]",
        r"\[TBCC-Errors\] \[ERROR\].*\[TBCC-Errors\] \[ERROR\]",
    )
]

HUB_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] \[(?P<service>[^\]]+)\] \[(?P<level>[^\]]+)\] (?P<body>.*)$"
)


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def alerts_enabled() -> bool:
    return (os.getenv("TBCC_ALERTS_ENABLED") or "1").strip().lower() in ("1", "true", "yes", "on")


def hub_scan_enabled() -> bool:
    return (os.getenv("TBCC_ALERTS_HUB_SCAN") or "0").strip().lower() in ("1", "true", "yes", "on")


def hub_toast_enabled() -> bool:
    """Desktop/dashboard toasts for error-hub lines (inbox/Secretary still receive events when hub_scan=1)."""
    return (os.getenv("TBCC_ALERTS_HUB_TOAST") or "0").strip().lower() in ("1", "true", "yes", "on")


def ops_toast_enabled() -> bool:
    """Toast critical ops inbox events (error hub, worker crashes). Off by default — use Secretary /ops."""
    return (os.getenv("TBCC_ALERTS_OPS_TOAST") or "0").strip().lower() in ("1", "true", "yes", "on")


def hub_critical_only() -> bool:
    """When hub scan is on, only toast/push critical-severity hub lines (skip generic warnings)."""
    return (os.getenv("TBCC_ALERTS_HUB_CRITICAL_ONLY") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def payment_toast_enabled() -> bool:
    return (os.getenv("TBCC_ALERTS_PAYMENT_TOAST") or "1").strip().lower() in ("1", "true", "yes", "on")


def alert_dedup_ttl_s() -> int:
    try:
        return max(300, int(os.getenv("TBCC_ALERTS_DEDUP_TTL_S") or "1800"))
    except ValueError:
        return 1800


def hub_max_per_poll() -> int:
    try:
        return max(0, min(5, int(os.getenv("TBCC_ALERTS_HUB_MAX_PER_POLL") or "1")))
    except ValueError:
        return 1


def hub_catchup_tail() -> int:
    try:
        return max(1, min(20, int(os.getenv("TBCC_ALERTS_HUB_CATCHUP_TAIL") or "3")))
    except ValueError:
        return 3


def client_toast_min_interval_s() -> int:
    try:
        return max(30, int(os.getenv("TBCC_ALERTS_CLIENT_MIN_INTERVAL_S") or "120"))
    except ValueError:
        return 120


def max_client_toasts_per_2min() -> int:
    """Runtime cap on non-payment desktop toasts per 2-minute sliding window."""
    try:
        r = _redis_client()
        raw = r.get(REDIS_KEY_MAX_TOASTS_PER_2MIN)
        if raw is not None and str(raw).strip() != "":
            return max(0, min(10, int(raw)))
    except Exception:
        pass
    try:
        return max(0, min(10, int(os.getenv("TBCC_ALERTS_MAX_TOASTS_PER_2MIN") or "1")))
    except ValueError:
        return 1


def set_max_client_toasts_per_2min(n: int) -> int:
    n = max(0, min(10, int(n)))
    try:
        _redis_client().set(REDIS_KEY_MAX_TOASTS_PER_2MIN, str(n))
    except Exception:
        pass
    return n


def adjust_max_client_toasts_per_2min(delta: int) -> int:
    return set_max_client_toasts_per_2min(max_client_toasts_per_2min() + int(delta))


def get_alert_toast_settings() -> dict[str, Any]:
    cap = max_client_toasts_per_2min()
    return {
        "max_toasts_per_2min": cap,
        "window_seconds": TOAST_WINDOW_SECONDS,
        "hub_scan": hub_scan_enabled(),
        "hub_toast": hub_toast_enabled(),
        "ops_toast": ops_toast_enabled(),
        "payment_toast": payment_toast_enabled(),
        "payment_toasts_exempt": True,
        "effective_interval_seconds": (
            None if cap <= 0 else max(30, TOAST_WINDOW_SECONDS // cap) if cap > 0 else None
        ),
    }


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _dedup_seen(alert_id: str) -> bool:
    """Return True if this alert was already emitted recently."""
    try:
        r = _redis_client()
        key = REDIS_DEDUP_PREFIX + alert_id
        if r.exists(key):
            return True
        r.set(key, "1", ex=alert_dedup_ttl_s())
        return False
    except Exception:
        return True


def _error_hub_path() -> Path:
    return _tbcc_root() / ".tbcc-run" / "error-hub.log"


def _is_benign_hub_line(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 4:
        return True
    for pat in HUB_BENIGN_PATTERNS:
        if pat.search(t):
            return True
    if re.match(r"^(INFO|DEBUG)\s", t, re.I):
        return True
    return False


def _is_irregular_hub_line(text: str) -> bool:
    t = (text or "").strip()
    if not t or _is_benign_hub_line(t):
        return False
    for pat, _code, _sev, _title in HIGH_SIGNAL_HUB:
        if pat.search(t):
            return True
    for pat in HUB_ERROR_PATTERNS:
        if pat.search(t):
            return True
    if re.search(r"^\s*error[:\s]", t, re.I) or re.search(r"exception in", t, re.I):
        return True
    return False


def _classify_hub_line(text: str) -> tuple[str, str, str] | None:
    """Return (code, severity, title) or None."""
    t = (text or "").strip()
    if not _is_irregular_hub_line(t):
        return None
    for pat, code, severity, title in HIGH_SIGNAL_HUB:
        if pat.search(t):
            return code, severity, title
    return "error_hub", "warning", "TBCC error hub"


def _service_display_name(service: str) -> str:
    labels = {
        "TBCC-Celery-Post": "Scheduled posting",
        "TBCC-Celery": "Background jobs",
        "TBCC-Beat": "Scheduler",
        "TBCC-Backend": "API",
    }
    return labels.get(service, service or "TBCC")


def _normalize_hub_body(body: str) -> str:
    one = re.sub(r"[\r\n]+", " ", (body or "").strip())
    return one[:200]


def _hub_fingerprint(service: str, body: str) -> str:
    b = (body or "").lower()
    if "getupdates" in b and "conflict" in b:
        raw = "hub:global:telegram_409_conflict"
    elif "traceback (most recent call last)" in b:
        raw = f"hub:{service}:traceback"
    elif "nsfw classify" in b and "actively refused" in b:
        raw = f"hub:{service}:nsfw_sidecar_down"
    elif "httpx" in b and ("network" in b or "connect" in b):
        raw = f"hub:{service}:telegram_network"
    elif "unhandled" in b or "emoji_pack" in b or "on_media" in b:
        raw = f"hub:{service}:bot_unhandled"
    else:
        norm = _normalize_hub_body(body).lower()
        raw = f"hub:{service}:{norm}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]


def _parse_hub_alert(line: str) -> dict[str, Any] | None:
    m = HUB_LINE_RE.match(line.strip())
    if m:
        body = m.group("body") or ""
        service = m.group("service") or "unknown"
        level = (m.group("level") or "").upper()
    else:
        body = line.strip()
        service = "unknown"
        level = ""

    classified = _classify_hub_line(body if body else line)
    if not classified:
        return None
    code, severity, title = classified
    if code == "session_sqlite_lock":
        try:
            from app.services.focus_profile import count_active_import_jobs

            if count_active_import_jobs() > 0:
                return None
        except Exception:
            pass
    blob = body or line
    if code == "telegram_409_conflict":
        if "payment" in service.lower():
            title = "Duplicate PaymentBot"
        elif "loot" in service.lower():
            title = "Duplicate LootBot"
        else:
            title = "Duplicate Telegram bot"
    elif service and service != "unknown" and title == "TBCC error hub":
        title = f"{service} error"
    if "traceback (most recent call last)" in blob.lower():
        if "database is locked" in blob.lower():
            return None
        code = "service_traceback"
        title = f"{service} error"
        severity = "critical" if hub_critical_only() else "warning"
    elif "nsfw classify" in blob.lower() and "actively refused" in blob.lower():
        return None
    if level in ("ERROR", "CRITICAL", "FATAL") and severity == "warning":
        if "traceback" not in blob.lower():
            severity = "critical"

    fp = _hub_fingerprint(service, blob)
    context = resolve_hub_alert_context(code, blob, service)
    user_copy = hub_alert_user_copy(code, blob, service, context=context)
    if user_copy.get("title"):
        title = str(user_copy["title"])
    display = format_hub_alert_message(user_copy)
    if not (user_copy.get("impact") or user_copy.get("action")):
        msg = _normalize_hub_body(body or line)
        if len(msg) > 220:
            msg = msg[:220] + "…"
        display = f"{_service_display_name(service)}: {msg}"
    fix = suggest_fix_for_hub_line(blob, service)
    return {
        "id": f"hub:{fp}",
        "kind": "error_hub",
        "code": code,
        "severity": severity,
        "title": title,
        "message": display,
        "fix_hint": fix,
        "service": service,
        "scheduler_names": list(context.get("scheduler_names") or []),
        "post_ids": list(context.get("post_ids") or []),
        "timestamp": m.group("ts") if m else datetime.now(timezone.utc).isoformat(),
    }


def _is_payment_priority_alert(alert: dict[str, Any]) -> bool:
    code = str(alert.get("code") or "").lower()
    priority = str(alert.get("priority") or "").lower()
    return code in ("payment", "invoice", "loot") or priority == "payment"


def _client_toast_rate_ok(*, bypass: bool = False) -> bool:
    if bypass:
        return True
    cap = max_client_toasts_per_2min()
    if cap <= 0:
        return False
    now = time.time()
    try:
        r = _redis_client()
        key = REDIS_KEY_CLIENT_TOAST_WINDOW
        r.zremrangebyscore(key, 0, now - TOAST_WINDOW_SECONDS)
        if int(r.zcard(key)) >= cap:
            return False
        r.zadd(key, {f"{now:.6f}": now})
        r.expire(key, TOAST_WINDOW_SECONDS + 60)
        return True
    except Exception:
        try:
            r = _redis_client()
            last = float(r.get(REDIS_KEY_CLIENT_TOAST_LAST) or "0")
            interval = max(30, TOAST_WINDOW_SECONDS // max(1, cap))
            if now - last < interval:
                return False
            r.set(REDIS_KEY_CLIENT_TOAST_LAST, str(now), ex=interval * 3)
            return True
        except Exception:
            return True


def _collapse_hub_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backlog catch-up: keep tail only; collapse into one digest when multiple."""
    if not alerts:
        return []
    max_poll = hub_max_per_poll()
    if max_poll <= 0:
        return []
    tail_n = hub_catchup_tail()
    trimmed = alerts[-tail_n:] if len(alerts) > tail_n else list(alerts)
    if len(trimmed) == 1:
        return trimmed[:max_poll]
    sev_rank = {"info": 0, "warning": 1, "critical": 2}
    top_sev = max((str(a.get("severity") or "warning") for a in trimmed), key=lambda s: sev_rank.get(s, 1))
    lines: list[str] = []
    for a in trimmed[-3:]:
        title = str(a.get("title") or "Error").strip()
        msg = str(a.get("message") or "").strip().split("\n")[0][:140]
        lines.append(f"• {title}" + (f" — {msg}" if msg else ""))
    skipped = len(alerts) - len(trimmed)
    head = f"{len(alerts)} error-hub line(s)"
    if skipped > 0:
        head += f" (showing last {len(trimmed)})"
    digest = {
        "id": f"hub:digest:{hashlib.sha256('|'.join(str(a.get('id') or '') for a in trimmed).encode()).hexdigest()[:16]}",
        "kind": "error_hub",
        "code": "error_hub_digest",
        "severity": top_sev,
        "title": f"Error hub · {len(alerts)} new",
        "message": head + ":\n" + "\n".join(lines) + "\n\nOpen TBCC-Errors tab or Secretary /ops for full log.",
        "timestamp": _now_iso(),
    }
    if not _dedup_seen(digest["id"]):
        return [digest][:max_poll]
    return []


def _apply_client_poll_limits(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Never flood clients: payment toasts always; at most one ops/hub toast per poll + global rate limit."""
    if not alerts:
        return []
    payment = [a for a in alerts if _is_payment_priority_alert(a)]
    rest = [a for a in alerts if a not in payment]

    hub = [a for a in rest if str(a.get("kind") or "") == "error_hub"]
    other = [a for a in rest if str(a.get("kind") or "") != "error_hub"]

    emit: list[dict[str, Any]] = []
    if hub and hub_toast_enabled():
        emit.extend(_collapse_hub_alerts(hub))
    if other:
        emit.append(other[0])

    if emit and not _client_toast_rate_ok(bypass=bool(payment)):
        emit = []

    return payment + emit[:1]


def skip_hub_alert_backlog() -> dict[str, Any]:
    """
    Advance error-hub scan offset + inbox toast cursor to now.
    Stops catch-up toasts without deleting the log file.
    """
    path = _error_hub_path()
    size = path.stat().st_size if path.is_file() else 0
    try:
        r = _redis_client()
        r.set(REDIS_KEY_HUB_OFFSET, str(size))
    except Exception:
        pass

    max_ts = time.time()
    try:
        from app.services.admin_inbox import list_inbox_events

        events = list_inbox_events(limit=5)
        if events:
            max_ts = max(float(ev.get("ts_unix") or 0) for ev in events)
    except Exception:
        pass
    try:
        r = _redis_client()
        r.set(REDIS_KEY_INBOX_TOAST_CURSOR, str(max_ts))
        r.set(REDIS_KEY_CLIENT_TOAST_LAST, str(time.time()), ex=client_toast_min_interval_s() * 3)
    except Exception:
        pass
    return {"ok": True, "hub_offset": size, "inbox_toast_cursor_ts": max_ts}


def _scan_error_hub_new_lines() -> list[dict[str, Any]]:
    path = _error_hub_path()
    if not path.is_file():
        return []

    alerts: list[dict[str, Any]] = []
    try:
        r = _redis_client()
        offset = int(r.get(REDIS_KEY_HUB_OFFSET) or "0")
    except Exception:
        offset = 0

    try:
        size = path.stat().st_size
        if offset > size:
            offset = 0
        # First scan: only watch new lines (avoid toasting a full historical log).
        if offset == 0 and size > 0:
            from_start = (os.getenv("TBCC_ALERTS_HUB_FROM_START") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not from_start:
                offset = size
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(offset)
            chunk = f.read()
            new_offset = f.tell()
    except OSError as e:
        logger.debug("error hub read failed: %s", e)
        return []

    try:
        r = _redis_client()
        r.set(REDIS_KEY_HUB_OFFSET, str(new_offset))
    except Exception:
        pass

    for line in chunk.splitlines():
        if not line.strip() or line.startswith("===="):
            continue
        alert = _parse_hub_alert(line)
        if alert and not _dedup_seen(alert["id"]):
            if hub_critical_only() and str(alert.get("severity") or "") != "critical":
                continue
            alerts.append(alert)

    if alerts:
        try:
            from app.services.admin_inbox import hub_batch_instant_enabled, push_hub_ops_alerts_batch

            if hub_batch_instant_enabled():
                push_hub_ops_alerts_batch(alerts)
            else:
                for alert in alerts:
                    _push_ops_inbox_alert(alert)
        except Exception as e:
            logger.debug("hub inbox push failed: %s", e)
            for alert in alerts:
                _push_ops_inbox_alert(alert)
    if not hub_toast_enabled():
        return []
    return alerts


def _collect_breaking_conflict_alerts() -> list[dict[str, Any]]:
    from app.services.system_health import collect_system_health

    health = collect_system_health()
    conflicts = health.get("conflicts") or []
    current = {
        str(c.get("code") or "")
        for c in conflicts
        if c.get("severity") == "critical" and str(c.get("code") or "") in BREAKING_CONFLICT_CODES
    }

    alerts: list[dict[str, Any]] = []
    try:
        r = _redis_client()
        prev_raw = r.smembers(REDIS_KEY_CONFLICT_CODES) or set()
        prev = {str(x) for x in prev_raw}
        new_codes = current - prev
        if current != prev:
            r.delete(REDIS_KEY_CONFLICT_CODES)
            if current:
                r.sadd(REDIS_KEY_CONFLICT_CODES, *current)
    except Exception:
        new_codes = current

    by_code = {str(c.get("code") or ""): c for c in conflicts}
    for code in sorted(new_codes):
        c = by_code.get(code) or {}
        alert_id = f"conflict:{code}"
        if _dedup_seen(alert_id):
            continue
        friendly = conflict_alert_user_copy(code, str(c.get("message") or code))
        item = {
            "id": alert_id,
            "kind": "conflict",
            "code": code,
            "severity": "critical",
            "title": friendly["title"],
            "message": friendly["message"][:480],
            "timestamp": health.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        }
        alerts.append(item)
        _push_ops_inbox_alert(item)
    return alerts


def _collect_companion_gate_alerts() -> list[dict[str, Any]]:
    """Warn when companion bot cannot verify membership in all AOF addlist channels."""
    try:
        from app.services.companion_access import gate_enabled
        from app.services.companion_gate_health import probe_companion_bot_channel_admin_sync
    except Exception:
        return []

    if not gate_enabled():
        return []

    probe = probe_companion_bot_channel_admin_sync()
    if not probe.get("ok"):
        return []
    all_ok = bool(probe.get("bot_admin_all_channels"))
    alert_id = "companion_gate:bot_admin_all_channels"

    try:
        r = _redis_client()
        prev = str(r.get(REDIS_KEY_COMPANION_GATE) or "")
        cur = "1" if all_ok else "0"
        if prev == cur:
            return []
        r.set(REDIS_KEY_COMPANION_GATE, cur, ex=86400 * 7)
    except Exception:
        if all_ok:
            return []

    if all_ok:
        if _dedup_seen(f"{alert_id}:recovered"):
            return []
        item = {
            "id": f"{alert_id}:recovered",
            "kind": "companion_gate",
            "code": "companion_gate_channels_ok",
            "severity": "info",
            "title": "Companion gate channels OK",
            "message": (
                f"@aof_spicybot_bot is admin in all {probe.get('channel_count', '?')} AOF channels — "
                "membership verify works on any addlist lane."
            ),
            "timestamp": _now_iso(),
        }
        alerts: list[dict[str, Any]] = [item]
        return alerts

    if _dedup_seen(alert_id):
        return []

    missing = probe.get("missing_channels") or []
    names = ", ".join(str(m.get("display_name") or "?") for m in missing[:3])
    extra = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
    item = {
        "id": alert_id,
        "kind": "companion_gate",
        "code": "companion_gate_channels",
        "severity": "warning",
        "title": "Companion gate blocked",
        "message": (
            f"@aof_spicybot_bot is not admin in {len(missing)}/{probe.get('channel_count', '?')} "
            f"AOF channels ({names}{extra}).\n\n"
            "What to do:\n"
            "1) Add the bot as admin in each missing channel\n"
            "2) Or run ensure_companion_bot_channel_admin.py --execute\n"
            "3) Until fixed, users may stay stuck at Member pending"
        )[:480],
        "timestamp": _now_iso(),
    }
    alerts = [item]
    _push_ops_inbox_alert(item)
    return alerts


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _poll_payment_priority_toasts() -> list[dict[str, Any]]:
    """Sales, pending checkout, and other money/urgent inbox events → dashboard toasts."""
    if not payment_toast_enabled():
        return []

    from app.services.admin_inbox import list_inbox_events

    try:
        r = _redis_client()
        last_ts = float(r.get(REDIS_KEY_INBOX_TOAST_CURSOR) or "0")
    except Exception:
        last_ts = 0.0

    events = list_inbox_events(limit=100)
    if not events:
        return []

    if last_ts <= 0:
        newest = max(float(ev.get("ts_unix") or 0) for ev in events)
        try:
            r = _redis_client()
            r.set(REDIS_KEY_INBOX_TOAST_CURSOR, str(newest))
        except Exception:
            pass
        return []

    alerts: list[dict[str, Any]] = []
    max_ts = last_ts
    for ev in reversed(events):
        ts = float(ev.get("ts_unix") or 0)
        if ts <= last_ts:
            continue
        cat = str(ev.get("category") or "").lower()
        sev = str(ev.get("severity") or "info").lower()
        include = False
        priority = "urgent"
        toast_severity = "warning"
        if cat in ("payment", "invoice"):
            include = True
            priority = "payment"
            toast_severity = "critical" if cat == "payment" else "warning"
        elif cat == "loot" and sev in ("important", "critical"):
            include = True
            priority = "payment"
            toast_severity = "critical"
        elif ops_toast_enabled() and cat == "ops" and sev == "critical":
            include = True
            priority = "urgent"
            toast_severity = "critical"
        if not include:
            max_ts = max(max_ts, ts)
            continue

        event_id = str(ev.get("id") or "")
        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
        fp_src = "|".join(
            [
                cat,
                sev,
                str(meta.get("code") or ""),
                str(meta.get("alert_id") or ""),
                str(ev.get("title") or "")[:80],
            ]
        )
        alert_id = f"inbox:{hashlib.sha256(fp_src.encode()).hexdigest()[:20]}"
        if _dedup_seen(alert_id):
            max_ts = max(max_ts, ts)
            continue

        title = str(ev.get("title") or "TBCC alert")
        body = _strip_html(str(ev.get("body") or ""))
        msg = body or title
        if len(msg) > 480:
            msg = msg[:480] + "…"

        alerts.append(
            {
                "id": alert_id,
                "kind": priority,
                "code": cat,
                "severity": toast_severity,
                "priority": priority,
                "title": title,
                "message": msg,
                "timestamp": ev.get("ts") or _now_iso(),
            }
        )
        max_ts = max(max_ts, ts)

    if max_ts > last_ts:
        try:
            r = _redis_client()
            r.set(REDIS_KEY_INBOX_TOAST_CURSOR, str(max_ts))
        except Exception:
            pass
    return alerts


def _push_ops_inbox_alert(alert: dict[str, Any]) -> None:
    try:
        from app.services.admin_inbox import push_admin_inbox_event

        sev = str(alert.get("severity") or "warning").lower()
        inbox_sev = "critical" if sev == "critical" else "important" if sev == "warning" else "info"
        push_admin_inbox_event(
            category="ops",
            severity=inbox_sev,  # type: ignore[arg-type]
            title=str(alert.get("title") or "TBCC alert"),
            body=str(alert.get("message") or "")[:1200],
            meta={
                "code": alert.get("code"),
                "kind": alert.get("kind"),
                "alert_id": alert.get("id"),
                "scheduler_names": alert.get("scheduler_names"),
                "post_ids": alert.get("post_ids"),
            },
            instant=(
                str(alert.get("kind") or "") != "error_hub"
                and inbox_sev in ("critical", "important")
            ),
        )
    except Exception as e:
        logger.debug("ops inbox push failed: %s", e)


def poll_ops_alerts() -> dict[str, Any]:
    """Return newly deduped alerts for clients (toast / tray / extension)."""
    from app.services.ops_restart_grace import backend_restart_grace_active, restart_grace_public_snapshot

    grace = restart_grace_public_snapshot()
    if backend_restart_grace_active():
        return {
            "ok": True,
            "enabled": alerts_enabled(),
            "hub_scan": hub_scan_enabled(),
            "hub_toast": hub_toast_enabled(),
            "hub_critical_only": hub_critical_only(),
            "ops_toast": ops_toast_enabled(),
            "payment_toast": payment_toast_enabled(),
            "alerts": [],
            "count": 0,
            "restart_grace": grace,
            "timestamp": _now_iso(),
        }

    alerts: list[dict[str, Any]] = []
    if not alerts_enabled():
        return {
            "ok": True,
            "enabled": False,
            "alerts": [],
            "restart_grace": grace,
            "timestamp": _now_iso(),
        }

    try:
        alerts.extend(_poll_payment_priority_toasts())
    except Exception as e:
        logger.debug("payment inbox toasts failed: %s", e)

    try:
        alerts.extend(_collect_breaking_conflict_alerts())
    except Exception as e:
        logger.debug("conflict alerts failed: %s", e)

    try:
        alerts.extend(_collect_companion_gate_alerts())
    except Exception as e:
        logger.debug("companion gate alerts failed: %s", e)

    if hub_scan_enabled():
        try:
            alerts.extend(_scan_error_hub_new_lines())
        except Exception as e:
            logger.debug("hub alerts failed: %s", e)

    alerts = _apply_client_poll_limits(alerts)

    return {
        "ok": True,
        "enabled": True,
        "hub_scan": hub_scan_enabled(),
        "hub_toast": hub_toast_enabled(),
        "hub_critical_only": hub_critical_only(),
        "ops_toast": ops_toast_enabled(),
        "payment_toast": payment_toast_enabled(),
        "toast_budget": get_alert_toast_settings(),
        "alerts": alerts,
        "count": len(alerts),
        "restart_grace": grace,
        "timestamp": _now_iso(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
