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

logger = logging.getLogger(__name__)

REDIS_KEY_HUB_OFFSET = "tbcc:alerts:hub_offset"
REDIS_KEY_CONFLICT_CODES = "tbcc:alerts:conflict_codes"
REDIS_DEDUP_PREFIX = "tbcc:alerts:dedup:"

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
    (re.compile(r"database is locked", re.I), "session_sqlite_lock", "critical", "Telethon/SQLite session lock"),
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
    return (os.getenv("TBCC_ALERTS_HUB_SCAN") or "1").strip().lower() in ("1", "true", "yes", "on")


def alert_dedup_ttl_s() -> int:
    try:
        return max(300, int(os.getenv("TBCC_ALERTS_DEDUP_TTL_S") or "1800"))
    except ValueError:
        return 1800


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


def _normalize_hub_body(body: str) -> str:
    one = re.sub(r"[\r\n]+", " ", (body or "").strip())
    return one[:200]


def _hub_fingerprint(service: str, body: str) -> str:
    b = (body or "").lower()
    if "traceback (most recent call last)" in b:
        raw = f"hub:{service}:traceback"
    elif "nsfw classify" in b and "actively refused" in b:
        raw = f"hub:{service}:nsfw_sidecar_down"
    elif "httpx" in b and ("network" in b or "connect" in b):
        raw = f"hub:{service}:telegram_network"
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
    blob = body or line
    if "traceback (most recent call last)" in blob.lower():
        code = "service_traceback"
        title = f"{service} error"
        severity = "warning"
    elif "nsfw classify" in blob.lower() and "actively refused" in blob.lower():
        return None
    if level in ("ERROR", "CRITICAL", "FATAL") and severity == "warning":
        if "traceback" not in blob.lower():
            severity = "critical"

    fp = _hub_fingerprint(service, blob)
    msg = _normalize_hub_body(body or line)
    if len(msg) > 220:
        msg = msg[:220] + "…"
    return {
        "id": f"hub:{fp}",
        "kind": "error_hub",
        "code": code,
        "severity": severity,
        "title": title,
        "message": f"[{service}] {msg}",
        "service": service,
        "timestamp": m.group("ts") if m else datetime.now(timezone.utc).isoformat(),
    }


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
            alerts.append(alert)
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
    titles = {
        "redis_down": "Redis down",
        "api_port_duplicate": "API port conflict",
        "uvicorn_orphans": "Orphan API workers",
        "session_lock_storm": "Session lock storm",
    }
    for code in sorted(new_codes):
        c = by_code.get(code) or {}
        alert_id = f"conflict:{code}"
        if _dedup_seen(alert_id):
            continue
        alerts.append(
            {
                "id": alert_id,
                "kind": "conflict",
                "code": code,
                "severity": "critical",
                "title": titles.get(code, "TBCC service conflict"),
                "message": str(c.get("message") or code)[:280],
                "timestamp": health.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            }
        )
    return alerts


def poll_ops_alerts() -> dict[str, Any]:
    """Return newly deduped alerts for clients (toast / tray / extension)."""
    if not alerts_enabled():
        return {"ok": True, "enabled": False, "alerts": [], "timestamp": _now_iso()}

    alerts: list[dict[str, Any]] = []
    try:
        alerts.extend(_collect_breaking_conflict_alerts())
    except Exception as e:
        logger.debug("conflict alerts failed: %s", e)

    if hub_scan_enabled():
        try:
            alerts.extend(_scan_error_hub_new_lines())
        except Exception as e:
            logger.debug("hub alerts failed: %s", e)

    return {
        "ok": True,
        "enabled": True,
        "hub_scan": hub_scan_enabled(),
        "alerts": alerts,
        "count": len(alerts),
        "timestamp": _now_iso(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
