"""CLIP catalog slugs + caption fragments -> AOF content-lane network keys.

Frozen high-confidence mapping (gatekeeper-lane-split-train Phase 1). The
raw ``tbcc/data/clip-categories.json`` catalog has ~1260 generic slugs
(``just-boobs``, ``thick-booty``, ...) that do not match AOF ``network_key``
values. ``CLIP_SLUG_TO_LANE`` maps the obvious high-volume slugs onto the
11 AOF split lanes; anything unmapped falls back to a fragment match
against ``LANE_TAG_MAP``. See ``docs/MEDIA_GATEKEEPER.md`` and
``docs/handoffs/2026-08-17_gatekeeper-lane-split-train.md`` (locked design).
"""

from __future__ import annotations

import re

from app.data.aof_storage_hub_map import CONTENT_LANE_NETWORK_KEYS
from app.services.aof_lane_tag_map import LANE_TAG_MAP

# Mixed-bulk split targets — hub content lanes minus inbox (the source) and
# packs (mega/link parcels, not visually classifiable feed media).
SPLIT_LANE_KEYS: frozenset[str] = frozenset(CONTENT_LANE_NETWORK_KEYS - {"inbox", "packs"})

CLIP_SLUG_TO_LANE: dict[str, tuple[str, ...]] = {
    # ass
    "thick-booty": ("ass",),
    "big-asses": ("ass",),
    "bubble-butt": ("ass",),
    "ass-clap": ("ass",),
    "cute-butts": ("ass",),
    "phat-ass-white-girls": ("ass",),
    "sexy-ass": ("ass",),
    "thick-ass": ("ass",),
    "ass-worship": ("ass",),
    "natural-ass": ("ass",),
    "spread-ass": ("ass",),
    "gaping-ass": ("ass",),
    "pawg-squirters": ("ass",),
    "ass-licking": ("ass",),
    "badonkadonk-big-ebony-ass": ("ass",),
    "jav-big-butt": ("ass",),
    # big_tits
    "just-boobs": ("big_tits",),
    "big-tits": ("big_tits",),
    "tittydrop": ("big_tits",),
    "natural-tits": ("big_tits",),
    "natural-big-tits": ("big_tits",),
    "perfect-tits": ("big_tits",),
    "busty-sluts": ("big_tits",),
    "boobs": ("big_tits",),
    "girls-with-big-natural-tits": ("big_tits",),
    "big-boob-drop": ("big_tits",),
    "busty-petite": ("big_tits",),
    # blowjob
    "blowjobs": ("blowjob",),
    "blowjob": ("blowjob",),
    "throated": ("blowjob",),
    "deep-throat": ("blowjob",),
    "deepthroat": ("blowjob",),
    "oral-sex": ("blowjob",),
    "oral": ("blowjob",),
    "blowjob-pov": ("blowjob",),
    "amateur-blowjobs": ("blowjob",),
    "blowjob-cumshot": ("blowjob",),
    # milf
    "milf": ("milf",),
    "milfs-over-30": ("milf",),
    "slutty-milfs": ("milf",),
    "horny-cougars": ("milf",),
    "cougars": ("milf",),
    "mature": ("milf",),
    "sexy-milfs": ("milf",),
    "blonde-milf": ("milf",),
    "mom": ("milf",),
    "hot-mom": ("milf",),
    "mature-sex": ("milf",),
    # voyeur
    "voyeur": ("voyeur",),
    "upskirt": ("voyeur",),
    "public-nudity": ("voyeur",),
    "public-sex": ("voyeur",),
    "public-flashing": ("voyeur",),
    "exposed-in-public": ("voyeur",),
    "voyeur-sex": ("voyeur",),
    "upskirt-tease": ("voyeur",),
    "nude-in-public": ("voyeur",),
    "solo-public": ("voyeur",),
    # taboo
    "stepsis": ("taboo",),
    "step-fantasy": ("taboo",),
    # goon
    "goon": ("goon",),
    "edging": ("goon",),
    "jerk-off-instructions": ("goon",),
    "joi-jerk-off-instructions": ("goon",),
    "goon-captions": ("goon",),
    "jerk-my-cock": ("goon",),
    # ai (hentai / animated / deepfake — not real people)
    "hentai": ("ai",),
    "3d-hentai": ("ai",),
    "animated-hentai": ("ai",),
    "hentai-sex": ("ai",),
    "cartoon-sex": ("ai",),
    "animated-sex": ("ai",),
    "hanime": ("ai",),
    "western-hentai": ("ai",),
    "anime-hentai": ("ai",),
    "genshin-impact-hentai": ("ai",),
    # abg (ABG/LBFM — Asian)
    "asian": ("abg",),
    "asian-babe": ("abg",),
    "asian-girls": ("abg",),
    "busty-asians": ("abg",),
    "korean-nsfw": ("abg",),
    "japanese-nsfw": ("abg",),
    "petite-asians": ("abg",),
    "asian-amateur": ("abg",),
    # full_length
    "compilations": ("full_length",),
    "compilation": ("full_length",),
    "cumshot-compilation": ("full_length",),
    "orgasm-compilation": ("full_length",),
    "masturbation-compilation": ("full_length",),
    "creampie-compilation": ("full_length",),
    # bop
    "nude-dancers": ("bop",),
    "sex-dance": ("bop",),
    "twerking": ("bop",),
    "twerking-ass": ("bop",),
}


def _merge_corpus_clip_slug_aliases() -> None:
    """Layer first-party tag_corpus.json aliases onto CLIP_SLUG_TO_LANE (additive —
    never overwrites a hand-curated entry above). Keeps this map, LANE_TAG_MAP, and
    the vision-LLM prompt cues aligned to one source instead of three divergent
    hand-maintained lists. See app/services/tag_corpus.py.
    """
    try:
        from app.services.tag_corpus import clip_slug_aliases_for_lane

        for lane in SPLIT_LANE_KEYS:
            for slug, lanes in clip_slug_aliases_for_lane(lane).items():
                CLIP_SLUG_TO_LANE.setdefault(slug, lanes)
    except Exception:
        pass


_merge_corpus_clip_slug_aliases()

_TOKEN_RE = re.compile(r"#?(\w+)", re.UNICODE)

# LANE_TAG_MAP has 2-3 letter fragments ("ai", "bj", "bop", "ass") that are
# plain English substrings ("waiting", "abject", "captain"...). A bare
# `fragment in text` check false-positives on ordinary captions — guard
# short fragments with a word boundary; longer fragments keep substring
# matching (e.g. "curvy" should still hit "curvyness").
_SHORT_FRAGMENT_LEN = 4


def _fragment_pattern(fragment: str) -> re.Pattern[str]:
    escaped = re.escape(fragment)
    if len(fragment) < _SHORT_FRAGMENT_LEN:
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.UNICODE)
    return re.compile(escaped, re.UNICODE)


_FRAGMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    fragment: _fragment_pattern(fragment) for fragment in LANE_TAG_MAP
}


def _fragment_hit(fragment: str, text: str) -> bool:
    pattern = _FRAGMENT_PATTERNS.get(fragment) or _fragment_pattern(fragment)
    return bool(pattern.search(text))


def _normalize_slug(slug: str) -> str:
    return (slug or "").strip().lower().replace(" ", "-")


def map_clip_slugs_to_lanes(
    slugs: list[str], *, scores: dict[str, float] | None = None
) -> list[tuple[str, float]]:
    """Rank AOF split lanes implied by a list of CLIP catalog slugs.

    Direct ``CLIP_SLUG_TO_LANE`` hits win; unmapped slugs fall back to a
    fragment match against ``LANE_TAG_MAP``. ``scores`` (slug -> confidence,
    keyed by the raw or normalized slug) is optional — bare slug lists score
    1.0 per hit. Lanes outside ``SPLIT_LANE_KEYS`` are dropped.
    """
    scores = scores or {}
    lane_scores: dict[str, float] = {}
    for raw_slug in slugs or []:
        if not raw_slug:
            continue
        key = _normalize_slug(raw_slug)
        weight = float(scores.get(raw_slug, scores.get(key, 1.0)))
        lanes = CLIP_SLUG_TO_LANE.get(key)
        if not lanes:
            text = key.replace("-", " ")
            hit: set[str] = set()
            for fragment, mapped in LANE_TAG_MAP.items():
                if _fragment_hit(fragment, text):
                    hit.update(mapped)
            lanes = tuple(hit)
        for lane in lanes:
            if lane not in SPLIT_LANE_KEYS:
                continue
            if weight > lane_scores.get(lane, 0.0):
                lane_scores[lane] = weight
    return sorted(lane_scores.items(), key=lambda kv: kv[1], reverse=True)


def map_text_to_lanes(caption: str, filename: str = "") -> list[str]:
    """All plausible AOF split lanes from caption/filename hashtags — ranked, not just top-1.

    Uses a word-boundary-guarded scan of ``LANE_TAG_MAP`` directly rather than
    ``suggest_lane_keys_from_tags`` — that helper's ``token in fragment``
    fallback (built for short scrape hashtags) false-positives on ordinary
    caption sentences (e.g. "i think this is great" -> "abg").
    """
    text = f"{caption or ''}\n{filename or ''}".strip().lower()
    if not text:
        return []
    scores: dict[str, int] = {}
    for fragment, keys in LANE_TAG_MAP.items():
        if _fragment_hit(fragment, text):
            for k in keys:
                if k in SPLIT_LANE_KEYS:
                    scores[k] = scores.get(k, 0) + 1
    if not scores:
        return []
    return sorted(scores, key=lambda k: scores[k], reverse=True)


def caption_confidence(caption: str, filename: str = "") -> float:
    """1.0 exact hashtag/token in LANE_TAG_MAP, 0.55 fragment/contains match, 0.0 no match.

    Only counts a hit whose mapped lane(s) are actual split targets — a tag
    like ``#amateur`` or ``#packs`` resolves in ``LANE_TAG_MAP`` but has no
    AOF split lane, so it must not score as a confident (or any) proposal.
    """
    text = f"{caption or ''}\n{filename or ''}".strip().lower()
    if not text:
        return 0.0
    tokens = {m.group(1) for m in _TOKEN_RE.finditer(text)}
    for tok in tokens:
        keys = LANE_TAG_MAP.get(tok)
        if keys and any(k in SPLIT_LANE_KEYS for k in keys):
            return 1.0
    for fragment, keys in LANE_TAG_MAP.items():
        if any(k in SPLIT_LANE_KEYS for k in keys) and _fragment_hit(fragment, text):
            return 0.55
    return 0.0
