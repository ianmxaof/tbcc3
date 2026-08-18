"""Tests for scripts/export_aof_lane_clip_catalog.py — small AOF-lane CLIP catalog helper."""

from __future__ import annotations

import json

from app.data.clip_slug_lane_map import SPLIT_LANE_KEYS
from scripts.export_aof_lane_clip_catalog import build_aof_lane_catalog, main


def test_build_aof_lane_catalog_covers_every_split_lane():
    catalog = build_aof_lane_catalog()
    groups = {row["group"] for row in catalog["categories"]}
    assert groups == set(SPLIT_LANE_KEYS)


def test_build_aof_lane_catalog_respects_max_per_lane():
    catalog = build_aof_lane_catalog(max_slugs_per_lane=1)
    counts: dict[str, int] = {}
    for row in catalog["categories"]:
        counts[row["group"]] = counts.get(row["group"], 0) + 1
    assert all(n <= 1 for n in counts.values())
    assert catalog["count"] == len(catalog["categories"])


def test_build_aof_lane_catalog_shape_matches_production_catalog_format():
    catalog = build_aof_lane_catalog()
    assert set(catalog.keys()) == {"categories", "count", "source"}
    for row in catalog["categories"]:
        assert set(row.keys()) == {"slug", "name", "prompts", "group"}
        assert isinstance(row["prompts"], list) and row["prompts"]


def test_main_refuses_to_overwrite_production_catalog(tmp_path, capsys):
    target = tmp_path / "clip-categories.json"
    rc = main(["--out", str(target)])
    assert rc == 1
    assert not target.exists()


def test_main_writes_small_catalog_file(tmp_path):
    target = tmp_path / "clip-categories-aof-lanes.example.json"
    rc = main(["--out", str(target)])
    assert rc == 0
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["count"] == len(data["categories"])
    assert data["count"] > 0


def test_main_prints_to_stdout_when_no_out(capsys):
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["count"] > 0
