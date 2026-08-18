"""
Central admin notification inbox — one tidy feed for payment, loot, ops, and invoices.

Events are stored in Redis (recent ~200) and optionally pushed instantly to ADMIN_TELEGRAM_ID
via the secretary bot token. Digests: /inbox /now in `python -m bots.secretary_bot` (admin only).

Categories: payment, loot, ops, invoice, system, traffic (growth alias legacy)
Severity: critical, important, info

Instant Telegram policy:
- payment (completed sales): important + TBCC_INBOX_INSTANT_SALES (default on)
- invoice (pending manual checkout): important + instant=True on push
- ops (errors, bottlenecks): critical/important per TBCC_INBOX_INSTANT (default critical)
- loot referral / growth analytics: info, inbox-only (no instant DM)
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

Category = Literal["payment", "loot", "ops", "invoice", "system", "traffic", "growth"]
Severity = Literal["critical", "important", "info"]

REDIS_KEY_EVENTS = "tbcc:admin_inbox:events"
REDIS_KEY_LAST_READ = "tbcc:admin_inbox:last_read"
REDIS_KEY_SECRETARY_ONLINE = "tbcc:admin_inbox:last_secretary_online"
REDIS_KEY_RECURRING_ISSUES = "tbcc:admin_inbox:recurring_issues"
MAX_EVENTS = 200
RECURRING_ISSUE_TTL_SEC = 14 * 86400  # drop stale rows after 14d idle
SECRETARY_ONLINE_DEDUP_SEC = 1200  # 20 min — deploy restarts should not flood inbox

_CATEGORY_ICON: dict[str, str] = {
    "payment": "💰",
    "loot": "🎮",
    "ops": "🔧",
    "invoice": "🧾",
    "system": "⚙️",
    "traffic": "📡",
    "growth": "📊",
}

_SEVERITY_RANK = {"info": 0, "important": 1, "critical": 2}


def inbox_enabled() -> bool:
    v = (os.getenv("TBCC_INBOX_ENABLED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def hub_batch_instant_enabled() -> bool:
    """Batch error-hub ops alerts into one Telegram ping (avoids 20 consecutive DMs)."""
    return (os.getenv("TBCC_INBOX_HUB_BATCH_INSTANT") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def hub_batch_max_lines_in_digest() -> int:
    raw = (os.getenv("TBCC_INBOX_HUB_BATCH_PREVIEW_LINES") or "5").strip()
    try:
        return max(1, min(10, int(raw)))
    except ValueError:
        return 5


def invoice_inbox_actions_enabled() -> bool:
    return (os.getenv("TBCC_INBOX_INVOICE_ACTIONS") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def ops_inbox_actions_enabled() -> bool:
    return (os.getenv("TBCC_INBOX_OPS_ACTIONS") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def instant_severities() -> set[str]:
    raw = (os.getenv("TBCC_INBOX_INSTANT") or "critical").strip().lower()
    if raw in ("0", "false", "no", "off", "none"):
        return set()
    if raw in ("1", "true", "yes", "on", "all"):
        return {"critical", "important", "info"}
    return {s.strip() for s in raw.split(",") if s.strip()}


def _format_event_body_html(event: dict[str, Any], *, truncate: int | None = None) -> str:
    """Render inbox body as Telegram-safe HTML (meta-aware; never double-escape our tags)."""
    cat = str(event.get("category") or "")
    meta = event.get("meta") or {}
    raw_body = str(event.get("body") or "").strip()

    if cat == "invoice":
        ref = html.escape(str(meta.get("reference_code") or ""))
        uid = html.escape(str(meta.get("telegram_user_id") or ""))
        plan = html.escape(str(meta.get("plan_name") or "Product"))
        stars = int(meta.get("price_stars") or 0)
        lines = [
            f"Ref <code>{ref}</code> · buyer <code>{uid}</code>",
            f"{plan} · {stars} ⭐",
        ]
        if bool(meta.get("crypto_auto_checkout")):
            lines.append("NOWPayments IPN usually auto-fulfills — Approve only if paid but access is missing.")
        else:
            lines.append("Confirm payment received, then tap <b>Approve</b> (or <b>Deny</b> to clear).")
        text = "\n".join(lines)
    elif cat == "payment":
        uid = html.escape(str(meta.get("telegram_user_id") or ""))
        plan = html.escape(str(meta.get("plan_name") or "Product"))
        sale_kind = html.escape(str(meta.get("sale_kind") or meta.get("product_type") or "subscription"))
        pm = html.escape(str(meta.get("payment_method_label") or meta.get("payment_method") or "?"))
        stars = int(meta.get("amount_stars") or 0)
        ref = meta.get("reference_code")
        ref_line = f"\nRef <code>{html.escape(str(ref))}</code>" if ref else ""
        text = (
            f"<b>{plan}</b> · {sale_kind.replace('_', ' ')}\n"
            f"Buyer <code>{uid}</code> · {stars} ⭐ · {pm}{ref_line}"
        )
    elif cat == "growth":
        slug = html.escape(str(meta.get("slug") or ""))
        hits = int(meta.get("hit_count") or 0)
        ip = html.escape(str(meta.get("ip") or "?"))
        country = html.escape(str(meta.get("country") or "??"))
        ua = html.escape(str(meta.get("user_agent") or "")[:100])
        dest = html.escape(str(meta.get("destination_url") or "")[:160])
        campaign = (meta.get("campaign_id") or "").strip()
        lines = [
            f"slug <code>{slug}</code> · hits {hits}",
            f"ip {ip} · {country}",
            f"ua {ua}",
        ]
        if campaign:
            lines.append(f"id <code>{html.escape(campaign)}</code>")
        lines.append(f"→ {dest}")
        text = "\n".join(lines)
    elif str(meta.get("code") or "") in (
        "revenue_brief",
        "secretary_draft",
        "secretary_draft_fail",
        "secretary_new_lead",
    ) and raw_body:
        # Pre-rendered Telegram HTML from revenue brief / secretary drafts.
        text = raw_body[:1200]
    elif cat == "traffic" and meta.get("pulse_event_type"):
        from app.services.traffic_inbox_copy import format_traffic_detail

        text = format_traffic_detail(meta, raw_body=raw_body)
        if not text.strip() and raw_body:
            text = html.escape(raw_body)
    elif cat == "traffic" and (
        str(meta.get("pulse_event_type") or "") == "beacon" or meta.get("slug")
    ):
        from app.services.traffic_beacon_notify import format_traffic_beacon_body_html

        text = format_traffic_beacon_body_html(meta)
        if not text.strip() and raw_body:
            text = html.escape(raw_body)
    else:
        text = html.escape(raw_body) if raw_body else ""

    if truncate is not None and len(text) > truncate:
        return _truncate_html_fragment(text, truncate)
    return text


def parse_admin_telegram_id(raw: str | None = None) -> int | None:
    """Parse ADMIN_TELEGRAM_ID; strips accidental non-digit prefix/suffix (e.g. l7787282561)."""
    text = (raw if raw is not None else os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if digits:
        try:
            return int(digits)
        except ValueError:
            pass
    try:
        return int(text)
    except ValueError:
        logger.warning("ADMIN_TELEGRAM_ID invalid: %r", text[:24])
        return None


def admin_telegram_ids() -> set[int]:
    """Primary admin plus optional extras + hardcoded TBCC operators (owner + alt)."""
    from app.services.tbcc_operator_ids import tbcc_operator_ids

    ids: set[int] = set(tbcc_operator_ids())
    primary = parse_admin_telegram_id()
    if primary is not None:
        ids.add(primary)
    for key in (
        "TBCC_INBOX_ADMIN_IDS",
        "TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS",
        "TBCC_SECRETARY_ADMIN_IDS",
    ):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        for part in raw.split(","):
            token = part.strip()
            if not token:
                continue
            parsed = parse_admin_telegram_id(token)
            if parsed is not None:
                ids.add(parsed)
    notify_raw = (os.getenv("TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID") or "").strip()
    if notify_raw:
        parsed = parse_admin_telegram_id(notify_raw)
        if parsed is not None:
            ids.add(parsed)
    return ids


def _admin_telegram_id() -> int | None:
    return parse_admin_telegram_id()


def _bot_token() -> str:
    return (
        (os.getenv("TBCC_SECRETARY_BOT_TOKEN") or os.getenv("SECRETARY_BOT_TOKEN") or "").strip()
        or (os.getenv("TBCC_INBOX_BOT_TOKEN") or "").strip()
        or (os.getenv("TBCC_SALES_NOTIFY_BOT_TOKEN") or "").strip()
        or (os.getenv("BOT_TOKEN") or "").strip()
    )


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_ts() -> float:
    return time.time()


def get_inbox_event_by_id(event_id: str) -> dict[str, Any] | None:
    needle = (event_id or "").strip()
    if not needle:
        return None
    try:
        r = _redis_client()
        raw_items = r.lrange(REDIS_KEY_EVENTS, 0, MAX_EVENTS - 1)
    except Exception:
        return None
    for raw in raw_items:
        try:
            ev = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(ev, dict) and str(ev.get("id") or "") == needle:
            return ev
    return None


def _ops_instant_reply_markup(event: dict[str, Any]) -> dict[str, Any] | None:
    if not ops_inbox_actions_enabled():
        return None
    if str(event.get("category") or "") != "ops":
        return None
    if str(event.get("severity") or "") not in ("critical", "important"):
        return None
    eid = str(event.get("id") or "")[:32]
    if not eid:
        return None
    meta = event.get("meta") or {}
    fw_id = str(meta.get("flywheel_action_id") or "")[:32]
    rows: list[list[dict[str, str]]] = [
        [{"text": "⚡ Telegram relief", "callback_data": f"ops:relief:{eid}"}],
        [
            {"text": "📋 Copy for Cursor", "callback_data": f"ops:copy:{eid}"},
            {"text": "🤖 Agent triage", "callback_data": f"ops:cursor:{eid}"},
        ],
    ]
    if fw_id:
        rows.append(
            [
                {"text": "✅ Approve fix", "callback_data": f"ops:fw:ok:{fw_id}"},
                {"text": "✗ Reject", "callback_data": f"ops:fw:no:{fw_id}"},
            ]
        )
    rows.append([{"text": "🏠 Menu", "callback_data": "sec:menu:home"}])
    return {"inline_keyboard": rows}


def _invoice_instant_reply_markup(event: dict[str, Any]) -> dict[str, Any] | None:
    if not invoice_inbox_actions_enabled():
        return None
    if str(event.get("category") or "") != "invoice":
        return None
    if str(event.get("severity") or "") not in ("critical", "important"):
        return None
    eid = str(event.get("id") or "")[:32]
    if not eid:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve sale", "callback_data": f"inv:ok:{eid}"},
                {"text": "✗ Deny", "callback_data": f"inv:no:{eid}"},
            ],
            [{"text": "🏠 Menu", "callback_data": "sec:menu:home"}],
        ]
    }


def _instant_reply_markup(event: dict[str, Any]) -> dict[str, Any] | None:
    return _ops_instant_reply_markup(event) or _invoice_instant_reply_markup(event)


def _telegram_send_html(text: str, *, reply_markup: dict[str, Any] | None = None) -> None:
    chat_ids = admin_telegram_ids()
    token = _bot_token()
    if not chat_ids or not token:
        if not token:
            logger.debug("admin inbox Telegram skipped: no bot token (TBCC_SECRETARY_BOT_TOKEN)")
        elif not chat_ids:
            logger.debug("admin inbox Telegram skipped: ADMIN_TELEGRAM_ID unset")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in sorted(chat_ids):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.post(url, json=payload)
                if r.status_code >= 400:
                    hint = ""
                    if r.status_code == 403:
                        hint = " — open @aof_secretary_bot and tap /start once to allow DMs"
                    logger.warning(
                        "admin inbox Telegram HTTP %s (chat %s): %s%s",
                        r.status_code,
                        chat_id,
                        (r.text or "")[:300],
                        hint,
                    )
        except Exception as e:
            logger.warning("admin inbox Telegram failed (chat %s): %s", chat_id, e)


def _store_event(event: dict[str, Any]) -> None:
    try:
        r = _redis_client()
        r.lpush(REDIS_KEY_EVENTS, json.dumps(event, separators=(",", ":")))
        r.ltrim(REDIS_KEY_EVENTS, 0, MAX_EVENTS - 1)
    except Exception as e:
        logger.debug("admin inbox store failed: %s", e)


def _format_instant(event: dict[str, Any]) -> str:
    cat = str(event.get("category") or "system")
    meta = event.get("meta") or {}
    if cat == "traffic" and meta.get("pulse_event_type"):
        from app.services.traffic_inbox_copy import format_traffic_compact_line

        return format_traffic_compact_line(event, ago="now")
    if str(meta.get("code") or "") in (
        "revenue_brief",
        "secretary_draft_fail",
        "secretary_new_lead",
        "secretary_draft",
    ):
        body = _format_event_body_html(event)
        if body:
            return body
    icon = _CATEGORY_ICON.get(cat, "📬")
    sev = str(event.get("severity") or "info")
    if cat == "payment":
        icon = "✅"
    sev_tag = {"critical": "🔴", "important": "🟠", "info": "🔵"}.get(sev, "")
    title = html.escape(str(event.get("title") or "Alert"))
    body = _format_event_body_html(event)
    lines = [f"{icon} <b>{title}</b> {sev_tag}".rstrip()]
    if body:
        lines.append(body)
    if str(event.get("category") or "") == "ops" and ops_inbox_actions_enabled():
        lines.append("<i>Tap a button below or use /ops · /relief</i>")
    elif str(event.get("category") or "") == "invoice" and invoice_inbox_actions_enabled():
        lines.append("<i>Tap Approve or Deny below · history: /inbox</i>")
    elif str(event.get("category") or "") == "payment":
        lines.append("<i>Sale recorded · /inbox for history</i>")
    return "\n".join(lines)


def push_admin_inbox_event(
    *,
    category: Category,
    severity: Severity,
    title: str,
    body: str = "",
    meta: dict[str, Any] | None = None,
    instant: bool | None = None,
) -> dict[str, Any] | None:
    """Record an admin notification. Returns the event dict or None when disabled."""
    if not inbox_enabled():
        return None
    title_s = (title or "").strip()[:200]
    if category == "system" and title_s.lower() == "secretary bot online":
        try:
            r = _redis_client()
            last = float(r.get(REDIS_KEY_SECRETARY_ONLINE) or 0)
            if last and (_now_ts() - last) < SECRETARY_ONLINE_DEDUP_SEC:
                return None
            r.set(REDIS_KEY_SECRETARY_ONLINE, str(_now_ts()))
        except Exception:
            pass
    event: dict[str, Any] = {
        "id": secrets.token_hex(8),
        "ts": _now_iso(),
        "ts_unix": _now_ts(),
        "category": category,
        "severity": severity,
        "title": title_s,
        "body": (body or "").strip()[:3500],
        "meta": meta or {},
    }
    _store_event(event)
    should_instant = instant if instant is not None else severity in instant_severities()
    if should_instant:
        _telegram_send_html(_format_instant(event), reply_markup=_instant_reply_markup(event))
    return event


def push_hub_ops_alerts_batch(alerts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Store each hub alert in inbox but send at most one instant Telegram digest.
    Prevents notification storms when error-hub catches up on many lines at once.
    """
    if not inbox_enabled() or not alerts:
        return None

    stored: list[dict[str, Any]] = []
    for alert in alerts:
        sev_raw = str(alert.get("severity") or "warning").lower()
        inbox_sev: Severity = (
            "critical" if sev_raw == "critical" else "important" if sev_raw == "warning" else "info"
        )
        ev = push_admin_inbox_event(
            category="ops",
            severity=inbox_sev,
            title=str(alert.get("title") or "TBCC alert"),
            body=str(alert.get("message") or "")[:1200],
            meta={
                "code": alert.get("code"),
                "kind": alert.get("kind"),
                "alert_id": alert.get("id"),
                "fix_hint": alert.get("fix_hint"),
                "scheduler_names": alert.get("scheduler_names"),
                "post_ids": alert.get("post_ids"),
            },
            instant=False,
        )
        if ev:
            stored.append(ev)

    if not stored:
        return None

    if not instant_severities() or not any(e.get("severity") == "critical" for e in stored):
        return {"stored": len(stored), "batched_instant": False}

    preview_n = hub_batch_max_lines_in_digest()
    preview_lines: list[str] = []
    for ev in stored[:preview_n]:
        t = html.escape(str(ev.get("title") or ""))
        b = _format_event_body_html(ev, truncate=220)
        preview_lines.append(f"• <b>{t}</b>\n  {b}")
    extra = len(stored) - preview_n
    if extra > 0:
        preview_lines.append(f"… and <b>{extra}</b> more in <code>/ops</code>")

    text = (
        f"🔧 <b>Error hub batch</b> · <b>{len(stored)}</b> new 🔴\n\n"
        + "\n".join(preview_lines)
        + "\n\n<i>One ping per scan — details in /ops · tap Copy hub for .txt + copy buttons</i>"
    )

    latest_id = str(stored[0].get("id") or "")
    rows: list[list[dict[str, str]]] = [
        [{"text": "📋 Copy hub (20 lines)", "callback_data": "sec:menu:hubcopy"}],
        [
            {"text": "⚡ Relief", "callback_data": "sec:menu:run:relief"},
            {"text": "🧰 Ops menu", "callback_data": "sec:menu:cat:ops"},
        ],
        [{"text": "🏠 Menu", "callback_data": "sec:menu:home"}],
    ]
    _telegram_send_html(text, reply_markup={"inline_keyboard": rows})
    return {"stored": len(stored), "batched_instant": True}


def get_last_read_ts() -> float:
    try:
        r = _redis_client()
        raw = r.get(REDIS_KEY_LAST_READ)
        return float(raw) if raw else 0.0
    except Exception:
        return 0.0


def mark_inbox_read() -> float:
    ts = _now_ts()
    try:
        r = _redis_client()
        r.set(REDIS_KEY_LAST_READ, str(ts))
    except Exception:
        pass
    return ts


def bump_recurring_issue(
    issue_id: str,
    *,
    title: str,
    action: str = "",
    fingerprint: str = "",
) -> dict[str, Any]:
    """
    Increment an open recurring ops issue (Traffic Pulse digest playbook stuck on repeat).
    Stored in Redis — surfaced at top of /inbox and /inbox issues.
    """
    key = (issue_id or "").strip()
    if not key:
        return {}
    now = _now_ts()
    row: dict[str, Any] = {
        "issue_id": key,
        "count": 1,
        "title": (title or "").strip()[:400],
        "action": (action or "").strip()[:400],
        "fingerprint": (fingerprint or "").strip()[:512],
        "first_ts": now,
        "last_ts": now,
    }
    try:
        r = _redis_client()
        raw = r.hget(REDIS_KEY_RECURRING_ISSUES, key)
        if raw:
            try:
                prev = json.loads(raw)
                if isinstance(prev, dict):
                    row["count"] = int(prev.get("count") or 0) + 1
                    row["first_ts"] = float(prev.get("first_ts") or now)
            except (TypeError, json.JSONDecodeError, ValueError):
                pass
        r.hset(REDIS_KEY_RECURRING_ISSUES, key, json.dumps(row, separators=(",", ":")))
        # Prune idle rows
        all_raw = r.hgetall(REDIS_KEY_RECURRING_ISSUES) or {}
        for field, blob in all_raw.items():
            try:
                item = json.loads(blob)
                last = float(item.get("last_ts") or 0)
                if last and (now - last) > RECURRING_ISSUE_TTL_SEC:
                    r.hdel(REDIS_KEY_RECURRING_ISSUES, field)
            except (TypeError, json.JSONDecodeError, ValueError):
                r.hdel(REDIS_KEY_RECURRING_ISSUES, field)
    except Exception:
        logger.debug("recurring issue bump failed", exc_info=True)
    return row


def list_recurring_issues(*, min_count: int = 1, limit: int = 12) -> list[dict[str, Any]]:
    limit = max(1, min(30, int(limit)))
    min_count = max(1, int(min_count))
    try:
        r = _redis_client()
        raw = r.hgetall(REDIS_KEY_RECURRING_ISSUES) or {}
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for blob in raw.values():
        try:
            item = json.loads(blob)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        if int(item.get("count") or 0) < min_count:
            continue
        rows.append(item)
    rows.sort(key=lambda x: (-int(x.get("count") or 0), -float(x.get("last_ts") or 0)))
    return rows[:limit]


def clear_recurring_issue(issue_id: str) -> bool:
    key = (issue_id or "").strip()
    if not key:
        return False
    try:
        r = _redis_client()
        return bool(r.hdel(REDIS_KEY_RECURRING_ISSUES, key))
    except Exception:
        return False


def format_recurring_issues_html(
    issues: list[dict[str, Any]] | None = None,
    *,
    title: str = "Recurring issues",
    empty_hint: str = "No stuck playbooks — Traffic Pulse is not repeating the same advice.",
) -> str:
    from app.services.secretary_report_copy import humanize_pulse_issue

    rows = issues if issues is not None else list_recurring_issues()
    if not rows:
        return f"🔁 <b>{html.escape(title)}</b>\n\n{html.escape(empty_hint)}"

    lines = [
        f"🔁 <b>{html.escape(title)}</b>",
        "<i>Same Traffic Pulse advice on repeat — count ticks each digest window.</i>",
        "",
    ]
    for item in rows:
        iid = str(item.get("issue_id") or "")
        n = int(item.get("count") or 0)
        label = html.escape(humanize_pulse_issue(iid))
        action = html.escape(str(item.get("action") or "").strip())
        ago = _ago_label(float(item.get("last_ts") or 0))
        first = _ago_label(float(item.get("first_ts") or 0))
        lines.append(f"☑ <b>×{n}</b> · {label}")
        if action:
            lines.append(f"   {action}")
        lines.append(f"   <i>last {html.escape(ago)} · since {html.escape(first)}</i>")
        lines.append("")
    lines.append("<i>/inbox issues · digest DMs suppress when advice unchanged</i>")
    return clip_telegram_html("\n".join(lines).strip(), 4096)


def list_inbox_events(
    *,
    limit: int = 25,
    since_ts: float | None = None,
    category: str | None = None,
    min_severity: Severity | None = None,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    limit = max(1, min(100, int(limit)))
    if unread_only and since_ts is None:
        since_ts = get_last_read_ts()
    min_rank = _SEVERITY_RANK.get(min_severity or "info", 0)
    cat_filter = (category or "").strip().lower() or None
    try:
        r = _redis_client()
        raw_items = r.lrange(REDIS_KEY_EVENTS, 0, MAX_EVENTS - 1)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            ev = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(ev, dict):
            continue
        ts = float(ev.get("ts_unix") or 0)
        if since_ts is not None and ts <= since_ts:
            continue
        if cat_filter and str(ev.get("category") or "").lower() != cat_filter:
            continue
        sev = str(ev.get("severity") or "info")
        if _SEVERITY_RANK.get(sev, 0) < min_rank:
            continue
        out.append(ev)
        if len(out) >= limit:
            break
    return out


_HTML_CLOSE_TAGS = ("blockquote", "pre", "a", "code", "b", "i", "u")


def _truncate_html_fragment(text: str, max_len: int) -> str:
    """Cut a fragment without leaving a dangling tag or entity (parent may wrap in <i>)."""
    if max_len < 2 or len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    cut = re.sub(r"<[^>]*$", "", cut)
    cut = re.sub(r"&[a-zA-Z0-9#]*$", "", cut)
    return cut + "…"


def clip_telegram_html(text: str, max_len: int = 4096) -> str:
    """Keep Telegram sendMessage HTML under max_len without slicing mid-tag."""
    if len(text) <= max_len:
        return text
    reserve = 32
    cut = text[: max(1, max_len - reserve)]
    nl = cut.rfind("\n")
    if nl >= max_len // 3:
        cut = cut[:nl]
    cut = re.sub(r"<[^>]*$", "", cut)
    closers: list[str] = []
    for tag in _HTML_CLOSE_TAGS:
        opens = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", cut, flags=re.I))
        closes = len(re.findall(rf"</{tag}>", cut, flags=re.I))
        for _ in range(max(0, opens - closes)):
            closers.append(f"</{tag}>")
    note = "\n<i>…truncated — use a tighter filter</i>"
    out = cut.rstrip() + note + "".join(reversed(closers))
    if len(out) <= max_len:
        return out
    return _truncate_html_fragment(cut, max_len)


def _collapse_repeat_events(events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """Merge consecutive same category+title (hourly session-lock storms)."""
    out: list[tuple[dict[str, Any], int]] = []
    for ev in events:
        key = (
            str(ev.get("category") or ""),
            str(ev.get("title") or ""),
            str((ev.get("meta") or {}).get("code") or ""),
        )
        if out:
            prev, n = out[-1]
            pkey = (
                str(prev.get("category") or ""),
                str(prev.get("title") or ""),
                str((prev.get("meta") or {}).get("code") or ""),
            )
            if pkey == key:
                out[-1] = (prev, n + 1)
                continue
        out.append((ev, 1))
    return out


def _ago_label(ts_unix: float) -> str:
    if ts_unix <= 0:
        return "?"
    delta = max(0, int(_now_ts() - ts_unix))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def format_inbox_digest(
    events: list[dict[str, Any]],
    *,
    title: str = "TBCC Inbox",
    empty_hint: str = "Nothing here — you're caught up.",
) -> str:
    if not events:
        return f"📬 <b>{html.escape(title)}</b>\n\n{html.escape(empty_hint)}"
    unread_cutoff = get_last_read_ts()
    unread_count = sum(1 for e in events if float(e.get("ts_unix") or 0) > unread_cutoff)
    from app.services.secretary_report_copy import format_inbox_header

    header = format_inbox_header(title=title, unread_count=unread_count)
    blocks: list[str] = [header, ""]

    recurring = list_recurring_issues(min_count=2, limit=5)
    if recurring:
        blocks.append(format_recurring_issues_html(recurring, title="Recurring"))
        blocks.append("")

    traffic_events = [e for e in events if str(e.get("category") or "") == "traffic"]
    other_events = [e for e in events if str(e.get("category") or "") != "traffic"]

    from app.services.traffic_inbox_copy import format_system_compact_line, format_traffic_compact_line, format_traffic_rollup

    rollup = format_traffic_rollup(traffic_events, ago_fn=_ago_label) if len(traffic_events) >= 4 else None
    if rollup:
        blocks.append(rollup)
        blocks.append("")
        digest_events = other_events
    else:
        digest_events = events

    footer = (
        "\n\n<i>/read marks all as seen · /inbox issues · filters: /payment /loot /ops /critical</i>"
    )
    collapsed = _collapse_repeat_events(digest_events)
    skipped = 0
    for idx, (ev, repeats) in enumerate(collapsed):
        cat = str(ev.get("category") or "system")
        ago = _ago_label(float(ev.get("ts_unix") or 0))
        if cat == "traffic":
            line = format_traffic_compact_line(ev, ago=ago)
        elif cat == "system":
            line = format_system_compact_line(ev, ago=ago)
        else:
            icon = _CATEGORY_ICON.get(cat, "📬")
            sev = str(ev.get("severity") or "info")
            sev_tag = {"critical": "🔴", "important": "🟠", "info": ""}.get(sev, "")
            t = html.escape(str(ev.get("title") or ""))
            b = _format_event_body_html(ev, truncate=140)
            line = f"{icon} <b>{t}</b>"
            if sev_tag:
                line += f" {sev_tag}"
            line += f" · <code>{html.escape(ago)}</code>"
            if repeats > 1:
                line += f" · ×{repeats}"
            if b:
                line += f"\n  <i>{b}</i>"
        if repeats > 1 and cat in ("traffic", "system") and "×" not in line:
            line += f" · ×{repeats}"
        candidate = "\n".join(blocks + ["", line]).strip() + footer
        if len(candidate) > 4000:
            skipped = sum(n for _, n in collapsed[idx:])
            break
        blocks.append("")
        blocks.append(line)

    if skipped:
        blocks.append("")
        blocks.append(f"<i>…and {skipped} more (message cap) — try /ops or /now</i>")
    blocks.append("")
    blocks.append(
        "<i>/read marks all as seen · /inbox issues · filters: /payment /loot /ops /critical</i>"
    )
    return clip_telegram_html("\n".join(blocks).strip(), 4096)
