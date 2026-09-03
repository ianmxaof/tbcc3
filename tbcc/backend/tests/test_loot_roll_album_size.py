"""Paid roll album size includes interval bonus_album_draws (capped)."""

from __future__ import annotations

from app.services.loot_roll_preview import loot_album_max_items


def _paid_album_size(base_rarity: int, bonus_draws: int, *, cap: int | None = None) -> int:
    """Mirror loot_roll_preview paid-roll sizing."""
    limit = int(cap) if cap is not None else loot_album_max_items()
    return min(limit, int(base_rarity) + int(bonus_draws or 0))


def test_default_cap_keeps_draws_small(monkeypatch) -> None:
    monkeypatch.delenv("TBCC_LOOT_ALBUM_MAX", raising=False)
    assert loot_album_max_items() == 3
    assert _paid_album_size(5, 1) == 3


def test_env_can_raise_cap_for_bonus_draws(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_LOOT_ALBUM_MAX", "12")
    assert _paid_album_size(5, 1) == 6
    assert _paid_album_size(5, 2) == 7
    assert _paid_album_size(10, 2) == 12
