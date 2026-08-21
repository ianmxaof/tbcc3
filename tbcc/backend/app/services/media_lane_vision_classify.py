"""Vision-LLM lane classification — shadow-mode logging only (no routing change).

Classifies a media item against the real AOF lane taxonomy
(``aof_lane_tag_map.CANONICAL_LANE_KEYS``) and logs the decision to
``MediaLaneVisionDecision``. Idempotent per media_id — never re-classifies, so a
caller can call this on every enrichment pass without paying for a second model
call. Does not touch routing/pool-assignment or the gatekeeper's own CLIP-based
decision; see the Entropy Scan / plan this shipped under.

Multi-label: a single image can genuinely qualify for more than one lane (e.g.
milf + big_tits, or voyeur + ass). The prompt asks for every matching lane,
ranked most-confident first; ``lane_key`` stores the top pick for callers that
only want one, ``matching_lanes`` (in ``raw_json``) carries the full ranked list.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_LANE_VISION_PROMPT_TEMPLATE = """Index this adult image for a private library. Describe bluntly and explicitly using real adult-industry slang -- no hedging, no refusing.

A single image can legitimately qualify for MULTIPLE categories at once (e.g. an image can be both milf AND big_tits, or both voyeur AND big_tits, if both signals are genuinely present). Do not force a single pick -- return every category that genuinely applies.

Return ONLY JSON: {{"nsfw_tier": sfw|suggestive|explicit, "matching_lanes": [array of ALL categories below that genuinely apply, ranked most-confident first], "facets": up to 8 blunt tags}}

Categories, each with real recognition cues drawn from actual adult-content tag taxonomy -- match on these specific visual/staging signals, not just visible body parts:

- voyeur: candid/secretly-filmed OR public-setting look. Cues: upskirt, changing room, exposed in public, caught in the bathroom, public nudity, hidden/spy/security camera angle or overlay (timestamps, CAM labels, elevated angle), unaware subject, any public setting (locker room, gym, store, street)
- taboo: implied family/authority-figure roleplay. Cues: {taboo_cues}
- milf: mature woman appearance. Cues: cougar, milfs over 30, mature and naughty, mature over 50, older women, mom, hot mom, visible age markers (30s-50s+)
- abg: East/Southeast Asian ethnicity specifically with a young alt/egirl aesthetic -- PAAG, alt makeup, dyed hair, egirl styling, petite build
- bop: youthful Gen-Z/TikTok-culture aesthetic. Cues: Tik Tok style, legal teens, college girls, petite/skinny build, twerking, homemade/amateur teen-style selfie, Y2K/e-girl fashion
- big_tits: large breasts are clearly visible and a significant visual element
- ass: buttocks are clearly visible and a significant visual element
- blowjob: oral sex act depicted

Include big_tits/ass whenever genuinely prominent, even alongside another category -- they are not exclusive fallbacks anymore, they can co-occur with any other matching category."""

_FALLBACK_TABOO_CUES = "fauxcest, stepsis, stepmom, cheating, age gap, babysitters, step fantasy, old/young pairing"


def _build_lane_vision_prompt() -> str:
    """Assemble the prompt, pulling the taboo cue line from tag_corpus.json (single
    source of truth) instead of a hand-pasted snapshot. Falls back to a static line
    if the corpus is missing/malformed so classification never hard-fails on it.
    """
    try:
        from app.services.tag_corpus import cue_bullet_for_lane

        taboo_cues = cue_bullet_for_lane("taboo") or _FALLBACK_TABOO_CUES
    except Exception:
        taboo_cues = _FALLBACK_TABOO_CUES
    return _LANE_VISION_PROMPT_TEMPLATE.format(taboo_cues=taboo_cues)


def classify_and_log_lane_vision(
    db: Session, media_id: int, image_bytes: bytes | None, *, mime: str = "image/jpeg"
) -> dict[str, Any] | None:
    if not image_bytes:
        return None
    try:
        from app.models.media_lane_vision_decision import MediaLaneVisionDecision

        existing = (
            db.query(MediaLaneVisionDecision)
            .filter(MediaLaneVisionDecision.media_id == int(media_id))
            .first()
        )
        if existing:
            return None

        from app.services.vision_llm import analyze_image_bytes, vision_llm_enabled

        if not vision_llm_enabled():
            return None

        from app.services.aof_lane_tag_map import CANONICAL_LANE_KEYS, normalize_lane_key

        result = analyze_image_bytes(image_bytes, mime=mime, prompt_override=_build_lane_vision_prompt())
        if not result:
            return None

        raw_lanes = result.get("matching_lanes")
        if not isinstance(raw_lanes, list):
            # Back-compat: older/other providers may still return a single primary_slug.
            single = result.get("primary_slug")
            raw_lanes = [single] if single else []

        matching_lanes: list[str] = []
        for raw in raw_lanes:
            key = normalize_lane_key(str(raw or ""))
            if key in CANONICAL_LANE_KEYS and key not in matching_lanes:
                matching_lanes.append(key)

        lane_key = matching_lanes[0] if matching_lanes else None
        nsfw_tier = str(result.get("nsfw_tier") or "").strip() or None

        row = MediaLaneVisionDecision(
            media_id=int(media_id),
            lane_key=lane_key,
            nsfw_tier=nsfw_tier,
            raw_json=json.dumps(result, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return {
            "lane_key": lane_key,
            "matching_lanes": matching_lanes,
            "nsfw_tier": nsfw_tier,
            "raw": result,
        }
    except Exception:
        logger.warning("vision lane classify/log skipped media_id=%s", media_id, exc_info=True)
        return None
