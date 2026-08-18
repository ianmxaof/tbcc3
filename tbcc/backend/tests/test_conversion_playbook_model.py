"""ConversionPlaybook model CRUD + field validation."""

from __future__ import annotations

import json

from app.models.conversion_playbook import ConversionPlaybook


def test_create_defaults(db):
    pb = ConversionPlaybook(
        telegram_user_id=7787282561,
        phase_trajectory=json.dumps(["introduction", "engagement"]),
        psych_markers_at_conversion=json.dumps(
            {"financial_intent": "buyer", "trust_level": "medium", "urgency_score": 0.4}
        ),
        message_count_at_conversion=8,
        payment_lane_used="private",
        behavioral_directive_at_conversion="Introduce low-stakes logistical friction.",
        conversion_outcome="zelle_crypto",
        format_summary="8 msgs to conversion",
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)

    assert pb.id is not None
    assert pb.is_active is True
    assert pb.times_matched == 0
    assert pb.created_at is not None


def test_nullable_telegram_user_id(db):
    pb = ConversionPlaybook(
        telegram_user_id=None,
        phase_trajectory=json.dumps(["engagement"]),
        psych_markers_at_conversion=None,
        message_count_at_conversion=3,
        payment_lane_used="stars",
        conversion_outcome="stars_purchase",
        format_summary="3 msgs to conversion",
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    assert pb.telegram_user_id is None


def test_required_id_and_update_times_matched(db):
    pb = ConversionPlaybook(
        phase_trajectory=json.dumps(["introduction"]),
        conversion_outcome="unknown",
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)

    pb.times_matched = 4
    pb.is_active = False
    db.commit()
    db.refresh(pb)
    assert pb.times_matched == 4
    assert pb.is_active is False


def test_partial_insert_picks_defaults(db):
    # Every non-PK column carries a default or is nullable, so a partial insert is legal.
    pb = ConversionPlaybook(phase_trajectory='["introduction"]')
    db.add(pb)
    db.commit()
    db.refresh(pb)
    assert pb.id is not None
    assert pb.is_active is True
    assert pb.times_matched == 0
    assert pb.conversion_outcome is None


def test_delete(db):
    pb = ConversionPlaybook(
        phase_trajectory=json.dumps(["engagement"]),
        conversion_outcome="stars_purchase",
        format_summary="delete me",
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    pid = pb.id

    db.delete(pb)
    db.commit()
    assert db.query(ConversionPlaybook).filter(ConversionPlaybook.id == pid).one_or_none() is None