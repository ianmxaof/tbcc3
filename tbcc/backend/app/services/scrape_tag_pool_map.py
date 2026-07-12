"""
Quick hashtag → AOF pool-key suggestions (no CLIP / NSFW / LLM).

Enable multi-pool robocopy later with TBCC_SCRAPE_HASHTAG_ROUTE=1 (stores primary pool
from Source; suggestions still recorded on ScrapeChannelProfile for operators).

Maps are intentionally small and keyword-based — prefer speed over recall.
"""

from __future__ import annotations

import re

# tag fragment (lowercase, no #) → AOF network keys (from aof_network)
# Multiple keys = candidate robocopy destinations.
HASHTAG_POOL_MAP: dict[str, tuple[str, ...]] = {
    # ABG / LBFM lane
    "malaysian": ("abg",),
    "malay": ("abg",),
    "indonesian": ("abg",),
    "indo": ("abg",),
    "thai": ("abg",),
    "vietnam": ("abg",),
    "vietnamese": ("abg",),
    "viet": ("abg",),
    "cambodian": ("abg",),
    "khmer": ("abg",),
    "filipina": ("abg",),
    "pinay": ("abg",),
    "asian": ("abg",),
    "abg": ("abg",),
    "lbfm": ("abg",),
    # Ass / curvy
    "ass": ("ass",),
    "booty": ("ass",),
    "pawg": ("ass",),
    "curvy": ("ass", "bigtits"),
    "thick": ("ass", "bigtits"),
    # Big tits
    "bigtits": ("bigtits",),
    "bigboobs": ("bigtits",),
    "boobs": ("bigtits",),
    "tits": ("bigtits",),
    "bustyy": ("bigtits",),
    "busty": ("bigtits",),
    # Cosplay / anime-adjacent
    "cosplay": ("cosplay",),
    "cosplayer": ("cosplay",),
    # Amateur
    "amateur": ("amateur",),
    "homemade": ("amateur",),
}

_TAG_RE = re.compile(r"#?([\w\u0080-\uFFFF]+)", re.UNICODE)


def normalize_tag_token(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("#"):
        s = s[1:]
    return s


def suggest_pool_keys_from_hashtags(tags: str | list[str] | None, *, limit: int = 6) -> list[str]:
    """Return ordered unique AOF pool keys suggested by hashtag sample."""
    tokens: list[str] = []
    if isinstance(tags, list):
        tokens = [normalize_tag_token(t) for t in tags]
    elif tags:
        for part in re.split(r"[,;\s]+", str(tags)):
            m = _TAG_RE.match(part.strip())
            if m:
                tokens.append(normalize_tag_token(m.group(1)))

    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        # exact then substring match against map keys
        keys = HASHTAG_POOL_MAP.get(tok)
        if not keys:
            for frag, mapped in HASHTAG_POOL_MAP.items():
                if frag in tok or tok in frag:
                    keys = mapped
                    break
        if not keys:
            continue
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
                if len(out) >= limit:
                    return out
    return out


def suggest_pool_keys_csv(tags: str | list[str] | None) -> str | None:
    keys = suggest_pool_keys_from_hashtags(tags)
    return ",".join(keys) if keys else None
