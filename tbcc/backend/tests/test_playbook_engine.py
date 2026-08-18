"""Playbook engine — capture trajectory, score matching, format suffix."""

from __future__ import annotations

import json

from app.models.conversion_playbook import ConversionPlaybook
from app.services import playbook_engine
from app.services.playbook_engine import build_playbook_suffix


def _format_json(**overrides):
    base = {
        "version": 4,
        "name": "support-adaptive",
        "phase": "engagement",
        "phase_history": [
            {"from": "introduction", "to": "engagement", "at": "2026-08-01T00:00:00"},
        ],
        "psych_markers": {
            "financial_intent": "buyer",
            "trust_level": "medium",
            "urgency_score": 0.4,
        },
        "metrics": {
            "user_messages": 8,
            "assistant_messages": 6,
            "distress_events": 1,
            "investment_score": 0.8,
        },
    }
    base.update(overrides)
    return base


def test_save_playbook_stores_correct_trajectory(db):
    fmt = _format_json()
    pb = playbook_engine.save_playbook_on_conversion(
        7787282561, fmt, "private", "zelle_crypto", db=db
    )
    assert pb is not None
    assert pb.telegram_user_id == 7787282561
    assert json.loads(pb.phase_trajectory) == ["introduction", "engagement"]
    snapshot = json.loads(pb.psych_markers_at_conversion)
    assert snapshot["financial_intent"] == "buyer"
    assert snapshot["trust_level"] == "medium"
    assert pb.message_count_at_conversion == 8
    assert pb.payment_lane_used == "private"
    assert pb.conversion_outcome == "zelle_crypto"
    assert pb.is_active is True
    assert "final_phase=engagement" in pb.format_summary


def test_save_accepts_json_string(db):
    fmt = json.dumps(_format_json())
    pb = playbook_engine.save_playbook_on_conversion(1, fmt, "stars", db=db)
    assert pb is not None
    assert json.loads(pb.phase_trajectory) == ["introduction", "engagement"]


def _seed_playbook(db, intent, trust, phase, *, is_active=True):
    pb = ConversionPlaybook(
        phase_trajectory=json.dumps(["introduction", phase]),
        psych_markers_at_conversion=json.dumps(
            {"financial_intent": intent, "trust_level": trust, "urgency_score": 0.0}
        ),
        message_count_at_conversion=6,
        payment_lane_used="private" if intent == "committed" else "stars",
        conversion_outcome="zelle_crypto",
        format_summary=f"{phase} silhouette",
        behavioral_directive_at_conversion="Recovery then handoff.",
        is_active=is_active,
    )
    db.add(pb)
    return pb


def test_search_playbooks_scores_financial_intent_first(db):
    _seed_playbook(db, "buyer", "medium", "engagement")
    _seed_playbook(db, "buyer", "medium", "support")
    db.commit()

    matches = playbook_engine.search_playbooks(
        {"financial_intent": "buyer", "trust_level": "medium"}, "engagement", 8, db=db
    )
    assert len(matches) == 2
    matched_phases = [json.loads(p.phase_trajectory)[-1] for p in matches]
    # Engagement match additionally earns the same-phase point → ranks first.
    assert matched_phases == ["engagement", "support"]


def test_search_playbooks_excludes_below_threshold_and_inactive(db):
    _seed_playbook(db, "buyer", "medium", "engagement")  # 3 (financial) — passes
    _seed_playbook(db, "casual", "medium", "engagement")  # 0 — below threshold, excluded
    _seed_playbook(db, "buyer", "high", "support", is_active=False)  # 3 but inactive
    db.commit()

    matches = playbook_engine.search_playbooks(
        {"financial_intent": "buyer", "trust_level": "high"}, "support", 8, db=db
    )
    # Only the active row with a financial-intent match survives (exactly one).
    assert len(matches) == 1
    assert json.loads(matches[0].phase_trajectory)[-1] == "engagement"


def test_scoring_semantics(db):
    pb = _seed_playbook(db, "committed", "high", "support")
    db.commit()
    db.refresh(pb)

    full = playbook_engine.playbook_match_score(
        pb, {"financial_intent": "committed", "trust_level": "high"}, "support"
    )
    assert full == 3 + 2 + 1  # financial + trust + same phase

    no_phase = playbook_engine.playbook_match_score(
        pb, {"financial_intent": "committed", "trust_level": "high"}, "engagement"
    )
    assert no_phase == 3 + 2

    trust_only = playbook_engine.playbook_match_score(
        pb, {"financial_intent": "casual", "trust_level": "high"}, "support"
    )
    assert trust_only == 2 + 1

    empty_markers = playbook_engine.playbook_match_score(pb, None, None)
    assert empty_markers == 0


def test_search_limits_and_orders_desc(db):
    _seed_playbook(db, "buyer", "high", "engagement")  # 3 + 2 + 1 = 6
    _seed_playbook(db, "buyer", "high", "support")  # 3 + 2 = 5
    _seed_playbook(db, "buyer", "high", "introduction")  # 3 + 2 = 5
    db.commit()

    matches = playbook_engine.search_playbooks(
        {"financial_intent": "buyer", "trust_level": "high"}, "engagement", 8, limit=2, db=db
    )
    assert len(matches) == 2
    assert json.loads(matches[0].phase_trajectory)[-1] == "engagement"


def test_build_suffix_formats_and_increments_times_matched(db):
    _seed_playbook(db, "buyer", "medium", "engagement")
    db.commit()
    matches = playbook_engine.search_playbooks(
        {"financial_intent": "buyer", "trust_level": "medium"}, "engagement", 8, db=db
    )
    assert matches
    before = matches[0].times_matched

    text = build_playbook_suffix(matches, db=db)
    assert "Similar converted clients showed:" in text
    assert "Consider:" in text
    assert "engagement silhouette" in text
    assert "Recovery then handoff." in text

    db.refresh(matches[0])
    assert matches[0].times_matched == before + 1


def test_build_suffix_empty_returns_passthrough(db):
    assert build_playbook_suffix([], db=db) == ""