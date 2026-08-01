"""Stars bait DM outreach — unreachable-user skip."""

from unittest.mock import MagicMock, patch

from app.services.stars_bait_outreach import (
    _DM_UNREACHABLE_ERRORS,
    _is_dm_unreachable,
    _mark_dm_unreachable,
    send_stars_bait_dm_sync,
)


def test_unreachable_error_markers_cover_telegram_failures():
    joined = " ".join(_DM_UNREACHABLE_ERRORS)
    assert "initiate conversation" in joined
    assert "chat not found" in joined


def test_mark_and_skip_unreachable_user():
    r = MagicMock()
    r.get.return_value = "chat not found"
    _mark_dm_unreachable(r, 12345, reason="chat not found")
    r.setex.assert_called_once()
    assert _is_dm_unreachable(r, 12345) is True


def test_send_skips_unreachable_without_telegram_call():
    r = MagicMock()
    r.get.side_effect = lambda key: "1" if "unreachable" in key else None
    db = MagicMock()
    with patch("app.services.stars_bait_outreach._redis", return_value=r):
        with patch("app.services.stars_bait_outreach.stars_bait_dm_enabled", return_value=True):
            with patch.dict("os.environ", {"BOT_TOKEN": "test-token"}, clear=False):
                out = send_stars_bait_dm_sync(db, 999, force=False)
    assert out["skipped"] is True
    assert out["reason"] == "unreachable"
