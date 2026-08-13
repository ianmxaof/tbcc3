"""Tests for hub-first scrape gate."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_batch_scrape import queue_batch_scrapes, scrape_hub_first_enabled


def test_scrape_hub_first_enabled_default():
    with patch.dict("os.environ", {}, clear=True):
        assert scrape_hub_first_enabled() is True


def test_queue_batch_scrapes_blocked_when_hub_first():
    db = MagicMock()
    with patch("app.services.aof_batch_scrape.scrape_hub_first_enabled", return_value=True):
        out = queue_batch_scrapes(db, [1, 2, 3])
    assert out["hub_first"] is True
    assert out["queued_count"] == 0
    assert out["skipped_count"] == 3
    assert out["skipped"][0]["reason"] == "hub_first_blocked"
