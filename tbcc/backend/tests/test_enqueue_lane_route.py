"""enqueue_lane_route_for_media must not swallow Celery failures at debug."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


def test_enqueue_lane_route_success(monkeypatch):
    from app.services import gatekeeper_review as gr

    task = MagicMock()
    monkeypatch.setattr(
        "app.workers.gatekeeper_review_worker.route_approved_lanes_task",
        task,
        raising=False,
    )
    # Patch the import site used inside the function
    import sys
    from types import ModuleType

    mod = ModuleType("app.workers.gatekeeper_review_worker")
    mod.route_approved_lanes_task = task
    monkeypatch.setitem(sys.modules, "app.workers.gatekeeper_review_worker", mod)

    out = gr.enqueue_lane_route_for_media(42, ["ass", "milf"])
    assert out["ok"] is True
    assert out["queued"] is True
    task.delay.assert_called_once_with(42, ["ass", "milf"])


def test_enqueue_lane_route_failure_logs_exception(monkeypatch, caplog):
    from app.services import gatekeeper_review as gr

    task = MagicMock()
    task.delay.side_effect = RuntimeError("redis down")
    import sys
    from types import ModuleType

    mod = ModuleType("app.workers.gatekeeper_review_worker")
    mod.route_approved_lanes_task = task
    monkeypatch.setitem(sys.modules, "app.workers.gatekeeper_review_worker", mod)

    with caplog.at_level(logging.ERROR):
        out = gr.enqueue_lane_route_for_media(99, ["taboo"])

    assert out["ok"] is False
    assert out["queued"] is False
    assert "redis down" in (out.get("reason") or "")
    assert "lane route enqueue FAILED" in caplog.text


def test_enqueue_empty_lanes():
    from app.services.gatekeeper_review import enqueue_lane_route_for_media

    out = enqueue_lane_route_for_media(1, [])
    assert out["ok"] is False
    assert out["reason"] == "no_lane_keys"


def test_operator_approve_does_not_claim_routed_on_enqueue_fail(monkeypatch):
    from app.services import gatekeeper_review as gr

    class _Media:
        id = 7
        status = "quarantine"
        pool_id = None
        classification_json = '{"gatekeeper":{"verdict":"quarantine"}}'
        file_unique_id = "x"

    class _Q:
        def __init__(self, m):
            self._m = m

        def filter(self, *a, **k):
            return self

        def first(self):
            return self._m

    class _Db:
        def query(self, *a):
            return _Q(_Media())

        def commit(self):
            pass

    monkeypatch.setattr(gr, "gatekeeper_verdict_from_media", lambda m: "quarantine")
    monkeypatch.setattr(gr, "resolve_media_lane_key", lambda db, m: "ass")
    monkeypatch.setattr(gr, "record_operator_approve", lambda db, m: None)
    monkeypatch.setattr(gr, "enqueue_vault_approved_media", lambda mid: None)
    monkeypatch.setattr(gr, "approve_triggers_micro_pull", lambda: False)
    monkeypatch.setattr(
        gr,
        "enqueue_lane_route_for_media",
        lambda mid, lanes: {"ok": False, "queued": False, "reason": "boom"},
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: None,
    )
    monkeypatch.setattr(
        "app.services.gatekeeper_lane_picker.lane_picker_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.gatekeeper_lane_picker.clear_picked_lanes",
        lambda mid: None,
    )
    monkeypatch.setattr(
        "app.services.gatekeeper_lane_picker.get_picked_lanes",
        lambda mid: [],
    )
    monkeypatch.setattr(gr, "_merge_operator_action", lambda *a, **k: None)

    out = gr.operator_approve_media(_Db(), 7, lane_keys=["ass"])
    assert out["ok"] is True
    assert out["routed_lanes"] == []
    assert out["route_enqueue_ok"] is False
    assert out["route_enqueue_error"] == "boom"
