"""Vision-LLM lane classification decision log — shadow-mode logging only."""

from __future__ import annotations

from app.models.media_lane_vision_decision import MediaLaneVisionDecision
from app.services.media_lane_vision_classify import classify_and_log_lane_vision


def _enable_vision(monkeypatch, result: dict | None, *, capture_prompts: list[str] | None = None):
    monkeypatch.setattr("app.services.vision_llm.vision_llm_enabled", lambda: True)
    calls = {"n": 0}

    def _fake_analyze(image_bytes, **kwargs):
        calls["n"] += 1
        if capture_prompts is not None:
            capture_prompts.append(kwargs.get("prompt_override") or "")
        return result or {}

    monkeypatch.setattr("app.services.vision_llm.analyze_image_bytes", _fake_analyze)
    return calls


def test_classify_and_log_creates_row_with_normalized_lane(db, monkeypatch):
    _enable_vision(monkeypatch, {"matching_lanes": ["big_tits"], "nsfw_tier": "explicit"})

    out = classify_and_log_lane_vision(db, 101, b"fake-image-bytes")

    assert out == {
        "lane_key": "big_tits",
        "matching_lanes": ["big_tits"],
        "nsfw_tier": "explicit",
        "raw": {"matching_lanes": ["big_tits"], "nsfw_tier": "explicit"},
    }
    row = db.query(MediaLaneVisionDecision).filter(MediaLaneVisionDecision.media_id == 101).first()
    assert row is not None
    assert row.lane_key == "big_tits"
    assert row.nsfw_tier == "explicit"


def test_classify_and_log_is_idempotent(db, monkeypatch):
    calls = _enable_vision(monkeypatch, {"matching_lanes": ["milf"], "nsfw_tier": "suggestive"})

    first = classify_and_log_lane_vision(db, 202, b"fake-image-bytes")
    second = classify_and_log_lane_vision(db, 202, b"fake-image-bytes")

    assert first is not None
    assert second is None  # no-op, no second model call
    assert calls["n"] == 1
    rows = db.query(MediaLaneVisionDecision).filter(MediaLaneVisionDecision.media_id == 202).all()
    assert len(rows) == 1


def test_classify_and_log_noop_when_vision_disabled(db, monkeypatch):
    monkeypatch.setattr("app.services.vision_llm.vision_llm_enabled", lambda: False)

    out = classify_and_log_lane_vision(db, 303, b"fake-image-bytes")

    assert out is None
    assert db.query(MediaLaneVisionDecision).filter(MediaLaneVisionDecision.media_id == 303).first() is None


def test_classify_and_log_unknown_slug_stores_none_lane(db, monkeypatch):
    _enable_vision(monkeypatch, {"matching_lanes": ["not_a_real_lane"], "nsfw_tier": "unknown"})

    out = classify_and_log_lane_vision(db, 404, b"fake-image-bytes")

    assert out["lane_key"] is None
    assert out["matching_lanes"] == []
    row = db.query(MediaLaneVisionDecision).filter(MediaLaneVisionDecision.media_id == 404).first()
    assert row.lane_key is None
    assert row.nsfw_tier == "unknown"


def test_classify_and_log_noop_without_image_bytes(db, monkeypatch):
    calls = _enable_vision(monkeypatch, {"matching_lanes": ["milf"]})

    out = classify_and_log_lane_vision(db, 505, None)

    assert out is None
    assert calls["n"] == 0


def test_classify_and_log_multi_label_preserves_full_ranked_list(db, monkeypatch):
    """A single item can genuinely qualify for more than one lane (e.g. milf +
    big_tits) — lane_key is the top pick, matching_lanes carries the full list."""
    _enable_vision(monkeypatch, {"matching_lanes": ["milf", "big_tits", "ass"], "nsfw_tier": "explicit"})

    out = classify_and_log_lane_vision(db, 606, b"fake-image-bytes")

    assert out["lane_key"] == "milf"
    assert out["matching_lanes"] == ["milf", "big_tits", "ass"]
    row = db.query(MediaLaneVisionDecision).filter(MediaLaneVisionDecision.media_id == 606).first()
    assert row.lane_key == "milf"


def test_classify_and_log_backcompat_primary_slug_single_provider(db, monkeypatch):
    """Older/other providers may still return a bare primary_slug instead of
    matching_lanes — must still resolve to a single-item lane list."""
    _enable_vision(monkeypatch, {"primary_slug": "voyeur", "nsfw_tier": "explicit"})

    out = classify_and_log_lane_vision(db, 707, b"fake-image-bytes")

    assert out["lane_key"] == "voyeur"
    assert out["matching_lanes"] == ["voyeur"]


def test_taboo_cue_vocabulary_reaches_the_actual_prompt(db, monkeypatch):
    """The corpus-driven taboo cue line must actually be present in the prompt
    sent to the classifier, not just exist in the corpus in isolation."""
    prompts: list[str] = []
    _enable_vision(monkeypatch, {"matching_lanes": ["taboo"], "nsfw_tier": "suggestive"}, capture_prompts=prompts)

    classify_and_log_lane_vision(db, 808, b"fake-image-bytes")

    assert len(prompts) == 1
    for cue in ("stepsis", "stepmom", "fauxcest", "cheating", "babysitter", "age gap"):
        assert cue in prompts[0], f"taboo cue '{cue}' missing from the actual built prompt"


def test_replay_taboo_ground_truth_fixture_yields_nonzero_hits(db, monkeypatch):
    """Requirement: replaying a small taboo ground-truth fixture set yields
    non-zero taboo hits against the expanded corpus. LLM is mocked (no network
    in unit tests) but the cue/vocab path (prompt build -> call -> parse ->
    persist) must fire for real on every item in the fixture set."""
    fixture = [
        (1001, "stepsister roleplay bedroom selfie"),
        (1002, "cheating wife caught affair"),
        (1003, "babysitter age gap scenario"),
    ]
    prompts: list[str] = []

    def _fake_analyze(image_bytes, **kwargs):
        prompts.append(kwargs.get("prompt_override") or "")
        return {"matching_lanes": ["taboo"], "nsfw_tier": "suggestive", "facets": [image_bytes.decode()]}

    monkeypatch.setattr("app.services.vision_llm.vision_llm_enabled", lambda: True)
    monkeypatch.setattr("app.services.vision_llm.analyze_image_bytes", _fake_analyze)

    hits = 0
    for media_id, fake_caption in fixture:
        out = classify_and_log_lane_vision(db, media_id, fake_caption.encode())
        if out and out["lane_key"] == "taboo":
            hits += 1

    assert hits == len(fixture), "expected every taboo fixture item to land on the taboo lane"
    assert len(prompts) == len(fixture)
    assert all("stepsis" in p and "cheating" in p for p in prompts), "cue vocab must fire on every replay, not just once"
