"""psych_markers — CRM lead-signal scan bolted onto the Format Engine.

Display-only augmentation: must not perturb _infer_phase, _phase_charter, dominant_emotion
scoring, or sales-coach logic. Covers extract_psych_markers shapes, prepare_user_turn wiring,
DB round-trip survival, and phase-inference non-interference.
"""

from __future__ import annotations

from app.services.format_engine import extract_psych_markers


def test_extract_psych_markers_buyer_text():
    out = extract_psych_markers("how much is it to join?", "introduction", 1)
    assert out["financial_intent"] == "buyer"
    assert out["trust_level"] == "low"
    assert isinstance(out["urgency_score"], float)


def test_extract_psych_markers_comparison_text():
    out = extract_psych_markers("is this cheaper than the other one?", "engagement", 5)
    assert out["financial_intent"] == "comparison"
    assert out["trust_level"] == "medium"


def test_extract_psych_markers_casual_text():
    out = extract_psych_markers("haha that's funny", "engagement", 10)
    assert out["financial_intent"] == "casual"
    assert out["trust_level"] == "high"
    assert out["urgency_score"] == 0.0


def test_extract_psych_markers_trust_level_boundaries():
    assert extract_psych_markers("hi", "introduction", 2)["trust_level"] == "low"
    assert extract_psych_markers("hi", "introduction", 3)["trust_level"] == "medium"
    assert extract_psych_markers("hi", "introduction", 8)["trust_level"] == "medium"
    assert extract_psych_markers("hi", "introduction", 9)["trust_level"] == "high"


def test_extract_psych_markers_urgency_score_counts_and_caps():
    out = extract_psych_markers("I need this now, ready today, asap please", "engagement", 4)
    assert out["urgency_score"] > 0.3
    assert out["urgency_score"] <= 1.0
    out_none = extract_psych_markers("just browsing around", "engagement", 4)
    assert out_none["urgency_score"] == 0.0


def test_prepare_user_turn_populates_psych_markers(db, monkeypatch):
    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import _load_format, prepare_user_turn

    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    _suffix, ctx_id, _new_lead = prepare_user_turn(9_004_100, "how much to subscribe?", username="psych_test")
    assert ctx_id is not None

    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == ctx_id).one()
    fmt = _load_format(row.interaction_format_json)
    markers = fmt.get("psych_markers")
    assert markers is not None
    assert markers["financial_intent"] == "buyer"
    assert markers["trust_level"] == "low"


def test_psych_markers_survive_db_round_trip(db, monkeypatch):
    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import _load_format, prepare_user_turn

    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    uid = 9_004_200
    prepare_user_turn(uid, "how much to subscribe?", username="round_trip")

    # A second turn forces a fresh _load_format(...) of the persisted JSON blob — proves
    # the field survives serialize -> store -> reload, not just the in-memory dict.
    prepare_user_turn(uid, "ok thanks", username="round_trip")

    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == uid).one()
    reloaded = _load_format(row.interaction_format_json)
    assert "psych_markers" in reloaded
    assert reloaded["psych_markers"]["financial_intent"] == "casual"


def test_psych_markers_do_not_affect_phase_inference(db, monkeypatch):
    """Same conversation, run twice — once with extract_psych_markers wired normally,
    once with it forced to a no-op — phase output must be identical either way."""
    from app.models.secretary_user_context import SecretaryUserContext
    import app.services.format_engine as fe

    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr(fe, "format_engine_enabled", lambda: True)
    monkeypatch.setattr(fe, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    def _no_refine(*, user_text, heuristic, prev_phase, new_phase, format_snapshot):
        return heuristic, None

    monkeypatch.setattr("app.services.format_engine_llm.refine_emotion_on_phase_change", _no_refine)

    text_turns = ["how much to subscribe?", "card or zelle?", "let me in now"]

    def _run(uid: int) -> list[str]:
        phases = []
        for t in text_turns:
            _suffix, ctx_id, _ = fe.prepare_user_turn(uid, t, username="phase_check")
            row = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == ctx_id).one()
            phases.append(row.current_phase)
        return phases

    normal_phases = _run(9_004_300)

    monkeypatch.setattr(fe, "extract_psych_markers", lambda text, current_phase, message_count: {})
    stubbed_phases = _run(9_004_301)

    assert normal_phases == stubbed_phases
