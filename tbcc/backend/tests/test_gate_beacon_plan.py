"""Gate beacon plan — slug/source_ref convention and attribution classing."""

import re

import pytest

from app.data.aof_manual_gate_links import AOF_MANUAL_LV_GATES
from app.data.gate_beacon_plan import (
    ATTRIBUTION_CLICK_ONLY,
    ATTRIBUTION_FULL,
    SKIP_KEYS,
    beacon_slug,
    beacon_source_ref,
    build_gate_beacon_plan,
    normalize_week_tag,
)
from app.services.click_beacon import _SLUG_RE
from app.services.traffic_attribution import payload_to_source_ref

_SRC_REF_RE = re.compile(r"^src_[a-z0-9_]{2,56}$")


def test_normalize_week_tag_rejects_junk():
    assert normalize_week_tag("WK31") == "wk31"
    for bad in ("", "wk-31", "w", "wk31!", "a" * 13):
        with pytest.raises(ValueError):
            normalize_week_tag(bad)


def test_slug_and_source_ref_shape():
    assert beacon_slug("ass", "wk31") == "wk31-lv-ass"
    assert beacon_source_ref("ass", "wk31") == "src_lv_ass_wk31"


def test_plan_covers_every_gate_key():
    plan = build_gate_beacon_plan("wk31")
    keys = {b.key for b in plan}
    assert keys == set(AOF_MANUAL_LV_GATES) - SKIP_KEYS


def test_every_slug_is_valid_for_click_beacon():
    for b in build_gate_beacon_plan("wk31"):
        assert _SLUG_RE.match(b.slug), b.slug


def test_every_source_ref_round_trips_through_attribution():
    """A beacon's source_ref must survive payload_to_source_ref unchanged."""
    for b in build_gate_beacon_plan("wk31"):
        assert _SRC_REF_RE.match(b.source_ref), b.source_ref
        assert payload_to_source_ref(b.source_ref) == b.source_ref


def test_bot_routes_carry_start_payload():
    plan = {b.key: b for b in build_gate_beacon_plan("wk31")}
    loot = plan["loot"]
    assert loot.attribution == ATTRIBUTION_FULL
    assert loot.destination_url.endswith("?start=src_lv_loot_wk31")
    assert plan["main_group"].is_full_attribution


def test_gates_without_a_resolvable_channel_stay_click_only():
    """No channel to relay to means no honest way to attach a start payload."""
    plan = {b.key: b for b in build_gate_beacon_plan("wk31")}
    for key in ("mainhub", "addlist"):
        assert plan[key].attribution == ATTRIBUTION_CLICK_ONLY
        assert "?start=" not in plan[key].destination_url


def test_slugs_unique_within_a_week():
    plan = build_gate_beacon_plan("wk31")
    slugs = [b.slug for b in plan]
    assert len(slugs) == len(set(slugs))


def test_week_tag_changes_every_slug():
    a = {b.slug for b in build_gate_beacon_plan("wk31")}
    b = {x.slug for x in build_gate_beacon_plan("wk32")}
    assert not (a & b)
