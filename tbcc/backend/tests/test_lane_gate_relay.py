"""Lane gate relay — payload parsing and the resulting full-attribution plan."""

from app.data.gate_beacon_plan import (
    ATTRIBUTION_CLICK_ONLY,
    ATTRIBUTION_FULL,
    build_gate_beacon_plan,
)
from app.services.lane_gate_relay import (
    is_relayable_lane,
    lane_display_name,
    lane_invite_url,
    parse_lane_gate_payload,
)
from app.services.traffic_attribution import payload_to_source_ref


def test_parse_single_word_lane():
    assert parse_lane_gate_payload("src_lv_ass_wk31") == ("ass", "wk31")


def test_parse_multi_word_lane():
    """Lane keys contain underscores; only the last segment is the week."""
    assert parse_lane_gate_payload("src_lv_big_tits_wk31") == ("big_tits", "wk31")


def test_parse_rejects_unknown_lane():
    assert parse_lane_gate_payload("src_lv_notalane_wk31") is None


def test_parse_rejects_malformed():
    for bad in ("", "src_lv_", "src_lv_ass", "loot_free", "src_bait_vip", "SRC_LV_ASS_WK31!"):
        assert parse_lane_gate_payload(bad) is None


def test_parse_is_case_insensitive():
    assert parse_lane_gate_payload("SRC_LV_ASS_WK31") == ("ass", "wk31")


def test_relayable_lane_has_invite():
    assert is_relayable_lane("ass") is True
    assert lane_invite_url("ass").startswith("http")
    assert is_relayable_lane("notalane") is False
    assert lane_invite_url("notalane") is None


def test_lane_display_name_falls_back():
    assert lane_display_name("notalane") == "NOTALANE"


def test_lanes_now_route_through_bot_for_full_attribution():
    plan = {b.key: b for b in build_gate_beacon_plan("wk31")}
    lane = plan["ass"]
    assert lane.attribution == ATTRIBUTION_FULL
    assert lane.destination_url == "https://telegram.me/aof_lootgod_bot?start=src_lv_ass_wk31"
    # The relayed payload must round-trip back to the same source_ref.
    assert payload_to_source_ref(lane.source_ref) == lane.source_ref
    # And the bot must be able to turn it back into a lane.
    assert parse_lane_gate_payload(lane.source_ref) == ("ass", "wk31")


def test_every_full_attribution_lane_payload_resolves():
    for beacon in build_gate_beacon_plan("wk31"):
        if beacon.attribution != ATTRIBUTION_FULL:
            continue
        if beacon.key in ("loot", "main_group", "lootgod"):
            continue
        assert parse_lane_gate_payload(beacon.source_ref) is not None, beacon.key


def test_keys_without_a_channel_stay_click_only():
    plan = {b.key: b for b in build_gate_beacon_plan("wk31")}
    for key in ("mainhub", "addlist"):
        assert plan[key].attribution == ATTRIBUTION_CLICK_ONLY
        assert "?start=" not in plan[key].destination_url
