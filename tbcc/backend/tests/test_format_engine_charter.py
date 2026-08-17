"""Gap G3 — phase-conditional Format Engine ethical charter."""

from app.services.format_engine import _phase_charter


def test_introduction_charter_mentions_rapport():
    charter = _phase_charter("introduction", "standard")
    assert "rapport" in charter.lower()


def test_support_charter_forbids_pitch():
    charter = _phase_charter("support", "standard")
    lower = charter.lower()
    assert "support" in lower
    assert lower.count("checkout") <= 1
    assert "do not pitch checkout" in lower


def test_recovery_charter_mentions_availability():
    """Recovery is warm + no fake urgency. Checkout stays the payment bot — not a Stars/Zelle split."""
    charter = _phase_charter("recovery", "standard")
    lower = charter.lower()
    assert "availability" in lower
    assert "payment bot" in lower
    assert "zelle" not in lower
    assert "stars" not in lower


def test_engagement_charter_mentions_buying_intent():
    charter = _phase_charter("engagement", "standard")
    lower = charter.lower()
    assert "buying intent" in lower or "buying" in lower


def test_none_phase_no_charter():
    assert _phase_charter(None, "standard") == ""


def test_unrecognized_phase_no_charter():
    assert _phase_charter("weird-phase-name", "standard") == ""


def test_compact_truncates_to_first_sentence():
    charter = _phase_charter("engagement", "compact")
    assert charter == "Help the user with what they asked."
    assert charter.endswith(".")
    assert charter.count(".") == 1


def test_compact_none_phase_still_empty():
    assert _phase_charter(None, "compact") == ""
