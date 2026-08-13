"""Album dedupe — one Telegram file per media-group slot."""

from types import SimpleNamespace

from app.services.media_album_dedupe import dedupe_media_for_album, select_unique_pool_media


def _row(mid: int, *, tid: int = 0, fu: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=mid, telegram_message_id=tid, file_unique_id=fu)


def test_dedupe_collapses_same_telegram_message_id():
    rows = [
        _row(1, tid=100, fu="a"),
        _row(2, tid=100, fu="a"),
        _row(3, tid=101, fu="b"),
    ]
    out = dedupe_media_for_album(rows)
    assert [m.id for m in out] == [1, 3]


def test_dedupe_collapses_same_file_unique_id():
    rows = [
        _row(1, tid=100, fu="same"),
        _row(2, tid=101, fu="same"),
    ]
    out = dedupe_media_for_album(rows)
    assert [m.id for m in out] == [1]


def test_select_unique_pool_media_caps_after_dedupe():
    rows = [_row(i, tid=100) for i in range(1, 8)]
    out = select_unique_pool_media(rows, 5, randomize=False)
    assert len(out) == 1
    assert out[0].id == 1


def test_select_unique_pool_media_randomize_preserves_uniqueness():
    rows = [_row(i, tid=i) for i in range(1, 6)]
    out = select_unique_pool_media(rows, 3, randomize=True)
    assert len(out) == 3
    assert len({m.telegram_message_id for m in out}) == 3
