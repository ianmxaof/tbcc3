"""Tests for main-group notification budget."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.data.aof_network import MAIN_GROUP_IDENT
from app.services.main_group_notifications import (
    is_main_group_identifier,
    resolve_main_group_send_silent,
)


def test_is_main_group_identifier():
    assert is_main_group_identifier(MAIN_GROUP_IDENT) is True
    assert is_main_group_identifier("-100999") is False


def test_non_main_group_passthrough():
    assert resolve_main_group_send_silent(
        channel_identifier="-100999",
        post_send_silent=False,
        had_media=True,
    ) is False
    assert resolve_main_group_send_silent(
        channel_identifier="-100999",
        post_send_silent=True,
        had_media=True,
    ) is True


@patch("app.services.main_group_notifications.main_group_notify_gate_enabled", return_value=True)
@patch("app.services.main_group_notifications._last_loud_at", return_value=None)
@patch("app.services.main_group_notifications._record_loud_notify")
def test_first_loud_in_window_allowed(_record, _last, _enabled):
    silent = resolve_main_group_send_silent(
        channel_identifier=MAIN_GROUP_IDENT,
        post_send_silent=False,
        had_media=True,
    )
    assert silent is False
    _record.assert_called_once()


@patch("app.services.main_group_notifications.main_group_notify_gate_enabled", return_value=True)
@patch("app.services.main_group_notifications._last_loud_at")
def test_second_loud_in_window_forced_silent(last_mock, _enabled):
    last_mock.return_value = datetime.utcnow() - timedelta(minutes=30)
    silent = resolve_main_group_send_silent(
        channel_identifier=MAIN_GROUP_IDENT,
        post_send_silent=False,
        had_media=True,
    )
    assert silent is True
