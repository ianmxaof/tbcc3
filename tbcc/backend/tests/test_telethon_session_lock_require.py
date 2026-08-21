"""Telethon session-lock enforcement for ad-hoc admin.session access."""

from __future__ import annotations

import pytest


def test_require_lock_raises_when_not_held(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REQUIRE_TELETHON_SESSION_LOCK", "1")
    tsl._held_set().clear()
    with pytest.raises(RuntimeError, match="Redis session lock not held"):
        tsl.require_telethon_session_lock("admin")


def test_require_lock_passes_when_held(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REQUIRE_TELETHON_SESSION_LOCK", "1")
    tsl._held_set().clear()
    tsl._mark_lock_held("admin")
    try:
        tsl.require_telethon_session_lock("admin")  # no raise
    finally:
        tsl._mark_lock_released("admin")


def test_require_lock_disabled(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REQUIRE_TELETHON_SESSION_LOCK", "0")
    tsl._held_set().clear()
    tsl.require_telethon_session_lock("admin")  # no raise
