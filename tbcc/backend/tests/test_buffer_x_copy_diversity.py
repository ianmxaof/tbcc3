"""
Phase 3 — Buffer X hook stem diversity. See
tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase3_report.md.

Loads the committed catalogs directly (not a live-generated sample) so this test catches
drift: if someone regenerates without the round-robin fix, or hand-edits a JSON file with
a bad body, this fails without needing to run the generator script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BACKEND_DIR / "app" / "data" / "buffer_x_copy"
FALLBACK_DIR = BACKEND_DIR.parent / "docs" / "samples" / "buffer_x_copy"

MIN_FIRST_SENTENCE_DIVERSITY = 60

CATALOG_NAMES = ("lootgod.json", "spicy.json", "paired_dual_cta.json", "network.json", "affiliate.json")


def _first_sentence(body: str) -> str:
    """Mirrors generate_buffer_x_copy_catalog.first_sentence() — everything up to and
    including the first '.' or ':' followed by a space."""
    m = re.match(r"^(.*?[.:])\s", body)
    return m.group(1) if m else body.split(" ", 1)[0]


def _load_templates(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["templates"]


def test_runtime_catalogs_exist():
    assert RUNTIME_DIR.is_dir()
    for name in CATALOG_NAMES:
        assert (RUNTIME_DIR / name).exists(), f"missing {name} in {RUNTIME_DIR}"


def test_each_category_meets_first_sentence_diversity_floor():
    for name in CATALOG_NAMES:
        templates = _load_templates(RUNTIME_DIR / name)
        bodies = [t["body"] for t in templates]
        diversity = len({_first_sentence(b) for b in bodies})
        assert diversity >= MIN_FIRST_SENTENCE_DIVERSITY, (
            f"{name}: only {diversity} unique first-sentence hooks "
            f"(target >= {MIN_FIRST_SENTENCE_DIVERSITY})"
        )


def test_each_category_has_no_duplicate_bodies():
    for name in CATALOG_NAMES:
        templates = _load_templates(RUNTIME_DIR / name)
        bodies = [t["body"] for t in templates]
        assert len(bodies) == len(set(bodies)), f"{name} has duplicate template bodies"


def test_runtime_and_fallback_catalogs_match():
    """seed_social_copy_templates.py prefers RUNTIME_DIR and falls back to FALLBACK_DIR —
    they must stay in sync or the seed result depends on which directory happens to exist,
    which is exactly the drift the Phase 3 generator rewrite closed (dual-write)."""
    if not FALLBACK_DIR.is_dir():
        return
    for name in CATALOG_NAMES:
        runtime = (RUNTIME_DIR / name).read_text(encoding="utf-8")
        fallback = (FALLBACK_DIR / name).read_text(encoding="utf-8")
        assert runtime == fallback, f"{name} differs between {RUNTIME_DIR} and {FALLBACK_DIR}"


def test_templates_have_required_fields():
    for name in CATALOG_NAMES:
        templates = _load_templates(RUNTIME_DIR / name)
        assert len(templates) >= 90  # generator targets 100, allow some slack
        for t in templates:
            assert (t.get("body") or "").strip()
            assert t.get("surface") == "x_buffer"
            assert t.get("category")
