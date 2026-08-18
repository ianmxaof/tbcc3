"""Behavioral scripts + symmetry filter for secretary replies.

Noise/intro replies come from this corpus (not the LLM) so Auto cannot loop
subscription FAQ-speak. FAQ/buyer still use the LLM, then this module sanitizes.
"""

from __future__ import annotations

import re

from app.services.secretary_intent import IntentLane, classify_intent

_SIGNATURE_RE = re.compile(
    r"\s*(?:AOF\s+SECRETARY\s*,?\s*\d{1,2}:\d{2})?\s*$",
    re.I,
)
_ASSIST_RE = re.compile(
    r"(i'?m here to (?:help|assist)[^.!?]*[.!]?\s*)",
    re.I,
)
_HELP_LOOP = (
    "if you have questions about our services or subscriptions",
    "feel free to ask",
    "i'm here to assist you with any questions",
    "how can i assist you",
    "how can i help you today",
    "i appreciate you reaching out",
    "i appreciate your interest",
)


def payment_lane(phase: str | None, *, message_count: int = 0) -> str:
    """stars = initial qualification; private = Zelle/crypto after trust/recovery."""
    p = (phase or "introduction").lower()
    if p in ("support", "recovery") or message_count >= 5:
        return "private"
    return "stars"


def apply_symmetry(user_text: str, reply: str, *, variant: str = "natural") -> str:
    """N tracks user length; C/X get a slightly looser cap."""
    cleaned = sanitize_reply(reply)
    uw = max(1, len((user_text or "").split()))
    if variant == "natural":
        max_words = 6 if uw <= 3 else min(18, uw + 4)
        max_chars = 80 if uw <= 3 else 220
    elif variant == "close":
        max_words = min(22, max(8, uw + 10))
        max_chars = 220
    else:
        max_words = min(28, max(10, uw * 3))
        max_chars = 260
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,;") + "."
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned.strip()


def sanitize_reply(text: str) -> str:
    raw = (text or "").strip()
    raw = raw.strip('"“”')
    raw = _SIGNATURE_RE.sub("", raw).strip()
    # Drop a leading quoted echo of the user line.
    raw = re.sub(r'^["“].{0,80}["”]\s*', "", raw)
    for phrase in _HELP_LOOP:
        if phrase in raw.lower():
            raw = re.sub(re.escape(phrase), "", raw, flags=re.I)
    raw = _ASSIST_RE.sub("", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -")
    return raw


def corpus_candidates(
    user_text: str,
    *,
    intent: IntentLane | None = None,
    phase: str = "introduction",
    message_count: int = 0,
    payment_bot: str = "aofsubscriptions_bot",
) -> dict[str, str] | None:
    """Return N/C/X from scripts when the LLM should stay out. None = use LLM."""
    lane = intent or classify_intent(user_text)
    pay = (payment_bot or "aofsubscriptions_bot").lstrip("@")
    lowered = (user_text or "").lower()
    if lane != "noise":
        return None

    if any(
        s in lowered
        for s in ("link", "colleague", "block", "xpaja", "leakgallery", "anchor", "homepage")
    ):
        return {
            "natural": "not buying links.",
            "clear": "we don't buy homepage slots.",
            "close": "no thanks.",
        }

    # Greeting / short noise
    n = "hey" if len((user_text or "").split()) <= 2 else "what's this about"
    return {
        "natural": n,
        "clear": "yeah?",
        "close": "what's up",
    }


def behavior_suffix(
    *,
    intent: IntentLane,
    phase: str,
    message_count: int,
    payment_bot: str,
) -> str:
    lane = payment_lane(phase, message_count=message_count)
    pay = (payment_bot or "aofsubscriptions_bot").lstrip("@")
    lines = [
        f"Intent lane: {intent} (noise=dry/drop; faq=facts; buyer=close).",
        "Never sign messages. Never quote the user. Never say you are here to help with subscriptions.",
        "Talk like a person in Telegram DMs. No corporate support voice.",
    ]
    if intent == "noise":
        lines.append("Do not pitch checkout. Do not mention the payment bot unless they ask to buy.")
    elif lane == "private":
        lines.append(
            "Payment context: private/discreet — they can ask the operator about Zelle or crypto. "
            f"Do not dump Stars SKUs. Payment bot @{pay} only if they insist on in-app checkout."
        )
    else:
        lines.append(
            f"Payment context: initial — Stars checkout in @{pay} (/subscribe /packs). "
            "One mention max. No SKU dump unless they ask price."
        )
    return "\n".join(lines)
