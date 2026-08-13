"""Paid roll album size includes interval bonus_album_draws (capped)."""

from __future__ import annotations


def _paid_album_size(base_rarity: int, bonus_draws: int, *, cap: int = 12) -> int:
    """Mirror loot_roll_preview paid-roll sizing."""
    return min(cap, int(base_rarity) + int(bonus_draws or 0))


def test_m30_bonus_one_draw() -> None:
    assert _paid_album_size(5, 1) == 6


def test_m15_bonus_two_draws() -> None:
    assert _paid_album_size(5, 2) == 7


def test_album_size_cap_at_twelve() -> None:
    assert _paid_album_size(10, 2) == 12
