"""payment_lane() psych_markers fast-track — Format Engine financial_intent/trust_level/
urgency_score signals can route straight to 'private' (Zelle/crypto) ahead of the existing
phase/message_count gate. psych_markers=None must be a pure no-op (existing behavior)."""

from __future__ import annotations

from app.services.secretary_behavior import behavior_suffix, payment_lane


def test_committed_buyer_routes_private_regardless_of_message_count():
    assert (
        payment_lane(
            "introduction",
            message_count=1,
            psych_markers={"financial_intent": "committed", "trust_level": "low", "urgency_score": 0.0},
        )
        == "private"
    )


def test_buyer_with_low_trust_still_gets_stars():
    assert (
        payment_lane(
            "introduction",
            message_count=1,
            psych_markers={"financial_intent": "buyer", "trust_level": "low", "urgency_score": 0.0},
        )
        == "stars"
    )


def test_buyer_with_medium_or_high_trust_routes_private():
    assert (
        payment_lane(
            "engagement",
            message_count=4,
            psych_markers={"financial_intent": "buyer", "trust_level": "medium", "urgency_score": 0.0},
        )
        == "private"
    )
    assert (
        payment_lane(
            "engagement",
            message_count=10,
            psych_markers={"financial_intent": "buyer", "trust_level": "high", "urgency_score": 0.0},
        )
        == "private"
    )


def test_high_urgency_in_support_phase_routes_private():
    assert (
        payment_lane(
            "support",
            message_count=1,
            psych_markers={"financial_intent": "casual", "trust_level": "low", "urgency_score": 0.9},
        )
        == "private"
    )
    assert (
        payment_lane(
            "recovery",
            message_count=1,
            psych_markers={"financial_intent": "casual", "trust_level": "low", "urgency_score": 0.7},
        )
        == "private"
    )


def test_high_urgency_outside_support_recovery_does_not_fast_track():
    # Urgency alone in an unrelated phase isn't one of the three fast-track conditions,
    # so it falls through to the existing gate (introduction, count<5 -> stars).
    assert (
        payment_lane(
            "introduction",
            message_count=1,
            psych_markers={"financial_intent": "casual", "trust_level": "low", "urgency_score": 0.9},
        )
        == "stars"
    )


def test_none_psych_markers_falls_through_to_existing_logic():
    assert payment_lane("introduction", message_count=1, psych_markers=None) == "stars"
    assert payment_lane("recovery", message_count=2, psych_markers=None) == "private"
    assert payment_lane("introduction", message_count=5, psych_markers=None) == "private"


def test_psych_markers_present_but_no_match_falls_through_to_existing_gate():
    casual = {"financial_intent": "casual", "trust_level": "low", "urgency_score": 0.1}
    assert payment_lane("introduction", message_count=1, psych_markers=casual) == "stars"
    assert payment_lane("support", message_count=1, psych_markers=casual) == "private"


def test_default_call_without_psych_markers_arg_unchanged():
    # Existing call sites that never pass psych_markers must behave exactly as before.
    assert payment_lane("introduction", message_count=1) == "stars"
    assert payment_lane("recovery", message_count=2) == "private"


def test_behavior_suffix_threads_psych_markers_into_private_copy():
    out = behavior_suffix(
        intent="buyer",
        phase="introduction",
        message_count=1,
        payment_bot="aofsubscriptions_bot",
        psych_markers={"financial_intent": "committed", "trust_level": "low", "urgency_score": 0.0},
    )
    assert "Zelle or crypto" in out
    assert "Stars checkout" not in out
