"""Tests for collective-random pool selection on scheduled posts."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.scheduled_text_post import ScheduledTextPost
from app.services import scheduled_post_service as svc


def _mock_media(mid: int, pool_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=mid, pool_id=pool_id, status="approved", media_type="photo", telegram_message_id=mid)


def test_post_uses_pool_collective_random():
    post = ScheduledTextPost(content="hi", channel_id=1, pool_collective_random=True)
    assert svc._post_uses_pool(post) is True


def test_pick_collective_pool_id_returns_one_of_eligible():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = [
        (1,),
        (2,),
    ]
    with patch.object(svc.random, "choice", return_value=2):
        assert svc._pick_collective_pool_id(db) == 2


def test_load_pool_media_items_collective_uses_chosen_pool():
    post = ScheduledTextPost(
        content="hi",
        channel_id=1,
        pool_collective_random=True,
        album_size=2,
        pool_randomize=False,
    )
    db = MagicMock()
    pool = SimpleNamespace(id=7, album_size=5, randomize_queue=False)
    media_rows = [_mock_media(10, 7), _mock_media(11, 7), _mock_media(12, 7)]

    with patch.object(svc, "_pick_collective_pool_id", return_value=7):
        db.query.return_value.filter.return_value.first.return_value = pool
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = media_rows[:2]

        items = svc._load_pool_media_items(post, db, "static")

    assert len(items) == 2
    assert {m.id for m in items} == {10, 11}
