"""Tests for Scrolller agent-route market-intel probe."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.services import erome_browse_intel as ebi
from app.services.market_intel_scrolller_probe import (
    discover_scrolller_subreddit_candidates,
    run_scrolller_probes,
    scrolller_subreddit_rows,
)


def _patch_intel_paths(monkeypatch, tmp_path):
    ledger = tmp_path / "browse-intel.jsonl"
    ts = tmp_path / "market-intel-timeseries.jsonl"
    monkeypatch.setattr(ebi, "ledger_path", lambda: ledger)
    monkeypatch.setattr(ebi, "timeseries_path", lambda: ts)
    monkeypatch.setattr(ebi, "browse_intel_enabled", lambda: True)
    return ledger, ts


def _sample_payload():
    return {
        "slug": "amateur_milfs",
        "title": "amateur_milfs",
        "tags": ["milf"],
        "itemCount": 60000,
        "subscribers": 896149,
        "contentRating": "explicit",
        "embedUrl": "https://scrolller.com/r/amateur_milfs",
        "items": [
            {
                "contentId": "/sample_post_abc123",
                "title": "Sample gallery",
                "tags": ["amateur"],
                "embedUrl": "https://scrolller.com/sample_post_abc123",
                "contentType": "gallery",
                "source": "/r/amateur_milfs/comments/abc123/sample/",
                "contentRating": "explicit",
            }
        ],
    }


def test_scrolller_subreddit_rows_maps_sub_and_items():
    rows = scrolller_subreddit_rows(_sample_payload())
    assert len(rows) == 2
    sub_row = rows[0]
    assert sub_row["platform"] == "scrolller"
    assert sub_row["format_bucket"] == "subreddit"
    assert sub_row["views"] == 896149
    assert "amateur_milfs" in sub_row["tags"]

    item_row = rows[1]
    assert item_row["platform"] == "scrolller"
    assert item_row["format_bucket"] == "gallery"
    assert item_row["entity_url"].startswith("https://scrolller.com/")
    assert item_row["context"]["attribution"] == "scrolller"
    assert "amateur_milfs" in item_row["tags"]


def test_run_scrolller_probes_ingests(monkeypatch, tmp_path):
    ledger, _ = _patch_intel_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("TBCC_SCROLLLER_PROBE_ENABLED", "1")
    monkeypatch.setenv("TBCC_SCROLLLER_PROBE_SUBREDDITS", "amateur_milfs")
    monkeypatch.setattr(
        "app.services.market_intel_scrolller_probe.scrolller_request_interval_sec",
        lambda: 0.0,
    )

    with patch(
        "app.services.market_intel_scrolller_probe.scrolller_subreddit_snapshot",
        return_value=_sample_payload(),
    ):
        result = run_scrolller_probes(limit_per_sub=5)

    assert result["ok"] is True
    assert result["ingest"]["appended"] == 2
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["platform"] == "scrolller"


def test_discover_scrolller_subreddit_candidates_sorts_by_subscribers(monkeypatch):
    monkeypatch.setenv("TBCC_SCROLLLER_PROBE_SEED_SUBREDDITS", "erome,nsfw")
    monkeypatch.setattr(
        "app.services.market_intel_scrolller_probe.scrolller_request_interval_sec",
        lambda: 0.0,
    )

    def fake_snapshot(sub, *, limit=20):
        data = {
            "erome": {"slug": "erome", "subscribers": 13000, "itemCount": 56, "contentRating": "explicit", "items": []},
            "nsfw": {"slug": "nsfw", "subscribers": 4000000, "itemCount": 40000, "contentRating": "explicit", "items": []},
        }
        return data.get(sub)

    with patch(
        "app.services.market_intel_scrolller_probe.scrolller_subreddit_snapshot",
        side_effect=fake_snapshot,
    ):
        out = discover_scrolller_subreddit_candidates(limit_per_sub=1, max_subs=2)

    assert len(out) == 2
    assert out[0]["name"] == "nsfw"
    assert out[0]["subscribers"] > out[1]["subscribers"]
