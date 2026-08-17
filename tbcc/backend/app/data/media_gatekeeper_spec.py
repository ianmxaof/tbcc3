"""Media Gatekeeper — frozen policy constants + pure evaluation (spec only; no worker).

See ``docs/MEDIA_GATEKEEPER.md`` for the full product bible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.data.aof_scrape_inbound_map import SKIP_INBOUND_CHAT_IDS
from app.services.aof_lane_tag_map import LANE_TAG_MAP, suggest_lane_keys_from_tags

Verdict = Literal["reject", "quarantine", "approve"]

# ---------------------------------------------------------------------------
# Threshold constants (locked defaults)
# ---------------------------------------------------------------------------

QUALITY_BASE_SCORE = 50
SCORE_APPROVE_MIN = 70
SCORE_QUARANTINE_MIN = 40


def hub_auto_approve_enabled() -> bool:
    """Trusted Storage Hub ingest may skip quarantine when score clears the hub threshold."""
    from app.services.hub_intake_policy import hub_master_auto_approve_enabled

    return hub_master_auto_approve_enabled()


def hub_auto_approve_min_score() -> int:
    """Min quality score for trusted hub auto-approve (default SCORE_APPROVE_MIN)."""
    import os

    raw = (os.getenv("TBCC_GATEKEEPER_HUB_AUTO_APPROVE_MIN") or "").strip()
    if raw:
        try:
            return max(SCORE_QUARANTINE_MIN, min(100, int(raw)))
        except ValueError:
            pass
    return SCORE_APPROVE_MIN


def hub_require_lane_detect_enabled() -> bool:
    """When true, hub imports with expected lane but no detected lane → quarantine (AI/inbox exempt)."""
    import os

    raw = (os.getenv("TBCC_GATEKEEPER_HUB_REQUIRE_LANE_DETECT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


# Lanes where uncaptioned / untagged media is expected (AI art, operator intake).
LANE_UNKNOWN_ALLOW_KEYS: frozenset[str] = frozenset({"ai", "inbox"})

PHOTO_MIN_SHORTEST_SIDE = 480
PHOTO_MIN_FILESIZE_BYTES = 200 * 1024
VIDEO_MIN_DURATION_SECONDS = 3.0
VERTICAL_VIDEO_MIN_SECONDS = 5.0
VERTICAL_VIDEO_MAX_SECONDS = 60.0
RESOLUTION_720P_MIN_SHORTEST_SIDE = 720
CAPTION_URL_SPAM_RATIO = 0.80

QUALITY_BOOST_VERTICAL_SHORT = 25
QUALITY_BOOST_TRUSTED_SOURCE = 20
QUALITY_BOOST_EXPLICIT = 15
QUALITY_BOOST_CLIP_LANE = 15
QUALITY_BOOST_HD = 10
QUALITY_BOOST_MODEL_HASHTAG = 10

QUALITY_PENALTY_LETTERBOX = 20
QUALITY_PENALTY_SUGGESTIVE_ONLY = 10
QUALITY_PENALTY_UNKNOWN_SOURCE = 5
QUALITY_PENALTY_LANE_UNKNOWN = 5

SOURCE_DEMOTE_REJECT_STREAK = 5  # documented; wiring next slice

NON_MEDIA_TYPES: frozenset[str] = frozenset(
    {"document", "sticker", "voice", "audio", "animation"}
)

# AOF-owned handles exempt from competitor watermark trash rule
AOF_WATERMARK_EXEMPT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"aofmainhub", re.I),
    re.compile(r"aof_lootgod", re.I),
    re.compile(r"aofsubscriptions", re.I),
    re.compile(r"telegram\.me_aof", re.I),
)

COMPETITOR_WATERMARK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"@onlyfans", re.I),
    re.compile(r"onlyfans\.com", re.I),
    re.compile(r"@fansly", re.I),
    re.compile(r"fansly\.com", re.I),
)

AGE_ADJACENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bunder\s*age\b", re.I),
    re.compile(r"\bunderage\b", re.I),
    re.compile(r"\bjail\s*bait\b", re.I),
    re.compile(r"\bjailbait\b", re.I),
    re.compile(r"\bloli\b", re.I),
    re.compile(r"\bshota\b", re.I),
    re.compile(r"\bpreteen\b", re.I),
    re.compile(r"\bpedo\b", re.I),
    re.compile(r"\bminor\b", re.I),
    re.compile(r"\b(1[0-7])\s*(yo|y/?o|years?\s*old)\b", re.I),
    re.compile(r"\bschool\s*girl\b", re.I),
    re.compile(r"\bteen\s*(seller|menu|proof)\b", re.I),
)

SELLER_PROOF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bseller\b", re.I),
    re.compile(r"\bproof\b", re.I),
    re.compile(r"\bverify\b", re.I),
    re.compile(r"\bverification\b", re.I),
    re.compile(r"\bmenu\b", re.I),
    re.compile(r"\brates\b", re.I),
    re.compile(r"\bprice\s*list\b", re.I),
    re.compile(r"\bage\s*check\b", re.I),
    re.compile(r"\bsocial\s*proof\b", re.I),
)

ZOO_KEYWORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbestiality\b", re.I),
    re.compile(r"\bzoophil", re.I),
    re.compile(r"\bzoophilia\b", re.I),
    re.compile(r"\bzooskool\b", re.I),
    re.compile(r"\bhorse\s*(fuck|sex)\b", re.I),
    re.compile(r"\bdog\s*(fuck|sex)\b", re.I),
)

MODEL_HASHTAG_RE = re.compile(r"#\w{3,30}", re.I)

_URL_TOKEN_RE = re.compile(
    r"https?://|t\.me/|telegram\.me/|@\w+|www\.\w+",
    re.I,
)

# Operator-extensible; starts empty beyond SKIP_INBOUND_CHAT_IDS
GATEKEEPER_BANNED_SOURCE_IDS: frozenset[int] = frozenset()


# ---------------------------------------------------------------------------
# Verdict types
# ---------------------------------------------------------------------------


@dataclass
class GlobResult:
    """Per-glob evaluation snapshot."""

    name: str
    pass_: bool
    flags: list[str] = field(default_factory=list)
    score_delta: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"pass": self.pass_, "flags": list(self.flags)}
        if self.score_delta:
            out["score_delta"] = self.score_delta
        out.update(self.extra)
        return out


@dataclass
class MediaVerdict:
    """Aggregate gatekeeper outcome — mirrors EromePolicyVerdict shape."""

    verdict: Verdict
    quality_score: int
    blocks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)
    globs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "quality_score": self.quality_score,
            "blocks": list(self.blocks),
            "warnings": list(self.warnings),
            "boosts": list(self.boosts),
            "globs": dict(self.globs),
        }


@dataclass
class MediaGatekeeperInput:
    """Pure inputs for evaluation — no DB required."""

    media_type: str = ""
    caption: str = ""
    filename: str = ""
    source_channel_id: int | None = None
    file_unique_id: str = ""
    expected_lane: str | None = None
    is_duplicate_in_pool: bool = False
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    filesize_bytes: int | None = None
    nsfw_tier: str | None = None
    clip_slug: str | None = None
    clip_confident: bool = False
    source_trusted: bool = False
    is_letterbox: bool = False


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------


def _haystack(caption: str, filename: str) -> str:
    return f"{caption or ''}\n{filename or ''}".strip()


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def is_age_adjacent(caption: str, filename: str) -> bool:
    return bool(_matches_any(_haystack(caption, filename), AGE_ADJACENT_PATTERNS))


def is_seller_proof(caption: str, filename: str) -> bool:
    return bool(_matches_any(_haystack(caption, filename), SELLER_PROOF_PATTERNS))


def is_zoo_keyword(caption: str, filename: str) -> bool:
    return bool(_matches_any(_haystack(caption, filename), ZOO_KEYWORD_PATTERNS))


def is_competitor_watermark(caption: str, filename: str) -> bool:
    text = _haystack(caption, filename)
    for exempt in AOF_WATERMARK_EXEMPT_PATTERNS:
        if exempt.search(text):
            return False
    return bool(_matches_any(text, COMPETITOR_WATERMARK_PATTERNS))


def caption_url_spam_ratio(caption: str) -> float:
    raw = (caption or "").strip()
    if not raw:
        return 0.0
    tokens = raw.split()
    if not tokens:
        return 0.0
    urlish = sum(1 for t in tokens if _URL_TOKEN_RE.search(t))
    return urlish / len(tokens)


def is_vertical_video(width: int | None, height: int | None) -> bool:
    if not width or not height or width <= 0 or height <= 0:
        return False
    return height > width


def shortest_side(width: int | None, height: int | None) -> int | None:
    if not width or not height:
        return None
    return min(width, height)


def detect_lane_from_text(caption: str, filename: str) -> str | None:
    """Best-effort lane key from hashtags/words via LANE_TAG_MAP."""
    text = _haystack(caption, filename).lower()
    scores: dict[str, int] = {}
    for fragment, keys in LANE_TAG_MAP.items():
        if fragment in text or f"#{fragment}" in text:
            for k in keys:
                scores[k] = scores.get(k, 0) + 1
    for key in suggest_lane_keys_from_tags(text, limit=1):
        scores[key] = scores.get(key, 0) + 1
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def has_model_hashtag(caption: str) -> bool:
    return bool(MODEL_HASHTAG_RE.search(caption or ""))


def clamp_score(score: int) -> int:
    return max(0, min(100, int(score)))


# ---------------------------------------------------------------------------
# Glob evaluators
# ---------------------------------------------------------------------------


def glob_hard_block(inp: MediaGatekeeperInput) -> GlobResult:
    flags: list[str] = []
    hay = _haystack(inp.caption, inp.filename)

    if inp.source_channel_id is not None:
        sid = int(inp.source_channel_id)
        from app.services.gatekeeper_source_demote import is_source_banned

        if sid in SKIP_INBOUND_CHAT_IDS or sid in GATEKEEPER_BANNED_SOURCE_IDS or is_source_banned(sid):
            flags.append("known_bad_source")

    if is_zoo_keyword(inp.caption, inp.filename):
        flags.append("zoo")

    if is_age_adjacent(inp.caption, inp.filename):
        flags.append("age_adjacent")

    if is_seller_proof(inp.caption, inp.filename):
        flags.append("seller_proof")

    # Screenshot-ish: tall aspect + seller language
    ss = shortest_side(inp.width, inp.height)
    if ss and inp.height and inp.width and inp.height > inp.width * 1.5:
        if is_seller_proof(inp.caption, inp.filename):
            flags.append("seller_screenshot")

    return GlobResult(
        name="hard_block",
        pass_=len(flags) == 0,
        flags=flags,
    )


def glob_trash(inp: MediaGatekeeperInput) -> GlobResult:
    flags: list[str] = []
    mt = (inp.media_type or "").strip().lower()

    if mt in NON_MEDIA_TYPES:
        flags.append(f"non_media:{mt}")

    if inp.is_duplicate_in_pool:
        flags.append("duplicate")

    if mt in ("photo", "gif"):
        ss = shortest_side(inp.width, inp.height)
        if ss is not None and ss < PHOTO_MIN_SHORTEST_SIDE:
            flags.append("photo_too_small")
        if inp.filesize_bytes is not None and inp.filesize_bytes < PHOTO_MIN_FILESIZE_BYTES:
            flags.append("photo_tiny_file")

    if mt == "video" and inp.duration_seconds is not None:
        if inp.duration_seconds < VIDEO_MIN_DURATION_SECONDS:
            flags.append("video_too_short")

    if caption_url_spam_ratio(inp.caption) >= CAPTION_URL_SPAM_RATIO:
        flags.append("caption_url_spam")

    if is_competitor_watermark(inp.caption, inp.filename):
        flags.append("competitor_watermark")

    return GlobResult(name="trash", pass_=len(flags) == 0, flags=flags)


def glob_lane_fit(inp: MediaGatekeeperInput) -> GlobResult:
    from app.data.clip_slug_lane_map import map_clip_slugs_to_lanes, map_text_to_lanes

    expected = (inp.expected_lane or "").strip().lower() or None
    detected = detect_lane_from_text(inp.caption, inp.filename)
    if inp.clip_confident and inp.clip_slug:
        clip_lane = inp.clip_slug.strip().lower().replace(" ", "_")
        detected = clip_lane if not detected else detected

    caption_lanes = map_text_to_lanes(inp.caption, inp.filename)
    clip_lanes = [lane for lane, _score in map_clip_slugs_to_lanes([inp.clip_slug])] if inp.clip_slug else []

    proposed_lanes: list[str] = []
    for lane in caption_lanes + clip_lanes:
        if lane not in proposed_lanes:
            proposed_lanes.append(lane)

    flags: list[str] = []
    if caption_lanes and clip_lanes and caption_lanes[0] != clip_lanes[0]:
        flags.append("lane_ambiguous")

    extra: dict[str, Any] = {"expected": expected, "detected": detected, "proposed_lanes": proposed_lanes}
    score_delta = 0

    # Mixed-bulk inbox: never fail lane_fit on untagged/ambiguous inbox media —
    # proposed_lanes carries the split signal for the inbox split helper instead.
    if not expected or expected == "inbox":
        return GlobResult(name="lane_fit", pass_=True, flags=flags, score_delta=0, extra=extra)

    if not detected:
        score_delta = -QUALITY_PENALTY_LANE_UNKNOWN
        flags.append("lane_unknown")
        if (
            expected
            and expected not in LANE_UNKNOWN_ALLOW_KEYS
            and hub_require_lane_detect_enabled()
        ):
            return GlobResult(
                name="lane_fit",
                pass_=False,
                flags=flags,
                score_delta=score_delta,
                extra=extra,
            )
        return GlobResult(name="lane_fit", pass_=True, flags=flags, score_delta=score_delta, extra=extra)

    if detected == expected:
        score_delta = QUALITY_BOOST_CLIP_LANE // 2  # lane match boost (half of CLIP boost)
        return GlobResult(name="lane_fit", pass_=True, flags=flags, score_delta=score_delta, extra=extra)

    flags.append("lane_mismatch")
    return GlobResult(name="lane_fit", pass_=False, flags=flags, score_delta=0, extra=extra)


def glob_quality(inp: MediaGatekeeperInput, lane_fit: GlobResult) -> GlobResult:
    score = QUALITY_BASE_SCORE
    boosts: list[str] = []
    flags: list[str] = []

    score += lane_fit.score_delta

    mt = (inp.media_type or "").strip().lower()
    if mt == "video" and inp.duration_seconds is not None:
        if (
            VERTICAL_VIDEO_MIN_SECONDS
            <= inp.duration_seconds
            <= VERTICAL_VIDEO_MAX_SECONDS
            and is_vertical_video(inp.width, inp.height)
        ):
            score += QUALITY_BOOST_VERTICAL_SHORT
            boosts.append("vertical_short_video")

    if inp.source_trusted:
        score += QUALITY_BOOST_TRUSTED_SOURCE
        boosts.append("trusted_source")
    else:
        score += -QUALITY_PENALTY_UNKNOWN_SOURCE
        flags.append("unknown_source")

    tier = (inp.nsfw_tier or "").strip().lower()
    if tier == "explicit":
        score += QUALITY_BOOST_EXPLICIT
        boosts.append("explicit_tier")
    elif tier == "suggestive":
        score += -QUALITY_PENALTY_SUGGESTIVE_ONLY
        flags.append("suggestive_only")

    if inp.clip_confident and inp.clip_slug and inp.expected_lane:
        clip_lane = inp.clip_slug.strip().lower().replace(" ", "_")
        if clip_lane == inp.expected_lane.strip().lower():
            score += QUALITY_BOOST_CLIP_LANE
            boosts.append("clip_lane_match")

    ss = shortest_side(inp.width, inp.height)
    if ss is not None and ss >= RESOLUTION_720P_MIN_SHORTEST_SIDE:
        score += QUALITY_BOOST_HD
        boosts.append("hd_resolution")

    if has_model_hashtag(inp.caption):
        score += QUALITY_BOOST_MODEL_HASHTAG
        boosts.append("model_hashtag")

    if inp.is_letterbox:
        score += -QUALITY_PENALTY_LETTERBOX
        flags.append("letterbox")

    final = clamp_score(score)
    return GlobResult(
        name="quality",
        pass_=final >= SCORE_QUARANTINE_MIN,
        flags=flags,
        score_delta=final - QUALITY_BASE_SCORE,
        extra={"score": final, "boosts": boosts},
    )


def glob_enrich(inp: MediaGatekeeperInput) -> GlobResult:
    return GlobResult(
        name="enrich",
        pass_=True,
        extra={
            "nsfw_tier": inp.nsfw_tier,
            "clip_slug": inp.clip_slug,
            "clip_confident": inp.clip_confident,
        },
    )


# ---------------------------------------------------------------------------
# Aggregate verdict
# ---------------------------------------------------------------------------


def aggregate_verdict(
    hard_block: GlobResult,
    trash: GlobResult,
    lane_fit: GlobResult,
    quality: GlobResult,
    enrich: GlobResult,
    *,
    source_trusted: bool,
) -> MediaVerdict:
    globs = {
        "hard_block": hard_block.to_dict(),
        "trash": trash.to_dict(),
        "lane_fit": lane_fit.to_dict(),
        "quality": quality.to_dict(),
        "enrich": enrich.to_dict(),
    }
    blocks: list[str] = []
    warnings: list[str] = []
    boosts: list[str] = []

    quality_score = int(quality.extra.get("score", QUALITY_BASE_SCORE))
    for b in quality.extra.get("boosts", []):
        boosts.append(f"quality:{b}")

    # --- hard overrides ---
    if "zoo" in hard_block.flags or "known_bad_source" in hard_block.flags:
        for f in hard_block.flags:
            blocks.append(f"hard_block:{f}")
        return MediaVerdict(
            verdict="reject",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    age_seller = any(
        f in hard_block.flags for f in ("age_adjacent", "seller_proof", "seller_screenshot")
    )
    if age_seller:
        for f in hard_block.flags:
            warnings.append(f"hard_block:{f}")

    if not trash.pass_:
        for f in trash.flags:
            blocks.append(f"trash:{f}")
        return MediaVerdict(
            verdict="reject",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    if not lane_fit.pass_:
        warnings.append("lane_fit:mismatch")

    # --- score bands ---
    if quality_score < SCORE_QUARANTINE_MIN:
        blocks.append("quality:below_quarantine_floor")
        return MediaVerdict(
            verdict="reject",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    if age_seller:
        return MediaVerdict(
            verdict="quarantine",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    if not lane_fit.pass_:
        return MediaVerdict(
            verdict="quarantine",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    if quality_score >= hub_auto_approve_min_score() and source_trusted and hub_auto_approve_enabled():
        return MediaVerdict(
            verdict="approve",
            quality_score=quality_score,
            blocks=blocks,
            warnings=warnings,
            boosts=boosts,
            globs=globs,
        )

    return MediaVerdict(
        verdict="quarantine",
        quality_score=quality_score,
        blocks=blocks,
        warnings=warnings,
        boosts=boosts,
        globs=globs,
    )


def evaluate_media(inp: MediaGatekeeperInput) -> MediaVerdict:
    """Run all globs and return aggregate verdict."""
    hb = glob_hard_block(inp)
    tr = glob_trash(inp)
    lf = glob_lane_fit(inp)
    qu = glob_quality(inp, lf)
    en = glob_enrich(inp)
    return aggregate_verdict(hb, tr, lf, qu, en, source_trusted=inp.source_trusted)


def merge_gatekeeper_json(existing: dict[str, Any] | None, verdict: MediaVerdict) -> dict[str, Any]:
    """Merge gatekeeper verdict into classification_json without wiping other keys."""
    base = dict(existing or {})
    base["gatekeeper"] = verdict.to_dict()
    return base
