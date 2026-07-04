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


def test_build_context_suffix_compact():
    from app.models.secretary_user_context import SecretaryUserContext
    from app.services.format_engine import EmotionAnalysis, build_context_suffix

    ctx = SecretaryUserContext(current_phase="engagement", interaction_format_json=None)
    a = analyze_message("How do I subscribe?")
    compact = build_context_suffix(ctx, a, verbosity="compact")
    assert "FE context:" in compact
    assert "--- Format Engine" not in compact
    standard = build_context_suffix(ctx, a, verbosity="standard")
    assert "--- Format Engine" in standard
