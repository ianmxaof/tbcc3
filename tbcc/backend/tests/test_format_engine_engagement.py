"""Engagement score / funnel stage tracking on SecretaryUserContext."""

from app.services.format_engine import _funnel_stage_for_score, prepare_user_turn, reset_user_context
from app.models.secretary_user_context import SecretaryUserContext


def test_funnel_stage_thresholds():
    assert _funnel_stage_for_score(0.0) == "cold"
    assert _funnel_stage_for_score(0.24) == "cold"
    assert _funnel_stage_for_score(0.25) == "warming"
    assert _funnel_stage_for_score(0.49) == "warming"
    assert _funnel_stage_for_score(0.5) == "engaged"
    assert _funnel_stage_for_score(0.74) == "engaged"
    assert _funnel_stage_for_score(0.75) == "converted"
    assert _funnel_stage_for_score(1.0) == "converted"


def test_prepare_user_turn_persists_engagement_score_and_stage(db, monkeypatch):
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)

    _, context_id, is_new_lead = prepare_user_turn(4242, "hi, how does this work?", username="tester")
    assert is_new_lead is True

    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one()
    assert ctx.engagement_score > 0.0
    assert ctx.funnel_stage == _funnel_stage_for_score(ctx.engagement_score)

    # More turns from the same user raise the cumulative investment_score-derived score.
    for _ in range(6):
        prepare_user_turn(4242, "still here, pretty interested in the crypto plan", username="tester")

    db.expire_all()
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one()
    assert ctx.engagement_score >= 0.5
    assert ctx.funnel_stage in ("engaged", "converted")


def test_reset_user_context_clears_engagement(db, monkeypatch):
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)

    _, context_id, _ = prepare_user_turn(4343, "I want to subscribe now, how much does it cost?")
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one()
    assert ctx.engagement_score > 0.0

    assert reset_user_context(db, context_id) is True
    db.commit()

    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one()
    assert ctx.engagement_score == 0.0
    assert ctx.funnel_stage == "cold"
