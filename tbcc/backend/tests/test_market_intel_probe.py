"""Tests for Reddit JSON market-intel probe."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.services import erome_browse_intel as ebi
from app.services.market_intel_probe import _reddit_post_rows, run_market_probes


def _patch_intel_paths(monkeypatch, tmp_path):
    ledger = tmp_path / "browse-intel.jsonl"
    ts = tmp_path / "market-intel-timeseries.jsonl"
    monkeypatch.setattr(ebi, "ledger_path", lambda: ledger)
    monkeypatch.setattr(ebi, "timeseries_path", lambda: ts)
    monkeypatch.setattr(ebi, "browse_intel_enabled", lambda: True)
    return ledger, ts


def test_reddit_post_rows_parses_hot_json():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Test post",
                        "score": 120,
                        "num_comments": 8,
                        "created_utc": 1_700_000_000.0,
                        "author": "tester",
                        "permalink": "/r/erome/comments/abc123/test/",
                        "link_flair_text": "milf, webcam",
                        "is_video": True,
                    }
                }
            ]
        }
    }
    with patch("app.services.market_intel_probe._fetch_json", return_value=payload):
        rows = _reddit_post_rows("erome", limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["platform"] == "reddit"
    assert row["album_id"] == "abc123"
    assert row["uploader"] == "tester"
    assert "milf" in row["tags"]
    assert row["format_bucket"] == "video"
    assert row["views_per_day_proxy"] is not None


def test_run_market_probes_ingests(monkeypatch, tmp_path):
    ledger, _ = _patch_intel_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("TBCC_MARKET_INTEL_PROBE_ENABLED", "1")
    monkeypatch.setenv("TBCC_MARKET_INTEL_PROBE_SUBREDDITS", "erome")

    fake = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "x1",
                        "title": "Hot",
                        "score": 50,
                        "num_comments": 2,
                        "created_utc": 1_700_000_000.0,
                        "author": "u1",
                        "permalink": "/r/erome/comments/x1/h/",
                        "link_flair_text": "",
                    }
                }
            ]
        }
    }

    with patch("app.services.market_intel_probe._fetch_json", return_value=fake):
        result = run_market_probes(limit_per_sub=5)

    assert result["ok"] is True
    assert result["ingest"]["appended"] == 1
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["platform"] == "reddit"
