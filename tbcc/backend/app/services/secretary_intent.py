"""Intent gate for secretary — classify before sales coach (FE-v4 Phase 2).

Lanes: noise | faq | buyer
"""

from __future__ import annotations

import re

IntentLane = str  # noise | faq | buyer

_GREET_RE = re.compile(
    r"^(hi+|hey+|hello+|yo+|sup|what'?s up|hola|hiya|hi there|hello mate|hey mate)[\s!.?]*$",
    re.I,
)

_SOLICIT = (
    "homepage link",
    "buy links",
    "buying links",
    "anchor text",
    "xpaja",
    "leakgallery",
    "colleague",
    "who buys",
    "seo",
    "backlink",
    "why did you block",
    "why you block",
    "unblock",
)

_BUYER = (
    "how do i pay",
    "how to pay",
    "payment link",
    "i want to join",
    "i want to buy",
    "want to buy",
    "i want in",
    "subscribe",
    "invoice",
    "checkout",
    "buy vip",
    "buy pack",
    "stars",
    "zelle",
    "crypto",
    "i'll take it",
    "ill take it",
    "send the link",
)

_FAQ = (
    "how much",
    "price",
    "what do i get",
    "how does",
    "how do i",
    "vip",
    "pack",
    "access",
    "renew",
    "duration",
    "what's included",
    "whats included",
)


def classify_intent(user_text: str) -> IntentLane:
    raw = (user_text or "").strip()
    if not raw:
        return "noise"
    lowered = raw.lower()
    if _GREET_RE.match(raw) or len(raw.split()) <= 2 and lowered in {
        "hi", "hey", "hello", "yo", "sup", "ok", "okay", "?", "yes", "no",
    }:
        return "noise"
    if any(s in lowered for s in _SOLICIT):
        return "noise"
    if any(s in lowered for s in _BUYER):
        return "buyer"
    if any(s in lowered for s in _FAQ):
        return "faq"
    if len(raw.split()) <= 4 and not any(ch.isdigit() for ch in raw):
        return "noise"
    return "faq"


def intent_label(lane: IntentLane) -> str:
    return {
        "noise": "Noise / troll / solicitor",
        "faq": "FAQ / inquiry",
        "buyer": "High-intent buyer",
    }.get(lane, lane)
