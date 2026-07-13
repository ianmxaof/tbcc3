"""Loot operator unlimited access (QA / admin)."""

from __future__ import annotations

from app.services.loot_operator_access import is_loot_operator, loot_operator_ids


def test_hardcoded_operators_include_primary_and_alt():
    ids = loot_operator_ids()
    assert 7787282561 in ids
    assert 8630278848 in ids


def test_is_loot_operator_true_for_primary(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_OPERATOR_IDS", raising=False)
    assert is_loot_operator(7787282561) is True
    assert is_loot_operator(8630278848) is True
    assert is_loot_operator(111) is False


def test_env_extends_operators(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_OPERATOR_IDS", "999001,999002")
    ids = loot_operator_ids()
    assert 999001 in ids
    assert 7787282561 in ids  # hardcoded still present
