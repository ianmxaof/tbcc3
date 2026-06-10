"""Plan Telegram album chunk sizes when a send-promo tile rides in the last album."""
from __future__ import annotations

import math
from typing import TypeVar

T = TypeVar("T")

TELEGRAM_ALBUM_MAX = 10
GALLERY_SEND_PROMO_SOURCE = "extension:send-promo"


def plan_album_batch_sizes(batch_count: int, include_promo_tail: bool, max_size: int = TELEGRAM_ALBUM_MAX) -> list[int]:
    """
    Sizes of each album's batch-media slots (promo is not counted here).

    When include_promo_tail is True, the promo image is added server-side as the last
    media in the final album (≤ max_size items total in that album).
    """
    n = max(0, int(batch_count))
    max_size = max(1, int(max_size))
    if not include_promo_tail:
        if n == 0:
            return []
        return [min(max_size, n - i) for i in range(0, n, max_size)]
    if n == 0:
        return [0]
    k = math.ceil((n + 1) / max_size)
    sizes: list[int] = []
    i = 0
    for album_idx in range(k):
        is_last = album_idx == k - 1
        if is_last:
            sizes.append(n - i)
        else:
            take = max_size
            prefix_full = (k - 1) * max_size
            remainder = n - prefix_full
            if album_idx == k - 2 and remainder == 0:
                take = max_size - 1
            sizes.append(take)
            i += take
    return sizes


def chunk_sequence_with_promo_tail(
    batch_items: list[T],
    promo_item: T | None,
    max_size: int = TELEGRAM_ALBUM_MAX,
) -> list[list[T]]:
    """Split batch items into album chunks; promo_item is included in the last chunk."""
    if not batch_items and promo_item is not None:
        return [[promo_item]]
    if promo_item is None:
        return [batch_items[i : i + max_size] for i in range(0, len(batch_items), max_size)]
    sizes = plan_album_batch_sizes(len(batch_items), True, max_size)
    chunks: list[list[T]] = []
    i = 0
    for album_idx, size in enumerate(sizes):
        is_last = album_idx == len(sizes) - 1
        part = batch_items[i : i + size]
        i += size
        if is_last:
            part = [*part, promo_item]
        chunks.append(part)
    return chunks
