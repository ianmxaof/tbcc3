"""Per-customer Pilot/Auto reply mode."""

from __future__ import annotations

import os

import pytest

from app.models.secretary_user_context import SecretaryUserContext
from app.services.secretary_reply_mode import (
    get_reply_mode,
    get_stored_reply_mode,
    inherit_reply_mode,
    mode_label,
    set_reply_mode,
)


@pytest.fixture()
def db_session(db):
    return db


def test_inherit_business_defaults_pilot(monkeypatch):
    monkeypatch.delenv("TBCC_SECRETARY_AUTO_REPLY", raising=False)
    assert inherit_reply_mode(is_business=True) == "pilot"


def test_inherit_business_auto(monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_AUTO_REPLY", "1")
    assert inherit_reply_mode(is_business=True) == "auto"


def test_inherit_direct_defaults_pilot(monkeypatch):
    monkeypatch.delenv("TBCC_SECRETARY_SUGGEST_DIRECT", raising=False)
    assert inherit_reply_mode(is_business=False) == "pilot"


def test_inherit_direct_auto_when_suggest_off(monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_SUGGEST_DIRECT", "0")
    assert inherit_reply_mode(is_business=False) == "auto"


def test_set_and_get_overrides_env(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_AUTO_REPLY", "1")
    uid = 9_001_001
    assert get_reply_mode(db, uid, is_business=True) == "auto"
    set_reply_mode(db, uid, "pilot")
    assert get_stored_reply_mode(db, uid) == "pilot"
    assert get_reply_mode(db, uid, is_business=True) == "pilot"
    set_reply_mode(db, uid, "auto")
    assert get_reply_mode(db, uid, is_business=True) == "auto"


def test_set_reply_mode_rejects_bad(db):
    with pytest.raises(ValueError):
        set_reply_mode(db, 1, "fly")


def test_mode_label():
    assert mode_label("pilot") == "Pilot"
    assert mode_label("auto") == "Auto"


def test_row_null_inherits(db, monkeypatch):
    monkeypatch.delenv("TBCC_SECRETARY_AUTO_REPLY", raising=False)
    uid = 9_001_002
    db.add(SecretaryUserContext(telegram_user_id=uid, reply_mode=None))
    db.commit()
    assert get_stored_reply_mode(db, uid) is None
    assert get_reply_mode(db, uid, is_business=True) == "pilot"
