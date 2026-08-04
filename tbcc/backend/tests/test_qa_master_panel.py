"""Q&A master panel + hub intake policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.hub_intake_policy import (
    auto_pipe_destination_label,
    hub_master_auto_approve_enabled,
    set_hub_master_auto_approve,
)
from app.services.storage_auto_pipe import (
    all_lanes_auto_pipe_on,
    set_all_lanes_auto_pipe,
    set_storage_auto_pipe_enabled,
)


def test_hub_master_auto_approve_redis_toggle(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

    monkeypatch.setattr("app.services.hub_intake_policy._redis", lambda: FakeRedis())
    monkeypatch.delenv("TBCC_GATEKEEPER_HUB_AUTO_APPROVE", raising=False)
    monkeypatch.delenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE", raising=False)

    assert hub_master_auto_approve_enabled() is True
    set_hub_master_auto_approve(False)
    assert hub_master_auto_approve_enabled() is False
    set_hub_master_auto_approve(True)
    assert hub_master_auto_approve_enabled() is True


def test_auto_pipe_destination_labels(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

    monkeypatch.setattr("app.services.hub_intake_policy._redis", lambda: FakeRedis())
    monkeypatch.setattr("app.services.storage_auto_pipe._redis", lambda: FakeRedis())

    set_storage_auto_pipe_enabled(False)
    assert "Manual" in auto_pipe_destination_label()

    set_all_lanes_auto_pipe(True)
    set_hub_master_auto_approve(True)
    assert "pool" in auto_pipe_destination_label()

    set_hub_master_auto_approve(False)
    assert "Q&A" in auto_pipe_destination_label()


def test_set_all_lanes_auto_pipe(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

    monkeypatch.setattr("app.services.storage_auto_pipe._redis", lambda: FakeRedis())
    set_all_lanes_auto_pipe(False)
    assert all_lanes_auto_pipe_on() is False
    set_all_lanes_auto_pipe(True)
    assert all_lanes_auto_pipe_on() is True


def test_format_qa_master_panel_includes_inventory():
    from app.services.qa_master_panel import format_qa_master_panel_html

    db = MagicMock()
    with patch("app.services.qa_master_panel.lane_inventory_rows", return_value=[]):
        with patch("app.services.gatekeeper_review.count_quarantine_waiting", return_value=3):
            with patch("app.services.gatekeeper_review.format_lane_pool_depth_html", return_value="depth"):
                with patch("app.services.intake_scheduler.format_status_text", return_value="intake"):
                    html = format_qa_master_panel_html(db, page=0)
    assert "MASTER PANEL" in html
    assert "Auto-pipe" in html
    assert "Auto-approve" in html
