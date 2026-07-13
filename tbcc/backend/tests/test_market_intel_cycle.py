"""Tests for weekly market-intel cycle evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services import erome_browse_intel as ebi
from app.services import market_intel_cycle as mic


def _patch_paths(monkeypatch, tmp_path):
    ledger = tmp_path / "browse-intel.jsonl"
    cycle_ledger = tmp_path / "market-intel-cycle.jsonl"
    monkeypatch.setattr(ebi, "ledger_path", lambda: ledger)
    monkeypatch.setattr(ebi, "browse_intel_enabled", lambda: True)
    monkeypatch.setattr(mic, "cycle_ledger_path", lambda: cycle_ledger)
    monkeypatch.setattr(mic, "cycle_enabled", lambda: True)
    monkeypatch.setattr(mic, "cycle_min_erome_rows", lambda: 3)
    monkeypatch.setattr(mic, "cycle_min_reddit_rows", lambda: 2)
    monkeypatch.setattr(mic, "cycle_confidence_min", lambda: 0.5)
    return ledger, cycle_ledger


def _erome_row(tag: str, views: int, day: str = "2026-07-06") -> dict:
    return {
        "platform": "erome",
        "captured_at": f"{day}T12:00:00Z",
        "album_url": f"https://www.erome.com/a/{tag}-{views}",
        "views": views,
        "likes": max(1, views // 50),
        "tags": [tag],
        "format_bucket": "multi_video",
    }


def _reddit_row(tag: str, score: int, day: str = "2026-07-06") -> dict:
    return {
        "platform": "reddit",
        "captured_at": f"{day}T12:00:00Z",
        "album_url": f"https://www.reddit.com/r/erome/comments/{tag}-{score}/",
        "album_id": f"{tag}-{score}",
        "views": score,
        "likes": score,
        "tags": [tag],
        "format_bucket": "video",
    }


def test_compute_trend_scores_fuses_platforms():
    erome = [_erome_row("milf", 10_000) for _ in range(3)]
    reddit = [_reddit_row("milf", 200), _reddit_row("other", 50)]
    ranked = mic.compute_trend_scores(erome, reddit)
    assert ranked[0]["tag"] == "milf"
    assert ranked[0]["cross_platform"] is True


def test_evaluate_weekly_cycle_incomplete_on_low_samples(monkeypatch, tmp_path):
    ledger, cycle_ledger = _patch_paths(monkeypatch, tmp_path)
    ebi.ingest_rows([_erome_row("milf", 1000)])
    result = mic.evaluate_weekly_cycle(force=True)
    assert result["complete"] is False
    assert "insufficient_samples" in " ".join(result["reasons"])
    assert cycle_ledger.is_file()


def test_evaluate_weekly_cycle_complete_when_stable(monkeypatch, tmp_path):
    ledger, cycle_ledger = _patch_paths(monkeypatch, tmp_path)
    rows = [_erome_row("milf", 10_000 + i) for i in range(4)]
    rows += [_reddit_row("milf", 300 + i) for i in range(3)]
    ebi.ingest_rows(rows)

    prior_week = {
        "week_id": "2026-W26",
        "top_tags": [{"tag": "milf", "trend_score": 0.8}],
        "leader_tag": "milf",
        "complete": True,
    }
    cycle_ledger.write_text(json.dumps(prior_week) + "\n", encoding="utf-8")

    fixed_now = datetime(2026, 7, 7, 9, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(mic, "week_id", lambda dt=None: "2026-W28")

    result = mic.evaluate_weekly_cycle(force=True)
    assert result["leader_tag"] == "milf"
    assert result["complete"] is True
    assert result["confidence"] >= 0.5


def test_cycle_signal_from_last_record(monkeypatch, tmp_path):
    _, cycle_ledger = _patch_paths(monkeypatch, tmp_path)
    record = {
        "week_id": "2026-W28",
        "complete": True,
        "confidence": 0.82,
        "leader_tag": "milf",
        "top_tags": [{"tag": "milf", "trend_score": 0.9}],
    }
    cycle_ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setattr(mic, "week_id", lambda dt=None: "2026-W28")

    sig = mic.cycle_signal_from_last_record()
    assert sig is not None
    assert sig["signal_type"] == "market_intel_weekly_cycle"
    assert sig["tag"] == "milf"


def test_skips_duplicate_week_without_force(monkeypatch, tmp_path):
    _, cycle_ledger = _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(mic, "week_id", lambda dt=None: "2026-W28")
    cycle_ledger.write_text(
        json.dumps({"week_id": "2026-W28", "complete": False, "reasons": ["x"]}) + "\n",
        encoding="utf-8",
    )
    result = mic.evaluate_weekly_cycle(force=False)
    assert result.get("skipped") is True
    assert result.get("reason") == "already_evaluated_this_week"
