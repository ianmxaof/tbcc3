"""Loot bot operator / QA accounts — delegates to operator_sandbox (3 owner ids)."""

from __future__ import annotations

from app.services.operator_sandbox import is_operator_sandbox, operator_sandbox_ids


def loot_operator_ids() -> frozenset[int]:
    return operator_sandbox_ids()


def is_loot_operator(telegram_user_id: int | None) -> bool:
    return is_operator_sandbox(telegram_user_id)
