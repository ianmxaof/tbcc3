"""First-party tag corpus — taboo hierarchy + alias resolve + vision cue wire."""

from __future__ import annotations

import pytest


def test_load_corpus_version_and_taboo_tree():
    from app.services.tag_corpus import load_tag_corpus

    load_tag_corpus.cache_clear()
    corpus = load_tag_corpus()
    assert corpus.version == "1.0.0"
    assert "taboo" in corpus.slug_to_node
    assert "taboo-stepfamily" in corpus.slug_to_node
    assert corpus.slug_to_node["taboo-stepfamily"].parent_slug == "taboo"


@pytest.mark.parametrize(
    "alias",
    ["stepsis", "step mom", "fauxcest", "age gap", "babysitter", "cheating", "step-fantasy"],
)
def test_taboo_aliases_resolve_to_taboo_lane(alias):
    from app.services.tag_corpus import load_tag_corpus, resolve_lane_keys_for_alias

    load_tag_corpus.cache_clear()
    lanes = resolve_lane_keys_for_alias(alias)
    assert "taboo" in lanes, f"{alias!r} -> {lanes}"


def test_cue_bullet_nonempty_for_taboo():
    from app.services.tag_corpus import cue_bullet_for_lane, load_tag_corpus

    load_tag_corpus.cache_clear()
    cues = cue_bullet_for_lane("taboo")
    assert cues
    assert "stepsis" in cues or "fauxcest" in cues


def test_vision_prompt_embeds_corpus_taboo_cues():
    from app.services.media_lane_vision_classify import _build_lane_vision_prompt
    from app.services.tag_corpus import load_tag_corpus

    load_tag_corpus.cache_clear()
    prompt = _build_lane_vision_prompt()
    assert "taboo:" in prompt
    assert "stepsis" in prompt or "fauxcest" in prompt


def test_lane_tag_map_receives_corpus_aliases():
    from app.services.aof_lane_tag_map import LANE_TAG_MAP, suggest_lane_keys_from_tags

    # Corpus merge is additive at import time
    assert "stepsis" in LANE_TAG_MAP or "fauxcest" in LANE_TAG_MAP or "step fantasy" in LANE_TAG_MAP
    keys = suggest_lane_keys_from_tags("stepsis fauxcest")
    assert "taboo" in keys
