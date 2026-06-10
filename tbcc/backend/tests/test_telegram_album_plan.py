"""Telegram album chunk planning with gallery send-promo in the last album."""
from app.services.telegram_album_plan import chunk_sequence_with_promo_tail, plan_album_batch_sizes


def _batch_sizes_from_chunks(chunks: list[list], promo_marker: str = "__promo__") -> list[int]:
    out = []
    for ch in chunks:
        n = sum(1 for x in ch if x != promo_marker)
        out.append(n)
    return out


def test_plan_21_batch_includes_promo_in_last_album():
    assert plan_album_batch_sizes(21, True) == [10, 10, 1]


def test_plan_20_batch_peels_one_for_promo_album():
    assert plan_album_batch_sizes(20, True) == [10, 9, 1]


def test_chunk_20_plus_promo_last_album():
    batch = [f"b{i}" for i in range(20)]
    chunks = chunk_sequence_with_promo_tail(batch, "__promo__")
    assert len(chunks) == 3
    assert len(chunks[0]) == 10
    assert len(chunks[1]) == 9
    assert chunks[1][-1] != "__promo__"
    assert chunks[2] == ["b19", "__promo__"]


def test_chunk_21_plus_promo():
    batch = [f"b{i}" for i in range(21)]
    chunks = chunk_sequence_with_promo_tail(batch, "__promo__")
    assert len(chunks) == 3
    assert chunks[2] == ["b20", "__promo__"]
