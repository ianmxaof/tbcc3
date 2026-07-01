"""Tests for growth reaction proposals (growth_reaction.py).

Proposals are observe-only drafts derived from signals; storage is a Redis set
(faked here). Verifies mapping, stable content-hash ids (dismissal survives
recompute), and dismissed filtering.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.channel import Channel
from app.models.post_delivery_metric import PostDeliveryMetric
from app.services import content_signals as cs
from app.services import growth_reaction as gr


class FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.sets: dict[str, set] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = str(value)

    def sadd(self, key, *vals):
        self.sets.setdefault(key, set()).update(str(v) for v in vals)

    def smembers(self, key):
        return set(self.sets.get(key, set()))


PEAK = {
    "signal_type": "peak_post_hour",
    "confidence": "medium",
    "strength": 0.5,
    "hour_local": 20,
    "vs_network_avg": 1.6,
    "recommendation": "Bias recurring posts toward 20:00.",
}
CAPTION = {
    "signal_type": "caption_slot_winner",
    "confidence": "high",
    "strength": 0.7,
    "scheduled_post_id": 42,
    "caption_slot_index": 1,
    "scheduler_name": "Daily tease",
    "recommendation": "Caption slot 1 wins.",
}
CHANNEL = {
    "signal_type": "channel_view_leader",
    "confidence": "medium",
    "strength": 0.6,
    "channel_id": 7,
    "channel_name": "Lane A",
    "recommendation": "Lane A leads.",
}
CONVERSION = {
    "signal_type": "conversion_hour",
    "confidence": "high",
    "strength": 0.8,
    "hour_local": 21,
    "recommendation": "Conversions cluster at 21:00.",
}
OBSERVATIONAL = {"signal_type": "industry_benchmark", "confidence": "low", "strength": 0.3}


# --------------------------------------------------------------------------- #
# propose_reactions — mapping
# --------------------------------------------------------------------------- #

def test_propose_reactions_maps_all_actionable_types():
    report = {"timezone": "UTC", "signals": [PEAK, CAPTION, CHANNEL, CONVERSION, OBSERVATIONAL]}
    proposals = gr.propose_reactions(report)

    # Observational signal is dropped.
    kinds = {p["action_kind"] for p in proposals}
    assert kinds == {
        "schedule_hour_bias",
        "caption_slot_reuse",
        "increase_channel_frequency",
        "align_cta_window",
    }
    assert all(p["status"] == "pending" for p in proposals)
    assert all(p["id"] and p["recommendation"] for p in proposals)


def test_peak_proposal_action_params():
    [p] = gr.propose_reactions({"timezone": "US/Eastern", "signals": [PEAK]})
    assert p["signal_type"] == "peak_post_hour"
    assert p["action_params"]["target_hour_local"] == 20
    assert p["action_params"]["timezone"] == "US/Eastern"
    assert "mcp_followup" in p["action_params"]


def test_caption_proposal_carries_ids():
    [p] = gr.propose_reactions({"timezone": "UTC", "signals": [CAPTION]})
    assert p["action_params"]["scheduled_post_id"] == 42
    assert p["action_params"]["caption_slot_index"] == 1


def test_no_actionable_signals_yields_empty():
    assert gr.propose_reactions({"signals": [OBSERVATIONAL]}) == []
    assert gr.propose_reactions({"signals": []}) == []


# --------------------------------------------------------------------------- #
# Stable ids — dismissal must survive recompute
# --------------------------------------------------------------------------- #

def test_proposal_id_stable_across_metric_drift():
    # Same opportunity (hour 20), different volatile metrics -> same id.
    a = dict(PEAK, strength=0.5, vs_network_avg=1.6)
    b = dict(PEAK, strength=0.9, vs_network_avg=2.4, avg_views=999)
    assert gr._proposal_id(a) == gr._proposal_id(b)


def test_proposal_id_differs_by_identity():
    assert gr._proposal_id(PEAK) != gr._proposal_id(dict(PEAK, hour_local=21))
    assert gr._proposal_id(CHANNEL) != gr._proposal_id(dict(CHANNEL, channel_id=8))


# --------------------------------------------------------------------------- #
# list_proposals / dismiss — Redis-backed filtering
# --------------------------------------------------------------------------- #

def _seed(db):
    db.add(Channel(id=1, name="Lane A", identifier="@lane_a"))
    now = datetime.utcnow()
    for i in range(5):
        db.add(PostDeliveryMetric(created_at=now - timedelta(days=1, minutes=i),
                                  event_type="scheduled_post_sent", channel_id=1,
                                  posted_hour_local=20, views_latest=200))
    for i in range(5):
        db.add(PostDeliveryMetric(created_at=now - timedelta(days=1, minutes=100 + i),
                                  event_type="scheduled_post_sent", channel_id=1,
                                  posted_hour_local=3, views_latest=40))
    db.commit()


def test_list_proposals_returns_pending(db, monkeypatch):
    _seed(db)
    monkeypatch.setattr(cs, "_redis_client", lambda: FakeRedis())
    out = gr.list_proposals(db, days=14)
    assert out["ok"] is True
    assert out["proposal_count"] >= 1
    assert out["dismissed_count"] == 0
    assert any(p["signal_type"] == "peak_post_hour" for p in out["proposals"])


def test_dismiss_then_filtered_out(db, monkeypatch):
    _seed(db)
    fake = FakeRedis()
    monkeypatch.setattr(cs, "_redis_client", lambda: fake)

    before = gr.list_proposals(db, days=14)
    target = before["proposals"][0]["id"]

    res = gr.dismiss_proposal(target)
    assert res["ok"] is True and res["dismissed"] is True

    after = gr.list_proposals(db, days=14)
    assert all(p["id"] != target for p in after["proposals"])
    assert after["dismissed_count"] == before["dismissed_count"] + 1


def test_dismiss_empty_id_rejected():
    assert gr.dismiss_proposal("")["ok"] is False


# --------------------------------------------------------------------------- #
# tick integration — proposed_actions on digest change
# --------------------------------------------------------------------------- #

def test_tick_includes_proposed_actions_on_change(db, monkeypatch):
    _seed(db)
    fake = FakeRedis({cs.REDIS_LAST_DIGEST: "stale"})
    monkeypatch.setattr(cs, "_redis_client", lambda: fake)

    result = cs.tick_growth_signals(db, refresh_views=False, push_inbox_on_change=False)
    assert result["digest_changed"] is True
    assert isinstance(result["proposed_actions"], list)
    assert any(p["signal_type"] == "peak_post_hour" for p in result["proposed_actions"])


def test_tick_no_proposals_when_unchanged(db, monkeypatch):
    _seed(db)
    report = cs.compute_strong_signals(db)
    digest = cs._digest_hash(report)
    monkeypatch.setattr(cs, "_redis_client", lambda: FakeRedis({cs.REDIS_LAST_DIGEST: digest}))

    result = cs.tick_growth_signals(db, refresh_views=False, push_inbox_on_change=False)
    assert result["digest_changed"] is False
    assert result["proposed_actions"] == []
