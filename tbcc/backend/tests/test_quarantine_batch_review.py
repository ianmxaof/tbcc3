"""Q&A batch approve must not stamp lead-only Redis picks onto every item."""

from __future__ import annotations

import json

import pytest


class _FakeRedis:
    def __init__(self, store: dict[str, str]):
        self.store = store

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def batch_redis(monkeypatch):
    store: dict[str, str] = {}
    fake = _FakeRedis(store)
    monkeypatch.setattr("app.services.quarantine_batch_review._redis", lambda: fake)
    monkeypatch.setattr("app.services.gatekeeper_lane_picker._redis", lambda: fake)
    return store


def test_store_and_load_batch_payload(batch_redis):
    from app.services.quarantine_batch_review import (
        _store_batch,
        load_batch_media_ids,
        load_batch_payload,
        batch_id_for_lead_media,
    )

    _store_batch("abcd", [10, 11, 12], lane_key="taboo", lead_media_id=12)
    payload = load_batch_payload("abcd")
    assert payload["media_ids"] == [10, 11, 12]
    assert payload["lane_key"] == "taboo"
    assert payload["lead_media_id"] == 12
    assert load_batch_media_ids("abcd") == [10, 11, 12]
    assert batch_id_for_lead_media(12) == "abcd"


def test_legacy_list_payload_still_loads(batch_redis):
    from app.services.quarantine_batch_review import BATCH_KEY_PREFIX, load_batch_payload

    batch_redis[f"{BATCH_KEY_PREFIX}legacy"] = json.dumps([1, 2, 3])
    payload = load_batch_payload("legacy")
    assert payload["media_ids"] == [1, 2, 3]
    assert payload["lead_media_id"] == 1


def test_fanout_toggle_writes_all_members(batch_redis):
    from app.services.quarantine_batch_review import (
        _store_batch,
        toggle_batch_picked_lane,
    )
    from app.services.gatekeeper_lane_picker import get_picked_lanes

    _store_batch("b1", [101, 102, 103], lane_key="ass", lead_media_id=101)
    selected = toggle_batch_picked_lane("b1", "taboo")
    assert "taboo" in selected
    for mid in (101, 102, 103):
        assert "taboo" in get_picked_lanes(mid)


def test_approve_batch_uses_batch_lane_not_empty_lead_stamp(batch_redis, monkeypatch):
    from app.services import quarantine_batch_review as qbr

    qbr._store_batch("b2", [201, 202, 203], lane_key="voyeur", lead_media_id=201)

    seen: list[tuple[int, list[str] | None]] = []

    def _approve(db, mid, *, operator_id=None, lane_keys=None):
        seen.append((int(mid), list(lane_keys) if lane_keys else None))
        return {"ok": True, "media_id": mid, "route_enqueue_ok": True}

    monkeypatch.setattr("app.services.gatekeeper_review.operator_approve_media", _approve)
    monkeypatch.setattr(
        "app.services.gatekeeper_lane_picker.get_picked_lanes",
        lambda mid: [],
    )

    out = qbr.operator_approve_batch(object(), "b2", operator_id=1)
    assert out["ok"] is True
    assert out["approved"] == 3
    assert seen == [
        (201, ["voyeur"]),
        (202, ["voyeur"]),
        (203, ["voyeur"]),
    ]


def test_approve_batch_operator_picks_fanout_not_lead_only_wrong_stamp(batch_redis, monkeypatch):
    """Operator toggled taboo on the batch card — all items get taboo, not a phantom lead-only map."""
    from app.services import quarantine_batch_review as qbr
    from app.services.gatekeeper_lane_picker import set_picked_lanes

    qbr._store_batch("b3", [301, 302, 303, 304, 305], lane_key="ass", lead_media_id=301)
    # Bug shape: only lead has a Redis pick (old keyboard wrote lead only)
    set_picked_lanes(301, ["taboo"])

    seen: dict[int, list[str] | None] = {}

    def _approve(db, mid, *, operator_id=None, lane_keys=None):
        seen[int(mid)] = list(lane_keys) if lane_keys else None
        return {"ok": True, "media_id": mid, "route_enqueue_ok": True}

    monkeypatch.setattr("app.services.gatekeeper_review.operator_approve_media", _approve)

    out = qbr.operator_approve_batch(object(), "b3")
    assert out["ok"] is True
    # Fan-out before approve: every item stamped taboo (operator intent), not ass from lead emptiness
    assert all(seen[m] == ["taboo"] for m in (301, 302, 303, 304, 305))


def test_batch_keyboard_uses_batch_toggle_callbacks(batch_redis, monkeypatch):
    from app.services.quarantine_batch_review import (
        CALLBACK_BATCH_TOGGLE,
        CALLBACK_BATCH_APPROVE,
        batch_review_keyboard,
    )

    monkeypatch.setattr(
        "app.services.gatekeeper_lane_picker.gatekeeper_lane_picker_keys",
        lambda: ["ass", "taboo"],
    )
    monkeypatch.setattr(
        "app.services.gatekeeper_review.panel_open_callback",
        lambda lane: "gk:panel:open",
    )
    kb = batch_review_keyboard("zz99", 500, lane_key="ass")
    datas = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert any(d.startswith(f"{CALLBACK_BATCH_TOGGLE}zz99:") for d in datas)
    assert f"{CALLBACK_BATCH_APPROVE}zz99" in datas
    assert not any(d.startswith("gk:t:") for d in datas)


def test_parse_batch_toggle_callback():
    from app.services.quarantine_batch_review import parse_batch_review_callback

    assert parse_batch_review_callback("gk:bt:abcd:taboo") == ("toggle_lane", "abcd", "taboo")
    assert parse_batch_review_callback("gk:ba:abcd") == ("approve", "abcd")
