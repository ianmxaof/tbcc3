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


def test_phase_introduction_early():
    fmt = _default_format()
    a = analyze_message("Hi")
    phase = _infer_phase(fmt, user_message_count=1, analysis=a, hours_since_last_user=None)
    assert phase == "introduction"
