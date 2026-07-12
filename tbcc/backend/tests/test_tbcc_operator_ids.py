"""Shared TBCC operator registry."""

from __future__ import annotations

from app.services.tbcc_operator_ids import (
    HARDCODED_TBCC_OPERATOR_IDS,
    is_tbcc_operator,
    tbcc_operator_ids,
)


def test_hardcoded_primary_and_secondary():
    assert 7787282561 in HARDCODED_TBCC_OPERATOR_IDS
    assert 8630278848 in HARDCODED_TBCC_OPERATOR_IDS
    assert is_tbcc_operator(7787282561)
    assert is_tbcc_operator(8630278848)
    assert not is_tbcc_operator(111)


def test_env_extends_operators(monkeypatch):
    monkeypatch.setenv("TBCC_OPERATOR_IDS", "555001")
    ids = tbcc_operator_ids()
    assert 555001 in ids
    assert 7787282561 in ids
