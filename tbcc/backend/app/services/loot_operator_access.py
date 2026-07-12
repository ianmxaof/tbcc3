"""Loot bot operator / QA accounts — delegates to shared TBCC operators."""

from __future__ import annotations

from app.services.tbcc_operator_ids import is_tbcc_operator, tbcc_operator_ids


def loot_operator_ids() -> frozenset[int]:
    return tbcc_operator_ids()


def is_loot_operator(telegram_user_id: int | None) -> bool:
    return is_tbcc_operator(telegram_user_id)
