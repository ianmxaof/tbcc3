"""Placement + cannibalization guards for prompt_gate SKUs (v1 doctrine).

Telegram: one Linkvertise destination per message; channel manual gate OR prompt_gate Text slug, never both.
Checkout + goblin claim URLs must never be wrapped behind a gate.
X/IG: no Linkvertise hosts when ``TBCC_X_USE_LINKVERTISE=0`` (default).
"""

from __future__ import annotations

import re
from typing import Iterable

from app.services.aof_loot_goblin_promo import PROMPT_DROP_MARKER
from app.services.link_gate_provider import is_gate_host, is_linkvertise_host

_URL_RE = re.compile(r"https?://[^\s<>\"'\)]+", re.I)

_LV_HOST_RE = re.compile(
    r"link-center\.net|direct-link\.net|link-hub\.net|link-target\.net|linkvertise",
    re.I,
)

_PROTECTED_CLEARNET_RE = re.compile(
    r"(?:start=loot_free|start=loot|start=subscribe|start=cm\d+|aofsubscriptions_bot|aof_lootgod_bot)",
    re.I,
)

VIOLATION_DUAL_LV = "dual_lv_destination"
VIOLATION_CHANNEL_GATE_AND_PROMPT = "channel_gate_with_prompt_drop"
VIOLATION_GATE_PROTECTED_URL = "gated_protected_checkout_or_claim"
VIOLATION_LV_ON_X = "lv_host_on_x_surface"

FOOTER_MARKER = "Join the full AOF stack"
_GATE_ANCHOR_RE = re.compile(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', re.I)


def extract_urls(text: str) -> list[str]:
    return [m.group(0).rstrip(".,;)") for m in _URL_RE.finditer(text or "")]


def linkvertise_urls_in_text(text: str) -> list[str]:
    return [u for u in extract_urls(text) if is_linkvertise_host(u)]


def gate_urls_in_text(text: str) -> list[str]:
    return [u for u in extract_urls(text) if is_gate_host(u)]


def is_protected_clearnet_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or is_gate_host(u):
        return False
    return bool(_PROTECTED_CLEARNET_RE.search(u))


def is_prompt_drop_message(text: str) -> bool:
    return PROMPT_DROP_MARKER in (text or "")


def _channel_gate_urls(channel_gate_urls: Iterable[str] | None) -> set[str]:
    if channel_gate_urls is not None:
        return {u.strip().split()[0] for u in channel_gate_urls if (u or "").strip()}
    from app.data.aof_manual_gate_links import all_manual_gate_urls

    return set(all_manual_gate_urls())


def _gated_protected_anchor_violations(body: str) -> bool:
    for m in _GATE_ANCHOR_RE.finditer(body or ""):
        href = (m.group(1) or "").strip()
        anchor = (m.group(2) or "").strip()
        if is_gate_host(href) and is_protected_clearnet_url(anchor):
            return True
    return False


def telegram_placement_violations(
    text: str,
    *,
    channel_gate_urls: Iterable[str] | None = None,
    footer_marker: str = FOOTER_MARKER,
) -> list[str]:
    """Return machine-readable violation codes for Telegram caption HTML."""
    violations: list[str] = []
    body = text or ""
    lv_urls = linkvertise_urls_in_text(body)

    if len(lv_urls) > 1:
        violations.append(VIOLATION_DUAL_LV)

    if _gated_protected_anchor_violations(body):
        violations.append(VIOLATION_GATE_PROTECTED_URL)

    if not is_prompt_drop_message(body):
        return violations

    manual_gates = _channel_gate_urls(channel_gate_urls)
    prompt_lv = set(lv_urls)
    manual_in_body = {g for g in manual_gates if g in body}

    if manual_in_body - prompt_lv:
        violations.append(VIOLATION_CHANNEL_GATE_AND_PROMPT)
    elif footer_marker in body and manual_in_body and prompt_lv:
        violations.append(VIOLATION_CHANNEL_GATE_AND_PROMPT)

    return violations


def x_placement_violations(text: str) -> list[str]:
    """Block Linkvertise hosts on X/IG when TBCC_X_USE_LINKVERTISE is off."""
    from app.services.aof_social_links import x_linkvertise_enabled

    if x_linkvertise_enabled():
        return []
    if _LV_HOST_RE.search(text or ""):
        return [VIOLATION_LV_ON_X]
    return []


def telegram_placement_ok(text: str, **kwargs) -> bool:
    return not telegram_placement_violations(text, **kwargs)


def x_placement_ok(text: str) -> bool:
    return not x_placement_violations(text)


def assert_telegram_placement_ok(text: str, **kwargs) -> None:
    violations = telegram_placement_violations(text, **kwargs)
    if violations:
        raise ValueError(f"telegram placement violation: {', '.join(violations)}")


def validate_prompt_drop_html(html: str) -> None:
    """Prompt-drop rows must ship exactly one LV slug and no channel-gate cannibalization."""
    assert_telegram_placement_ok(html, channel_gate_urls=())
    if len(linkvertise_urls_in_text(html)) != 1:
        raise ValueError("prompt drop must contain exactly one Linkvertise URL")
