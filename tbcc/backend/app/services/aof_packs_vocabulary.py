"""AOF PACKS copy vocabulary — block competitor parcel terms; AOF-native replacements."""

from __future__ import annotations

import hashlib
import re

# Competitor / borrowed parcel slang → never emit in captions or pack titles.
_BANNED_PACK_TERMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bbento\b", re.I), "__PARCEL_SYNONYM__"),
)

# AOF-native parcel descriptors (rotated deterministically per seed string).
PACK_PARCEL_SYNONYMS: tuple[str, ...] = (
    "batch",
    "thick rope",
    "wad",
    "parcel",
    "drop",
    "bundle",
)


def pick_pack_parcel_synonym(seed: str) -> str:
    raw = (seed or "aof-pack").strip().lower()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(PACK_PARCEL_SYNONYMS)
    return PACK_PARCEL_SYNONYMS[idx]


def _apply_synonym(match: re.Match[str], seed: str) -> str:
    word = match.group(0)
    syn = pick_pack_parcel_synonym(f"{seed}:{word.lower()}")
    if word.isupper():
        return syn.upper()
    if word[:1].isupper():
        return " ".join(part.capitalize() for part in syn.split())
    return syn


def sanitize_pack_copy(text: str | None, *, seed: str = "") -> str:
    """
    Remove competitor parcel vocabulary from pack labels, themes, and captions.
    Replaces e.g. 'ELITE BENTO PACKS' → 'ELITE Batch Packs' (synonym stable per seed).
    """
    out = re.sub(r"\s+", " ", (text or "").strip())
    if not out:
        return ""
    seed_key = (seed or out).strip()
    for pattern, replacement in _BANNED_PACK_TERMS:
        if replacement == "__PARCEL_SYNONYM__":
            out = pattern.sub(lambda m: _apply_synonym(m, seed_key), out)
        else:
            out = pattern.sub(replacement, out)
    out = re.sub(r"\s+", " ", out).strip()
    # Collapse awkward doubles after replacement.
    out = re.sub(r"\bpack\s+packs\b", "pack", out, flags=re.I)
    out = re.sub(r"\bpacks\s+packs\b", "packs", out, flags=re.I)
    return out.strip()
