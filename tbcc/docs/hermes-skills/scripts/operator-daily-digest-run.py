#!/usr/bin/env python3
"""Fetch + format operator daily digest — stdout is Telegram HTML (Hermes no_agent).

No LLM. Typical runtime: ~15–45s (Gmail/Calendar API + island health).
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo

PY = Path(r"C:\Python314\python.exe")
HERE = Path(__file__).resolve().parent
FETCH = HERE / "operator-daily-digest-fetch.py"
TZ = ZoneInfo("America/Los_Angeles")

# --- action URLs (official settings pages only) ---
URLS = {
    "wells_fargo": "https://connect.secure.wellsfargo.com/auth/login/present",
    "gmail_fwd": "https://mail.google.com/mail/u/?authuser={email}#settings/fwdandpop",
    "github_apps": "https://github.com/settings/applications",
    "google_connections": "https://myaccount.google.com/connections",
    "sccha": "https://portal.scchousingauthority.org/",
    "proton": "https://mail.proton.me/u/0/inbox",
    "cursor_billing": "https://cursor.com/settings/billing",
    "payoneer": "https://login.payoneer.com/",
    "stripe_billing": "https://billing.stripe.com/login",
}

DROP_LABELS = frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"})


def _run_fetch() -> dict:
    r = subprocess.run(
        [str(PY), str(FETCH)],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode not in (0, 2) or not (r.stdout or "").strip():
        err = (r.stderr or r.stdout or "fetch failed")[:500]
        raise RuntimeError(err)
    return json.loads(r.stdout)


def _email_addr(raw_from: str) -> str:
    _, addr = parseaddr(raw_from or "")
    return (addr or raw_from or "").strip().lower()


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _days_open_map(follow_through: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in follow_through or []:
        key = (_email_addr(row.get("from", "")) + "|" + (row.get("subject") or "")).lower()
        out[key] = int(row.get("days_open") or 0)
    return out


def _open_tag(msg: dict, days_map: dict[str, int]) -> str:
    key = (_email_addr(msg.get("from", "")) + "|" + (msg.get("subject") or "")).lower()
    days = days_map.get(key) or 0
    if days >= 2:
        return f"<i>open {days} days</i> · "
    return ""


def _classify(msg: dict) -> dict | None:
    """Return card spec or None if this message should not surface in TO HANDLE."""
    subj = (msg.get("subject") or "").lower()
    snip = (msg.get("snippet") or "").lower()
    frm = _email_addr(msg.get("from", ""))
    blob = f"{frm} {subj} {snip}"
    labels = set(msg.get("labels") or [])

    if labels & DROP_LABELS and "IMPORTANT" not in labels:
        return None

    if "wellsfargo" in frm or "alerts@notify.wellsfargo" in frm:
        action = "→ Fund Wells Fargo now"
        if "declined" in blob or "below zero" in blob or "zero" in blob:
            detail = "Debit declined or balance at/below zero."
            risk = "Overdraft fees and failed auto-pays."
        elif "zelle" in blob or "received" in blob:
            return None  # informational credit — not TO HANDLE
        else:
            detail = subj[:120] or "Wells Fargo alert."
            risk = "Review the account today."
        return {
            "emoji": "💳",
            "title": "BANKING",
            "action": action,
            "url": URLS["wells_fargo"],
            "detail": detail,
            "risk": risk,
            "sender": frm,
            "approach": (
                "Real Wells alerts come from alerts@notify.wellsfargo.com — still use the "
                "official login link above, never a link inside the email body. "
                "Phishing copies urgency but uses wrong domains or asks for credentials in-reply."
            ),
        }

    if "forwarding-noreply@google.com" in frm or "gmail forwarding confirmation" in subj:
        emails = re.findall(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", subj + " " + snip)
        fwd_links = []
        for em in emails:
            if "google.com" not in em and "gmail" not in em:
                fwd_links.append(
                    f'<a href="{URLS["gmail_fwd"].format(email=_esc(em))}">→ {_esc(em)} forwarding</a>'
                )
        if not fwd_links:
            fwd_links = [
                f'<a href="{URLS["gmail_fwd"].format(email="ianm.powercore@gmail.com")}">→ hub mailbox forwarding</a>'
            ]
        return {
            "emoji": "📬",
            "title": "GMAIL FORWARDING",
            "extra_links": fwd_links,
            "detail": "Forwarding confirmation pending — revoke if you did not start this.",
            "risk": "Live intercept of mail and password-reset tokens.",
            "sender": frm,
            "approach": (
                "Google sends these from forwarding-noreply@google.com when someone adds a forward. "
                "Legit if you set it up; if not, treat as account compromise and revoke immediately."
            ),
        }

    if "noreply@github.com" in frm and ("oauth" in blob or "third-party" in blob):
        return {
            "emoji": "🔑",
            "title": "APP ACCESS",
            "action": "→ GitHub Applications",
            "url": URLS["github_apps"],
            "detail": "Third-party OAuth app authorized on GitHub.",
            "risk": "Persistent repo access without your password.",
            "sender": frm,
            "approach": (
                "GitHub notifies from noreply@github.com for real OAuth grants. "
                "Revoke apps you do not recognize at GitHub → Settings → Applications."
            ),
        }

    if "noreply-accounts@google.com" in frm or ("shared" in blob and "google" in blob):
        return {
            "emoji": "🔑",
            "title": "APP ACCESS",
            "action": "→ Google connections",
            "url": URLS["google_connections"],
            "detail": (msg.get("subject") or "Google account data shared with a third party.")[:140],
            "risk": "Third-party sign-in can read profile data until revoked.",
            "sender": frm,
            "approach": (
                "Google sends these from noreply-accounts@google.com when you use Sign in with Google. "
                "Legit if you just signed into that site; otherwise revoke at connections."
            ),
        }

    if "stripe.com" in frm or ("payment" in blob and "failed" in blob) or "cursor" in blob:
        url = URLS["cursor_billing"] if "cursor" in blob else URLS["stripe_billing"]
        return {
            "emoji": "💳",
            "title": "PAYMENT FAILED",
            "action": "→ Fix billing",
            "url": url,
            "detail": (msg.get("subject") or "Subscription payment failed.")[:140],
            "risk": "Service interruption if unpaid.",
            "sender": frm,
        }

    if "payoneer" in frm:
        return {
            "emoji": "💳",
            "title": "PAYONEER",
            "action": "→ Payoneer login",
            "url": URLS["payoneer"],
            "detail": (msg.get("subject") or "Payoneer account notice.")[:140],
            "risk": "Complete any pending verification.",
            "sender": frm,
        }

    if "rentcafe" in frm or "yardi" in frm or "housing" in subj:
        return {
            "emoji": "🏠",
            "title": "HOUSING",
            "action": "→ SCCHA RentCafe portal",
            "url": URLS["sccha"],
            "detail": (msg.get("subject") or "Housing portal update.")[:140],
            "risk": "Confirm changes were authorized.",
            "sender": frm,
        }

    if "proton" in frm and "unread" in snip:
        return None  # waiting section

    # Security-ish catch-all from money bucket
    sec_words = ("security", "verify", "unauthorized", "password reset", "sign-in", "login attempt")
    if any(w in blob for w in sec_words):
        url = URLS["google_connections"] if "google" in frm else None
        return {
            "emoji": "🔑",
            "title": "SECURITY",
            "action": "→ Review account" if url else None,
            "url": url,
            "detail": (msg.get("subject") or "Security-related notice.")[:140],
            "risk": "Confirm this was you.",
            "sender": frm,
            "approach": "When unsure, open the official site manually — do not trust in-email links.",
        }

    if "invoice" in blob or "deadline" in blob or "action required" in blob:
        return {
            "emoji": "📋",
            "title": "ACTION REQUIRED",
            "detail": (msg.get("subject") or "")[:140],
            "risk": "Due soon or billing-related.",
            "sender": frm,
        }

    return None


def _collect_messages(payload: dict) -> list[tuple[int, dict]]:
    """(priority, msg) lower priority number = higher rank."""
    gmail = payload.get("gmail") or {}
    ranked: list[tuple[int, dict]] = []
    order = (
        ("money_3d", 0),
        ("unread_2d", 1),
        ("inbox_1d", 2),
        ("starred_7d", 3),
    )
    seen: set[str] = set()
    for key, pri in order:
        block = gmail.get(key) or {}
        msgs = block.get("messages") if isinstance(block.get("messages"), list) else []
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            fp = str(msg.get("threadId") or msg.get("id") or "")
            if not fp or fp in seen:
                continue
            seen.add(fp)
            ranked.append((pri, msg))
    ranked.sort(key=lambda t: t[0])
    return ranked


def _count_dropped(gmail: dict) -> int:
    n = 0
    for key in ("inbox_1d", "unread_2d"):
        block = gmail.get(key) or {}
        msgs = block.get("messages") if isinstance(block.get("messages"), list) else []
        for msg in msgs:
            if isinstance(msg, dict) and set(msg.get("labels") or []) & DROP_LABELS:
                n += 1
    return n


def _format_calendar(payload: dict) -> list[str]:
    lines: list[str] = []
    cal = payload.get("calendar") if isinstance(payload.get("calendar"), list) else []
    analysis = payload.get("calendar_analysis") or {}
    for o in analysis.get("overlaps") or []:
        lines.append(f"<b>overlap</b> · {_esc(o)}")
    for t in analysis.get("tight_gaps") or []:
        lines.append(f"<b>tight</b> · {_esc(t)}")
    if analysis.get("tentative"):
        lines.append("<b>tentative</b> · " + ", ".join(_esc(x) for x in analysis["tentative"]))
    timed = []
    for e in cal:
        if not isinstance(e, dict):
            continue
        start = e.get("start") or ""
        if "T" in start:
            timed.append((start, e.get("summary") or "(no title)"))
    timed.sort()
    for start, name in timed:
        lines.append(f"{_esc(name)}")
    if not lines:
        lines.append("<i>No timed events.</i>")
    return lines


def _format_waiting(ranked: list[tuple[int, dict]]) -> list[str]:
    waiting: list[str] = []
    for _, msg in ranked:
        frm = _email_addr(msg.get("from", ""))
        subj = (msg.get("subject") or "").lower()
        if "proton" in frm:
            m = re.search(r"(\d+)\s+unread", (msg.get("snippet") or "").lower())
            n = m.group(1) if m else "?"
            waiting.append(f'<a href="{URLS["proton"]}">Proton · {n} unread</a>')
        elif "experian" in frm or "experian" in subj:
            waiting.append(f"{_esc(msg.get('subject', 'Experian notice')[:80])}")
    return waiting[:3]


def format_digest(payload: dict) -> str:
    now = datetime.now(TZ)
    weekday = now.strftime("%a %d %b")
    island = payload.get("island_health") or {}
    island_txt = "island OK" if island.get("ok") else "island DOWN"

    if not payload.get("auth_ok"):
        auth = _esc(str(payload.get("auth_check") or "Gmail auth failed")[:200])
        return (
            f"<b>DIGEST</b> — {weekday} PT\n"
            f"0 meetings · 1 to handle · {island_txt}\n\n"
            f"📋 <blockquote><b>TO HANDLE</b></blockquote>\n"
            f"<blockquote><b>PROBE FAIL — Gmail</b></blockquote>\n"
            f"<code>{auth}</code>"
        )

    days_map = _days_open_map(payload.get("follow_through") or [])
    ranked = _collect_messages(payload)
    cards: list[str] = []
    used_titles: set[str] = set()

    for _, msg in ranked:
        spec = _classify(msg)
        if not spec:
            continue
        title_key = spec["title"]
        if title_key in used_titles:
            continue
        used_titles.add(title_key)

        emoji = spec["emoji"]
        title = spec["title"]
        sender = _esc(spec.get("sender") or _email_addr(msg.get("from", "")))
        open_pre = _open_tag(msg, days_map)

        block = [f'{emoji} <blockquote><b>{title}</b></blockquote>']
        if spec.get("url") and spec.get("action"):
            block.append(f'<a href="{spec["url"]}">{_esc(spec["action"])}</a>')
        for link in spec.get("extra_links") or []:
            block.append(link)
        block.append(f"{open_pre}<code>{sender}</code>")
        if spec.get("detail"):
            block.append(_esc(spec["detail"]))
        if spec.get("risk"):
            block.append(f"Risk: {_esc(spec['risk'])}")
        if spec.get("approach"):
            block.append(f'<blockquote expandable><b>Approach</b>\n{_esc(spec["approach"])}</blockquote>')
        cards.append("\n".join(block))
        if len(cards) >= 6:
            break

    cal_lines = _format_calendar(payload)
    waiting = _format_waiting(ranked)
    dropped = _count_dropped(payload.get("gmail") or {})

    n_meetings = len([e for e in (payload.get("calendar") or []) if isinstance(e, dict) and "T" in (e.get("start") or "")])
    header = (
        f"<b>DIGEST</b> — {weekday} PT\n"
        f"{n_meetings} meetings · {len(cards)} to handle · {island_txt}\n"
    )

    parts = [header, "📋 <blockquote><b>TO HANDLE</b></blockquote>"]
    if cards:
        parts.append("\n\n".join(cards))
    else:
        parts.append("<i>none</i>")

    parts.append("\n📅 <blockquote><b>TODAY</b></blockquote>\n" + "\n".join(cal_lines))

    if waiting:
        parts.append("📥 Waiting — " + " · ".join(waiting))
    else:
        parts.append("📥 Waiting — <i>none</i>")

    parts.append(f"🧹 Dropped — {dropped} promos / newsletters / dupes")
    return "\n\n".join(parts)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        payload = _run_fetch()
        print(format_digest(payload))
        return 0
    except Exception as e:
        print(
            f"<b>DIGEST</b> — error\n\n"
            f"PROBE <blockquote><b>SCRIPT FAIL</b></blockquote>\n"
            f"<code>{_esc(str(e)[:400])}</code>"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
