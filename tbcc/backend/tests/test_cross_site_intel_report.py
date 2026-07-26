"""Pure-helper tests for cross-site browse-intel revenue report."""

from __future__ import annotations

from pathlib import Path

from scripts.tbcc_cross_site_intel_report import (
    connections_block,
    coverage_block,
    lane_map_block,
)


def _row(
    *,
    platform: str,
    tags: list[str],
    views: int = 1000,
    uploader: str = "creator_a",
    format_bucket: str = "multi_video",
    captured_at: str = "2026-07-10T12:00:00Z",
    album_url: str = "https://example.com/a/1",
) -> dict:
    return {
        "platform": platform,
        "tags": tags,
        "views": views,
        "uploader": uploader,
        "format_bucket": format_bucket,
        "captured_at": captured_at,
        "album_url": album_url,
        "engagement_bps": 50,
    }


def test_connections_finds_cross_site_tags():
    rows = [
        _row(platform="erome", tags=["milf", "webcam"], album_url="https://erome.com/a/1"),
        _row(platform="thisvid", tags=["milf", "public"], album_url="https://thisvid.com/v/1"),
        _row(platform="motherless", tags=["solo"], album_url="https://motherless.com/g/1"),
    ]
    conn = connections_block(rows, top=10)
    tags = {x["tag"]: x for x in conn["cross_site_tags"]}
    assert "milf" in tags
    assert set(tags["milf"]["platforms"]) == {"erome", "thisvid"}
    assert "solo" not in tags


def test_lane_map_scores_overlapping_intel_tags():
    rows = [
        _row(platform="erome", tags=["busty", "milf"], views=50_000, album_url="https://erome.com/a/2"),
        _row(platform="thisvid", tags=["busty"], views=5_000, album_url="https://thisvid.com/v/2"),
    ]
    lanes = lane_map_block(rows, top=20)
    assert lanes["lanes"], "expected at least one AOF lane hit from LANE_TAG_MAP"
    by_key = {x["lane"]: x for x in lanes["lanes"]}
    assert "big_tits" in by_key or "milf" in by_key
    multi = lanes.get("multi_site_lanes") or []
    assert any(x["lane"] == "big_tits" and set(x["platforms"]) >= {"erome", "thisvid"} for x in multi)


def test_coverage_counts_per_platform():
    rows = [
        _row(platform="erome", tags=["a"], album_url="https://erome.com/a/3"),
        _row(platform="erome", tags=["b"], album_url="https://erome.com/a/4"),
        _row(platform="thisvid", tags=["c"], album_url="https://thisvid.com/v/3"),
    ]
    cov = coverage_block(rows, days=30, ledger=Path("/tmp/browse-intel.jsonl"))
    assert cov["total_rows"] == 3
    assert cov["platforms"]["erome"]["rows"] == 2
    assert cov["platforms"]["thisvid"]["rows"] == 1
    assert cov["platforms"]["motherless"]["rows"] == 0
