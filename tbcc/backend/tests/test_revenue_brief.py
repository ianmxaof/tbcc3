"""Daily revenue brief bundle + heuristic fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import growth_reaction, revenue_brief


def test_propose_funnel_signals_undress_spike():
    ops = {"companion": {"photos_sold": 0}}
    spike = {"spike_active": True, "hits_in_window": 10, "threshold": 8}
    signals = growth_reaction.propose_funnel_signals(ops, spike)
    kinds = {s["signal_type"] for s in signals}
    assert "bridge_undress_funnel" in kinds
    assert "boost_companion_cta" in kinds


def test_heuristic_brief_includes_spike():
    bundle = {
        "undress_spike": {"spike_active": True, "hits_in_window": 12, "threshold": 8},
        "blockers": [{"what": "Loot keys low", "why": "pool thin"}],
        "growth_proposals": [],
    }
    html = revenue_brief._heuristic_brief(bundle)
    assert "Undress" in html
    assert "now" in html
    assert "<blockquote>" in html
    assert "&lt;b&gt;" not in html


def test_build_revenue_brief_bundle_shape(monkeypatch):
    monkeypatch.setattr("app.services.revenue_brief.spike_state", lambda: {"hits_in_window": 0})
    monkeypatch.setattr("app.services.revenue_brief.traffic_pulse_snapshot", lambda: {"counts": {}, "top_refs": []})
    monkeypatch.setattr(
        "app.services.analytics_direction.build_direction_evidence_bundle",
        lambda _db, days=7: {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "ops": {
                "income": {"total_usd": 10, "total_stars": 5},
                "companion": {"photos_sold": 0},
                "bot_funnel": {"attributed_revenue_pct": 12},
                "blockers": [],
                "gate_funnel": {"totals": {"pass": 1}},
                "pools": {"approved_total": 1000},
                "posts": {},
            },
            "growth_proposals": [{"recommendation": "test", "action_kind": "review"}],
            "funnel_signals": [
                {
                    "signal_type": "boost_companion_cta",
                    "confidence": "medium",
                    "strength": 1.0,
                    "photos_sold": 0,
                    "recommendation": "Companion CTA",
                }
            ],
            "traffic_pulse": {"counts": {}, "top_refs": []},
            "sprint_labels": [],
            "contradictions": [],
            "category_demand": {"gaps": []},
            "export_proposals": [],
            "trends": {},
            "evidence_summary": {},
        },
    )
    monkeypatch.setattr(
        "app.services.analytics_direction.rank_directions",
        lambda _b: [{"rank": 1, "horizon": "ST", "title": "Companion CTA", "category": "grow", "confidence": "medium"}],
    )
    bundle = revenue_brief.build_revenue_brief_bundle(MagicMock(), days=7)
    assert bundle["income_usd"] == 10
    assert "growth_flywheel_note" in bundle
    assert "funnel_signals" in bundle
    assert any(s["signal_type"] == "boost_companion_cta" for s in bundle["funnel_signals"])


def test_draft_revenue_brief_fallback_without_llm():
    bundle = {"blockers": [{"what": "x", "why": "y"}], "growth_proposals": [], "undress_spike": {}}
    html = revenue_brief.draft_revenue_brief_html(bundle, use_llm=False)
    assert "revenue brief" in html.lower()


def test_is_revenue_brief_due(monkeypatch):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    monkeypatch.setenv("TBCC_REVENUE_BRIEF_TZ", "UTC")
    monkeypatch.setenv("TBCC_REVENUE_BRIEF_LOCAL_HOUR", "9")
    monkeypatch.setenv("TBCC_REVENUE_BRIEF_LOCAL_MINUTE", "30")
    due = datetime(2026, 7, 31, 9, 30, tzinfo=ZoneInfo("UTC"))
    not_due = datetime(2026, 7, 31, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert revenue_brief.is_revenue_brief_due(due) is True
    assert revenue_brief.is_revenue_brief_due(not_due) is False
