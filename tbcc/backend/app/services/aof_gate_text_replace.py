"""Replace stale gates (work.ink, /dynamic LV) with manual Post & earn slugs in post HTML."""

from __future__ import annotations

import json
import re
from html import escape, unescape
from urllib.parse import urlparse

from app.data.aof_manual_gate_links import (
    ANCHOR_TEXT_TO_GATE_KEY,
    manual_gate_url,
    manual_gate_urls,
)
from app.services.link_gate_provider import GATE_HOST_SUFFIXES, is_gate_host, is_linkvertise_host

_ANCHOR_RE = re.compile(
    r'<a\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.I)


def _is_stale_gate_url(url: str) -> bool:
    u = (url or "").strip().split()[0]
    if not u.startswith("http"):
        return False
    if "work.ink" in u:
        return True
    if is_linkvertise_host(u) and "/dynamic" in u.lower():
        return True
    if is_linkvertise_host(u):
        # Replace any LV slug not in our canonical manual set.
        from app.data.aof_manual_gate_links import all_manual_gate_urls

        return u not in all_manual_gate_urls()
    host = (urlparse(u).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in GATE_HOST_SUFFIXES if s != "work.ink")


def _gate_key_for_anchor(anchor_html: str) -> str | None:
    plain = re.sub(r"<[^>]+>", "", anchor_html or "")
    low = unescape(plain).strip().lower()
    for fragment, key in ANCHOR_TEXT_TO_GATE_KEY:
        if fragment in low:
            return key
    return None


def _gate_key_for_context(context: str) -> str | None:
    low = unescape(re.sub(r"<[^>]+>", " ", context or "")).lower()
    for fragment, key in ANCHOR_TEXT_TO_GATE_KEY:
        if fragment in low:
            return key
    for key in (
        "blowjob",
        "big_tits",
        "voyeur",
        "milf",
        "taboo",
        "abg",
        "goon",
        "bop",
        "packs",
        "loot",
        "mainhub",
        "main_group",
        "ai",
        "ass",
    ):
        label = key.replace("_", " ")
        if f"aof {label}" in low or label in low:
            return key
    return None


def replace_stale_gates_in_text(text: str, gates: dict[str, str] | None = None) -> tuple[str, int]:
    """Swap work.ink / dynamic LV / unknown LV slugs using anchor hints + canonical map."""
    if not text:
        return text or "", 0
    gates = gates or manual_gate_urls()
    changes = 0
    out = text

    def _sub_anchor(m: re.Match[str]) -> str:
        nonlocal changes
        href = m.group(1).strip()
        anchor = m.group(2)
        if not _is_stale_gate_url(href):
            return m.group(0)
        key = _gate_key_for_anchor(anchor)
        if key and gates.get(key):
            changes += 1
            return f'<a href="{escape(gates[key], quote=True)}">{anchor}</a>'
        return m.group(0)

    out = _ANCHOR_RE.sub(_sub_anchor, out)

    # Bare work.ink / unknown LV slugs — use surrounding caption context.
    for match in list(re.finditer(r"https://work\.ink[^\s\]\)<>\"']+", out, re.I)):
        old = match.group(0)
        if not _is_stale_gate_url(old):
            continue
        start = max(0, match.start() - 400)
        end = min(len(out), match.end() + 120)
        key = _gate_key_for_context(out[start:end])
        if key and gates.get(key):
            out = out.replace(old, gates[key], 1)
            changes += 1

    for match in list(_URL_RE.finditer(out)):
        old = match.group(0)
        if not _is_stale_gate_url(old) or "work.ink" in old:
            continue
        start = max(0, match.start() - 400)
        end = min(len(out), match.end() + 120)
        key = _gate_key_for_context(out[start:end])
        if key and gates.get(key):
            out = out.replace(old, gates[key], 1)
            changes += 1

    return out, changes


def replace_stale_gates_in_buttons(buttons_json: str | None, gates: dict[str, str] | None = None) -> tuple[str | None, int]:
    if not buttons_json:
        return buttons_json, 0
    gates = gates or manual_gate_urls()
    changes = 0
    try:
        btns = json.loads(buttons_json)
    except json.JSONDecodeError:
        return buttons_json, 0
    if not isinstance(btns, list):
        return buttons_json, 0

    label_map = {
        "full stack addlist": "addlist",
        "addlist": "addlist",
        "download pack": None,
        "loot room": None,
        "aof packs": "packs",
    }

    for row in btns:
        if not isinstance(row, list):
            continue
        for b in row:
            if not isinstance(b, dict):
                continue
            u = (b.get("url") or "").strip()
            if not _is_stale_gate_url(u):
                continue
            label = (b.get("text") or "").strip().lower()
            key = None
            for frag, k in label_map.items():
                if frag in label:
                    key = k
                    break
            if key and gates.get(key):
                b["url"] = gates[key]
                changes += 1
            elif "download" not in label:
                # Network promo buttons without a label match -> default public gate.
                b["url"] = gates.get("main_group", u)
                changes += 1
    return json.dumps(btns), changes
