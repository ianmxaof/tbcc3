"""Canonical TBCC / AOF operator Telegram user ids (owner + alt).

Hardcoded ids always have full product access (bots, gates, rolls, companion).
Env vars can *extend* the set; they cannot remove hardcoded operators.
"""

from __future__ import annotations

import os
import re

# Primary @FreeUseDistrictManager + secondary account (confirmed by owner).
# Do not store phone numbers here — ids only.
HARDCODED_TBCC_OPERATOR_IDS: frozenset[int] = frozenset(
    {
        7787282561,  # primary
        8630278848,  # secondary
    }
)

_ENV_KEYS: tuple[str, ...] = (
    "ADMIN_TELEGRAM_ID",
    "TBCC_OPERATOR_IDS",
    "TBCC_LOOT_OPERATOR_IDS",
    "TBCC_LOOT_UNLIMITED_USER_IDS",
    "TBCC_COMPANION_ADMIN_IDS",
    "TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS",
    "TBCC_SECRETARY_ADMIN_IDS",
    "TBCC_INBOX_ADMIN_IDS",
)


def _parse_id_token(token: str) -> int | None:
    text = (token or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def tbcc_operator_ids() -> frozenset[int]:
    ids: set[int] = set(HARDCODED_TBCC_OPERATOR_IDS)
    for key in _ENV_KEYS:
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        for part in raw.replace(";", ",").split(","):
            parsed = _parse_id_token(part)
            if parsed is not None:
                ids.add(parsed)
    return frozenset(ids)


def is_tbcc_operator(telegram_user_id: int | None) -> bool:
    if not telegram_user_id:
        return False
    return int(telegram_user_id) in tbcc_operator_ids()
