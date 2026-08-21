"""corpus_candidates() variety + anti-repeat (2026-08-21 review: a fixed 2-line
corpus produced an identical "hey" reply twice in one short real customer exchange)."""

from __future__ import annotations

from app.services.secretary_behavior import (
    _LONG_NOISE_NATURAL,
    _SHORT_NOISE_NATURAL,
    corpus_candidates,
)
from app.services.secretary_llm import builtin_default_system_prompt
from app.services.secretary_drafts import TRIAGE_JSON_INSTRUCTION


def test_short_noise_never_repeats_the_avoided_line():
    for _ in range(30):
        cands = corpus_candidates("hi", avoid_natural="hey")
        assert cands["natural"] != "hey"
        assert cands["natural"] in _SHORT_NOISE_NATURAL


def test_long_noise_never_repeats_the_avoided_line():
    for _ in range(30):
        cands = corpus_candidates("what's this about", avoid_natural="what's this about")
        assert cands["natural"] != "what's this about"
        assert cands["natural"] in _LONG_NOISE_NATURAL


def test_no_avoid_still_returns_a_valid_pool_member():
    cands = corpus_candidates("hi")
    assert cands["natural"] in _SHORT_NOISE_NATURAL


def test_solicitation_lane_unaffected_by_avoid():
    cands = corpus_candidates("stop sending me anchor text links", avoid_natural="not buying links.")
    assert cands["natural"] == "not buying links."


def test_non_noise_intent_still_defers_to_llm():
    assert corpus_candidates("how much is vip", avoid_natural="hey") is None


def test_system_prompts_forbid_self_reveal():
    assert "bot" in builtin_default_system_prompt().lower()
    assert "bot" in TRIAGE_JSON_INSTRUCTION.lower()
