"""Companion activity touch — last_active zset for re-engagement DMs."""

from unittest.mock import MagicMock, patch

from app.services.companion_access import (
    CompanionAccess,
    companion_had_real_session,
    touch_companion_activity,
)


def test_touch_companion_activity_updates_zset():
    r = MagicMock()
    acc = CompanionAccess(user_id=42, trial_used=1)
    with patch("app.services.companion_access.get_access", return_value=acc):
        with patch("app.services.companion_access.save_access") as save:
            with patch("app.services.companion_access._redis", return_value=r):
                touch_companion_activity(42)
    save.assert_called_once()
    r.zadd.assert_called_once()
    key, mapping = r.zadd.call_args[0]
    assert key == "tbcc:companion:last_active"
    assert "42" in mapping


def test_companion_had_real_session_requires_gate_or_usage():
    acc = CompanionAccess(user_id=1)
    with patch("app.services.companion_access.get_access", return_value=acc):
        with patch("app.services.companion_access.gate_enabled", return_value=True):
            assert companion_had_real_session(1) is False
    acc2 = CompanionAccess(user_id=2, lv_ack=True, member_verified=True, trial_used=1)
    with patch("app.services.companion_access.get_access", return_value=acc2):
        with patch("app.services.companion_access.gate_enabled", return_value=True):
            assert companion_had_real_session(2) is True
