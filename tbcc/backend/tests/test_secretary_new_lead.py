"""Format Engine prepare_user_turn new-lead flag."""

from app.services.format_engine import prepare_user_turn


def test_prepare_user_turn_marks_new_lead_once(db, monkeypatch):
    monkeypatch.setenv("TBCC_FORMAT_ENGINE_ENABLED", "1")
    monkeypatch.setattr("app.services.format_engine.format_engine_enabled", lambda: True)
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    uid = 9_002_100
    _suffix1, ctx1, new1 = prepare_user_turn(uid, "hey do you have VIP?", username="lead_test")
    assert new1 is True
    assert ctx1 is not None

    _suffix2, ctx2, new2 = prepare_user_turn(uid, "how much?", username="lead_test")
    assert new2 is False
    assert ctx2 == ctx1
