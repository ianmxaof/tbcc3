"""Analytics direction ranking + bundle tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import analytics_direction as ad


def _minimal_bundle(
    *,
    blockers=None,
    proposals=None,
    approved=2000,
    contradictions=None,
):
    return {
        "ops": {
            "blockers": blockers or [],
            "pools": {"approved_total": approved},
            "posts": {"failure_pct": 5, "outbound_total": 100, "outbound_failed": 5},
        },
        "funnel_signals": [],
        "growth_proposals": proposals or [],
        "export_proposals": [],
        "category_demand": {"gaps": []},
        "contradictions": contradictions or [],
        "sprint_labels": ["Loot album delivery"],
    }


def test_rank_directions_blocker_beats_weak_proposal():
    bundle = _minimal_bundle(
        blockers=[
            {
                "id": "revenue_stall",
                "severity": "high",
                "what": "No income 7d",
                "why": "Stall",
                "evidence": "latest=old",
            }
        ],
        proposals=[
            {
                "id": "p1",
                "action_kind": "review",
                "recommendation": "Weak signal",
                "strength": 0.2,
                "confidence": "low",
                "action_params": {},
            }
        ],
    )
    directions = ad.rank_directions(bundle)
    assert len(directions) <= 5
    assert directions[0]["source"] == "blocker"
    assert directions[0]["blocker_id"] == "revenue_stall"


def test_rank_directions_thin_pool_penalizes_cadence():
    bundle = _minimal_bundle(
        approved=100,
        proposals=[
            {
                "id": "cadence1",
                "action_kind": "increase_pool_cadence",
                "network_key": "voyeur",
                "recommendation": "Post more voyeur",
                "strength": 0.9,
                "confidence": "high",
                "action_params": {"network_key": "voyeur"},
            }
        ],
        contradictions=[
            {"proposal_id": "cadence1", "code": "thin_pool_vs_post_more", "message": "thin"},
        ],
    )
    directions = ad.rank_directions(bundle)
    pool_fix = next((d for d in directions if d.get("source") == "pool_pressure"), None)
    assert pool_fix is not None
    cadence = next((d for d in directions if d.get("action_kind") == "increase_pool_cadence"), None)
    if cadence and pool_fix:
        assert pool_fix["rank"] < cadence["rank"]


def test_rank_directions_dedupe_same_network():
    bundle = _minimal_bundle(
        proposals=[
            {
                "id": "a",
                "action_kind": "boost_lane_export",
                "network_key": "ai",
                "recommendation": "Export AI lane",
                "strength": 0.8,
                "confidence": "high",
                "action_params": {"network_key": "ai"},
            },
            {
                "id": "b",
                "action_kind": "boost_lane_export",
                "network_key": "ai",
                "recommendation": "Export AI lane again",
                "strength": 0.7,
                "confidence": "medium",
                "action_params": {"network_key": "ai"},
            },
        ],
    )
    directions = ad.rank_directions(bundle)
    export_dirs = [d for d in directions if d.get("network_key") == "ai"]
    assert len(export_dirs) == 1


def test_format_direction_markdown_smoke():
    bundle = _minimal_bundle()
    directions = [{"rank": 1, "horizon": "ST", "title": "Fix X", "category": "fix", "confidence": "high", "rationale": "r"}]
    md = ad.format_direction_markdown(bundle, directions)
    assert "TBCC analytics direction" in md
    assert "Fix X" in md


def test_draft_direction_narrative_skipped_without_llm():
    bundle = _minimal_bundle()
    directions = [{"rank": 1, "title": "A", "horizon": "ST", "category": "fix"}]
    assert ad.draft_direction_narrative(bundle, directions, use_llm=False) is None


@patch("app.services.analytics_direction.build_ops_picture_report")
@patch("app.services.analytics_direction.list_proposals")
@patch("app.services.analytics_direction.spike_state", return_value={"hits_in_window": 0})
@patch("app.services.analytics_direction.traffic_pulse_snapshot", return_value={"counts": {}, "top_refs": []})
@patch("app.services.content_signals.compute_strong_signals")
def test_build_direction_evidence_bundle_shape(
    mock_signals,
    _pulse,
    _spike,
    mock_proposals,
    mock_ops,
):
    mock_ops.return_value = {
        "blockers": [],
        "income": {"total_usd": 5},
        "companion": {"photos_sold": 1},
        "pools": {"approved_total": 1000},
        "posts": {},
    }
    mock_proposals.return_value = {"proposals": []}
    mock_signals.return_value = {"signals": []}
    with patch.object(ad, "_compute_trends", return_value={"income_usd": 5}):
        with patch.object(ad, "_sprint_in_flight_labels", return_value=[]):
            bundle = ad.build_direction_evidence_bundle(MagicMock(), days=30)
    assert bundle["window_days"] == 30
    assert "evidence_summary" in bundle
    assert "trends" in bundle


def test_build_analytics_direction_report(monkeypatch):
    monkeypatch.setattr(
        ad,
        "build_direction_evidence_bundle",
        lambda _db, days=30: _minimal_bundle(),
    )
    monkeypatch.setattr(
        ad,
        "rank_directions",
        lambda _b: [{"rank": 1, "horizon": "ST", "title": "T", "category": "fix", "confidence": "high"}],
    )
    monkeypatch.setattr(ad, "draft_direction_narrative", lambda *a, **k: None)
    report = ad.build_analytics_direction_report(MagicMock(), days=30, use_llm=False)
    assert report["ok"] is True
    assert len(report["directions"]) == 1
    assert "markdown" in report
