"""Detect provider refusals / safety lectures so FE-LLMv4 can rotate hosts."""

from __future__ import annotations

import re

_REFUSAL_RES = (
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"\bi('m| am) (not able|unable|not allowed) to\b", re.I),
    re.compile(r"\bi cannot (assist|help|provide|engage)\b", re.I),
    re.compile(r"\bagainst (my|our) (guidelines|policies|programming)\b", re.I),
    re.compile(r"\bi (must|have to) decline\b", re.I),
    re.compile(r"\bcontent (policy|moderation)\b", re.I),
    re.compile(r"\bi won't (help|assist) with (that|this)\b", re.I),
    re.compile(r"\bsorry,? i can('t|not)\b", re.I),
)


def looks_like_refusal(text: str | None) -> bool:
    blob = (text or "").strip()
    if not blob:
        return True
    if len(blob) > 900:
        return False
    hits = sum(1 for rx in _REFUSAL_RES if rx.search(blob))
    return hits >= 1
