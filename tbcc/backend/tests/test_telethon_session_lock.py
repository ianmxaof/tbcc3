"""Telethon session lock wait-duration instrumentation."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.telethon_session_lock import _acquire_session_lock


def test_acquire_session_lock_logs_wait_duration_on_second_poll(caplog):
    mock_r = MagicMock()
    mock_r.set.side_effect = [False, True]
    monotonic = iter([0.0, 0.0, 0.52, 0.52])

    with patch("app.services.telethon_session_lock._redis_client", return_value=mock_r):
        with patch("app.services.telethon_session_lock.time.sleep"):
            with patch("app.services.telethon_session_lock.time.monotonic", side_effect=monotonic):
                with patch("app.services.telethon_session_lock._poll_interval_s", return_value=0.35):
                    with caplog.at_level(logging.INFO):
                        token = _acquire_session_lock(
                            "tbcc:lock:test",
                            label="poster",
                            timeout_s=30.0,
                            stuck_hint="test hint",
                        )

    assert token
    assert "poster Telethon session lock acquired after 0.52s wait" in caplog.text


def test_acquire_session_lock_no_wait_log_on_immediate_acquire(caplog):
    mock_r = MagicMock()
    mock_r.set.return_value = True

    with patch("app.services.telethon_session_lock._redis_client", return_value=mock_r):
        with patch("app.services.telethon_session_lock.time.monotonic", return_value=10.0):
            with patch("app.services.telethon_session_lock._poll_interval_s", return_value=0.35):
                with caplog.at_level(logging.INFO):
                    token = _acquire_session_lock(
                        "tbcc:lock:test",
                        label="poster",
                        timeout_s=30.0,
                        stuck_hint="test hint",
                    )

    assert token
    assert "acquired after" not in caplog.text


def test_acquire_session_lock_logs_wait_duration_on_timeout(caplog):
    mock_r = MagicMock()
    mock_r.set.return_value = False
    monotonic = iter([0.0, 0.0, 5.0, 5.0])

    with patch("app.services.telethon_session_lock._redis_client", return_value=mock_r):
        with patch("app.services.telethon_session_lock.time.sleep"):
            with patch("app.services.telethon_session_lock.time.monotonic", side_effect=monotonic):
                with patch("app.services.telethon_session_lock._poll_interval_s", return_value=0.35):
                    with caplog.at_level(logging.INFO):
                        with pytest.raises(TimeoutError, match="Timed out after 5s"):
                            _acquire_session_lock(
                                "tbcc:lock:test",
                                label="import",
                                timeout_s=5.0,
                                stuck_hint="stuck",
                            )

    assert "import Telethon session lock timed out after 5.00s wait" in caplog.text
