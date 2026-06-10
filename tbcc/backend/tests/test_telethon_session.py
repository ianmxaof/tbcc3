"""Telethon session path helpers."""

from __future__ import annotations

import os

from app.utils.telethon_session import (
    admin_session_stem,
    import_session_stem,
    import_sessions_share_admin_file,
    telethon_disconnect_admin_after_io,
    telethon_disconnect_import_after_io,
)


def test_import_session_defaults_separate_from_admin(monkeypatch):
    monkeypatch.delenv("TBCC_IMPORT_TELEGRAM_SESSION", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION_PATH", raising=False)
    assert import_session_stem().endswith("admin_import")
    assert import_sessions_share_admin_file() is False


def test_import_session_shares_admin_when_configured_same(monkeypatch):
    admin = admin_session_stem()
    monkeypatch.setenv("TBCC_IMPORT_TELEGRAM_SESSION", os.path.basename(admin))
    assert import_sessions_share_admin_file() is True


def test_disconnect_after_io_off_when_sessions_separate(monkeypatch):
    monkeypatch.delenv("TBCC_TELEGRAM_DISCONNECT_AFTER_IO", raising=False)
    monkeypatch.delenv("TBCC_IMPORT_TELEGRAM_DISCONNECT_AFTER_IO", raising=False)
    monkeypatch.delenv("TBCC_IMPORT_TELEGRAM_SESSION", raising=False)
    monkeypatch.delenv("TBCC_POSTER_TELEGRAM_SESSION", raising=False)
    assert import_sessions_share_admin_file() is False
    assert telethon_disconnect_admin_after_io() is False
    assert telethon_disconnect_import_after_io() is False


def test_disconnect_after_io_env_override(monkeypatch):
    monkeypatch.setenv("TBCC_TELEGRAM_DISCONNECT_AFTER_IO", "1")
    assert telethon_disconnect_admin_after_io() is True
    assert telethon_disconnect_import_after_io() is True
