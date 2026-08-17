"""Format Engine heuristic tests."""

from app.services.format_engine import analyze_message, _infer_phase, _default_format, _update_format


def test_analyze_distress():
    a = analyze_message("This is a scam, I want a refund now!")
    assert a.distress_detected
    assert a.dominant == "distress"


def test_analyze_confusion():
    a = analyze_message("I'm confused — how do I subscribe?")
    assert a.dominant == "confusion"
    assert not a.distress_detected


def test_phase_support_on_distress():
    fmt = _default_format()
    a = analyze_message("I'm furious, this doesn't work")
    fmt = _update_format(fmt, analysis=a, user_text="I'm furious", new_phase="support")
    assert fmt["phase"] == "support"
    assert fmt["interaction_guidelines"]["escalation_hint"]


def test_load_format_keeps_intent_and_refinements():
    from app.services.format_engine import _load_format, _save_format, _default_format

    fmt = _default_format()
    fmt["last_intent"] = "buyer"
    fmt["llm_refinements"] = [{"tone_directive": "warmer"}]
    loaded = _load_format(_save_format(fmt))
    assert loaded["last_intent"] == "buyer"
    assert loaded["llm_refinements"][0]["tone_directive"] == "warmer"


def test_list_recent_contexts_orders_newest(db, monkeypatch):
    from datetime import datetime, timedelta

    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import list_recent_contexts, _save_format, _default_format

    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    older = SecretaryUserContext(
        telegram_user_id=101,
        telegram_username="old_user",
        current_phase="introduction",
        interaction_format_json=_save_format(_default_format()),
        updated_at=datetime.utcnow() - timedelta(hours=2),
    )
    newer = SecretaryUserContext(
        telegram_user_id=202,
        telegram_username="new_user",
        current_phase="engagement",
        interaction_format_json=_save_format(_default_format()),
        updated_at=datetime.utcnow(),
    )
    db.add_all([older, newer])
    db.commit()

    listed = list_recent_contexts(limit=8, offset=0)
    assert listed["total"] == 2
    assert listed["items"][0]["telegram_username"] == "new_user"

    found = list_recent_contexts(q="old_user")
    assert found["total"] == 1
    assert found["items"][0]["telegram_user_id"] == 101


def test_get_context_display_includes_last_user_line(db, monkeypatch):
    from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext
    from app.services.format_engine import (
        get_context_display,
        _save_format,
        _default_format,
    )

    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    ctx = SecretaryUserContext(
        telegram_user_id=303,
        telegram_username="card_user",
        current_phase="engagement",
        interaction_format_json=_save_format(_default_format()),
        reply_mode="pilot",
    )
    db.add(ctx)
    db.flush()
    db.add(SecretaryMessageRecord(context_id=ctx.id, role="user", content="how do I subscribe?"))
    db.commit()

    payload = get_context_display(telegram_user_id=303)
    assert payload is not None
    assert payload["telegram_username"] == "card_user"
    assert payload["reply_mode"] == "pilot"
    assert payload["last_user_text"] == "how do I subscribe?"


def test_build_context_suffix_compact():
    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import EmotionAnalysis, build_context_suffix

    ctx = SecretaryUserContext(current_phase="engagement", interaction_format_json=None)
    a = analyze_message("How do I subscribe?")
    compact = build_context_suffix(ctx, a, verbosity="compact")
    assert "FE context:" in compact
    assert "--- Format Engine" not in compact
    assert "Support only" not in compact
    assert "no manipulation" not in compact
    assert "Build rapport" in compact
    standard = build_context_suffix(ctx, a, verbosity="standard")
    assert "--- Format Engine" in standard
    assert "Do not manipulate" not in standard
    assert "Build rapport" in standard


def test_build_behavioral_directive_branches():
    from app.services.format_engine import build_behavioral_directive

    rapport = build_behavioral_directive({"message_count": 1, "phase": "introduction", "distress_events": 0})
    assert rapport == "Build rapport. Establish emotional baseline. No transactional language."

    engage = build_behavioral_directive({"message_count": 5, "phase": "engagement", "distress_events": 0})
    assert engage == "Introduce low-stakes logistical friction. Test compliance with minor requests."

    hold = build_behavioral_directive({"message_count": 1, "phase": "support", "distress_events": 0})
    assert hold == "Hold space. Do not extract. Transition target from distress back to dependency."

    hold_distress = build_behavioral_directive({"message_count": 8, "phase": "engagement", "distress_events": 2})
    assert hold_distress.startswith("Hold space.")


def test_prepare_user_turn_records_investment_score(db, monkeypatch):
    from app.services.format_engine import _load_format, prepare_user_turn
    from app.models.secretary_user_context import SecretaryUserContext

    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    text = "hello there"
    suffix, ctx_id, new_lead = prepare_user_turn(9_002_200, text, username="score_test")
    assert new_lead is True
    assert ctx_id is not None
    assert "Build rapport" in suffix

    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == ctx_id).one()
    fmt = _load_format(row.interaction_format_json)
    expected = min(1.0, (1 * 0.1) + (len(text) / 100.0))
    assert fmt["metrics"]["investment_score"] == expected
    assert fmt["metrics"]["user_messages"] == 1


def test_apply_llm_derived_emotion_valid():
    from app.services.format_engine import apply_llm_derived_emotion

    fmt = _default_format()
    fmt["dominant_emotions"] = ["anxious", "anxious"]
    out = apply_llm_derived_emotion(
        fmt,
        {
            "state": "anxious",
            "intensity": 0.8,
            "signals": ["short replies", "refund talk"],
        },
    )
    assert out["llm_emotion"]["state"] == "anxious"
    assert out["llm_emotion"]["intensity"] == 0.8
    assert out["dominant_emotions"][-1] == "anxious"
    assert out["dominant_emotions"] == out["dominant_emotions"][-12:]
    assert out["dominant_emotion"] == "anxious"
    assert "short replies" in out["observed_triggers"]
    assert "refund talk" in out["observed_triggers"]
    assert out["metrics"]["distress_events"] == 1


def test_apply_llm_invalid_state_falls_back_to_neutral():
    from app.services.format_engine import apply_llm_derived_emotion

    fmt = _default_format()
    out = apply_llm_derived_emotion(
        fmt,
        {"state": "elated", "intensity": 0.9, "signals": ["lol"]},
    )
    assert out["llm_emotion"]["state"] == "neutral"
    assert "elated" not in (out.get("dominant_emotions") or [])
    assert out["dominant_emotion"] == "neutral"
    assert out["metrics"]["distress_events"] == 0
    assert "lol" in out["observed_triggers"]


def test_apply_llm_intensity_clamping():
    from app.services.format_engine import apply_llm_derived_emotion

    hi = apply_llm_derived_emotion(
        _default_format(),
        {"state": "guarded", "intensity": 1.7, "signals": []},
    )
    assert hi["llm_emotion"]["intensity"] == 1.0
    assert hi["metrics"]["distress_events"] == 1

    lo = apply_llm_derived_emotion(
        _default_format(),
        {"state": "guarded", "intensity": -0.4, "signals": []},
    )
    assert lo["llm_emotion"]["intensity"] == 0.0
    assert lo["metrics"]["distress_events"] == 0

    mild = apply_llm_derived_emotion(
        _default_format(),
        {"state": "anxious", "intensity": 0.59, "signals": ["uneasy"]},
    )
    assert mild["metrics"]["distress_events"] == 0


def test_dismissive_triggers_recovery_phase():
    from app.services.format_engine import apply_llm_derived_emotion

    fmt = _default_format()
    fmt["metrics"]["user_messages"] = 4
    out = apply_llm_derived_emotion(
        fmt,
        {"state": "dismissive", "intensity": 0.5, "signals": ["whatever"]},
    )
    assert out["phase"] == "recovery"


def test_transactional_prevents_support_phase():
    from app.services.format_engine import apply_llm_derived_emotion

    fmt = _default_format()
    fmt["phase"] = "engagement"
    fmt["metrics"]["user_messages"] = 5
    fmt["metrics"]["distress_events"] = 2
    out = apply_llm_derived_emotion(
        fmt,
        {"state": "transactional", "intensity": 0.9, "signals": ["price"]},
    )
    assert out["phase"] != "support"
    assert out["phase"] == "engagement"


def test_dropped_turn_increments_metric(db, monkeypatch):
    from datetime import datetime

    from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext
    from app.services.format_engine import (
        _load_format,
        _save_format,
        _default_format,
        record_dropped_turn,
    )

    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    ctx = SecretaryUserContext(
        telegram_user_id=7_007_001,
        telegram_username="drop_user",
        current_phase="engagement",
        interaction_format_json=_save_format(_default_format()),
    )
    db.add(ctx)
    db.commit()
    before = ctx.last_assistant_at

    record_dropped_turn(7_007_001)

    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == 7_007_001).one()
    fmt = _load_format(row.interaction_format_json)
    assert fmt["metrics"]["dropped_turns"] == 1
    assert fmt["metrics"]["assistant_messages"] == 0
    assert row.last_assistant_at is not None
    assert before is None or row.last_assistant_at >= before
    assert (datetime.utcnow() - row.last_assistant_at).total_seconds() < 10
    asst_rows = (
        db.query(SecretaryMessageRecord)
        .filter(SecretaryMessageRecord.context_id == row.id, SecretaryMessageRecord.role == "assistant")
        .count()
    )
    assert asst_rows == 0


def test_dropped_turn_prevents_false_recovery(db, monkeypatch):
    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import _load_format, prepare_user_turn, record_dropped_turn

    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    def _no_refine(*, user_text, heuristic, prev_phase, new_phase, format_snapshot):
        return heuristic, None

    monkeypatch.setattr(
        "app.services.format_engine_llm.refine_emotion_on_phase_change",
        _no_refine,
    )

    uid = 7_007_007
    prepare_user_turn(uid, "How do I subscribe?", username="g7")
    prepare_user_turn(uid, "What is VIP access?", username="g7")
    suffix, ctx_id, _ = prepare_user_turn(uid, "Can I see the catalog?", username="g7")
    assert ctx_id is not None
    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == ctx_id).one()
    assert row.current_phase == "engagement"

    record_dropped_turn(uid)
    prepare_user_turn(uid, "Can I still subscribe?", username="g7")
    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == uid).one()
    fmt = _load_format(row.interaction_format_json)
    assert fmt["metrics"]["dropped_turns"] == 1
    assert row.current_phase == "engagement"
