"""
Phase 1 — structural fix for the "~440-520 content_variations, ~13-25 unique hooks"
padding bug in aof_growth_hub. See tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase1_report.md.

Phase 2 — PACKS + lane flavor bank expansion so each network scheduler rotates >=50
unique hooks. See tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase2_report.md.
"""

from __future__ import annotations

import json

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.aof_flavor_hooks import (
    gate_flavor_hooks,
    lane_flavor_hooks,
    vip_flavor_hooks,
)
from app.services.aof_growth_hub import (
    FOOTER_MARKER,
    _append_gate_flavor_variations,
    _append_gumroad_vip_variations,
    _append_lane_flavor_variations,
    _append_vip_flavor_variations,
    _dedupe_by_flavor_hook,
    _gumroad_vip_promo_variations,
    _merge_variations,
    _refresh_variation_footer,
    _sanitize_variations,
    _select_promo_footer,
    build_addlist_footer,
    build_telegram_footer_variants,
    unique_flavor_hook,
)


FOOTER = build_addlist_footer({})
LANE_KEYS = [ch.key for ch in AOF_NETWORK_CHANNELS if ch.key != "packs"]


def test_unique_flavor_hook_splits_before_footer_marker():
    caption = "💥 <b>NEW DELIVERY</b> 💥\nSome pack body." + FOOTER
    hook = unique_flavor_hook(caption)
    assert FOOTER_MARKER not in hook
    assert hook.startswith("💥 <b>NEW DELIVERY</b>")


def test_unique_flavor_hook_returns_whole_body_when_no_footer():
    caption = "🔥 standalone body with no footer at all"
    assert unique_flavor_hook(caption) == caption


def test_unique_flavor_hook_ignores_trailing_sponsor_or_url_differences():
    """Two captions with the same opener but different footer/url tails must hash to the
    same hook — that's exactly the padding pattern this helper exists to catch."""
    a = "⭐ <b>AOF VIP</b> — ad-free lane." + FOOTER
    b = "⭐ <b>AOF VIP</b> — ad-free lane." + FOOTER + "\n\nhttps://sponsor.example/x"
    assert unique_flavor_hook(a) == unique_flavor_hook(b)


def test_dedupe_by_flavor_hook_collapses_padded_list():
    """Regression test for the real-world bug: one hook x N affiliate footers used to
    produce N near-identical variations. N=8 here to make the collapse unmistakable."""
    padded = [f"🔒 <b>Skip the gates</b> — lane copy.{FOOTER}\n\nhttps://sponsor{i}.example" for i in range(8)]
    out = _dedupe_by_flavor_hook(padded)
    assert len(out) == 1
    assert out[0] == padded[0]


def test_dedupe_by_flavor_hook_preserves_order_and_keeps_first_occurrence():
    variations = [
        "AOF LINKS HUB bulletin body (no footer marker)",
        "🔓 <b>Skip the gates</b>" + FOOTER,
        "⭐ <b>AOF VIP</b>" + FOOTER,
        "🔓 <b>Skip the gates</b>" + FOOTER + "\n\nhttps://dup.example",  # duplicate hook
    ]
    out = _dedupe_by_flavor_hook(variations)
    assert out == variations[:3]
    assert out[0].startswith("AOF LINKS HUB")  # bulletin slot 0 survives


def test_dedupe_by_flavor_hook_is_idempotent():
    variations = [
        "🔓 <b>Skip the gates</b>" + FOOTER,
        "⭐ <b>AOF VIP</b>" + FOOTER,
    ]
    once = _dedupe_by_flavor_hook(variations)
    twice = _dedupe_by_flavor_hook(once)
    assert once == twice


def test_select_promo_footer_returns_only_footer_when_no_sponsors():
    assert _select_promo_footer([FOOTER], seed="ai") == FOOTER
    assert _select_promo_footer([], seed="ai") == ""


def test_select_promo_footer_picks_are_always_one_valid_variant():
    footer_variants = [FOOTER, FOOTER + "SPONSOR1", FOOTER + "SPONSOR2"]
    for seed in ("ai", "goon", "bop", "milf", "ass", "taboo", "voyeur", "abg", "main", "big_tits"):
        picked = _select_promo_footer(footer_variants, seed=seed)
        assert picked in footer_variants


def test_select_promo_footer_can_land_on_base_footer():
    """Base (sponsor-free) footer must stay reachable — affiliate exposure should shift
    *which* lane shows a sponsor, not turn into "sponsor on every lane's promo slot"."""
    footer_variants = [FOOTER, FOOTER + "SPONSOR1", FOOTER + "SPONSOR2"]
    seeds = ("ai", "goon", "bop", "milf", "ass", "taboo", "voyeur", "abg", "main", "big_tits", "blowjob", "packs")
    picks = {_select_promo_footer(footer_variants, seed=s) for s in seeds}
    assert FOOTER in picks


def test_select_promo_footer_is_deterministic():
    footer_variants = [FOOTER, FOOTER + "SPONSOR1", FOOTER + "SPONSOR2"]
    first = _select_promo_footer(footer_variants, seed="goon")
    second = _select_promo_footer(footer_variants, seed="goon")
    assert first == second


def test_select_promo_footer_spreads_sponsors_across_lanes():
    """Not every lane should land on the same sponsor — that's the whole point of
    rotating the footer instead of always using footer_variants[0]."""
    footer_variants = [FOOTER, FOOTER + "SPONSOR1", FOOTER + "SPONSOR2", FOOTER + "SPONSOR3"]
    seeds = ["ai", "goon", "bop", "milf", "ass", "taboo", "voyeur", "abg", "main", "big_tits", "blowjob", "packs"]
    picks = {_select_promo_footer(footer_variants, seed=s) for s in seeds}
    assert len(picks) > 1


def test_gumroad_vip_variations_use_all_minimal_bodies_not_just_first():
    """Phase 1 requirement: vip_promo_minimal_bodies() usage expands from [:1] to all
    bodies, so the VIP rotation slot isn't stuck repeating one line."""
    out = _gumroad_vip_promo_variations(FOOTER)
    # 2 inline bodies + all 3 vip_promo_minimal_bodies() == 5 distinct variations
    assert len(out) == 5
    hooks = {unique_flavor_hook(v) for v in out}
    assert len(hooks) == 5


def test_gumroad_vip_variations_stay_under_telegram_caption_limit():
    out = _gumroad_vip_promo_variations(FOOTER)
    for v in out:
        assert len(v) < 1024


def test_selected_sponsor_footer_survives_sanitize_round_trip(db):
    """_select_promo_footer only matters in production if the sponsor line it picks
    survives _sanitize_variations -> _refresh_variation_footer, which re-extracts and
    re-injects the sponsor line into a clean footer. Prove the round trip for real
    instead of assuming the extraction heuristic (💰 / href= line) matches
    build_sponsor_link_html's actual output."""
    row = PromoAffiliateLink(
        label="Test Sponsor",
        url="https://sponsor.example/aff",
        placements_json=json.dumps(["telegram_footer"]),
        network_keys_json=json.dumps([]),
        active=True,
    )
    db.add(row)
    db.commit()

    lv = {"addlist": "https://t.me/addlist/x", "mainhub": "https://telegram.me/aofmainhub"}
    footer_variants = build_telegram_footer_variants(db, lv, network_key="ai")
    assert len(footer_variants) > 1  # sponsor candidate present in this fixture

    picked = _select_promo_footer(footer_variants, seed="ai")
    assert picked != footer_variants[0]  # picked a sponsor-carrying footer, not the base

    caption = "🧠 <b>AOF AI</b> — test lane promo." + picked
    assert "sponsor.example" in caption  # sanity: sponsor really is in the input

    sanitized = _refresh_variation_footer(caption, footer_variants[0])
    assert "sponsor.example" in sanitized  # sponsor line must survive sanitize


# --- Phase 2: lane flavor bank ------------------------------------------------------


def test_lane_flavor_hooks_meet_minimum_per_lane():
    for key in LANE_KEYS:
        hooks = lane_flavor_hooks(key)
        assert len(hooks) >= 50, f"lane {key} has only {len(hooks)} flavor hooks"
        assert len(hooks) == len(set(hooks)), f"lane {key} has duplicate hooks"


def test_lane_flavor_hooks_are_lane_colored_not_identical_across_lanes():
    """The shared-bank design must still produce genuinely distinct text per lane —
    otherwise 'lane-colored openers' is just a label, not real diversity."""
    ai_hooks = set(lane_flavor_hooks("ai"))
    goon_hooks = set(lane_flavor_hooks("goon"))
    assert ai_hooks.isdisjoint(goon_hooks)


def test_lane_flavor_hooks_include_gold_planet_express_line():
    hooks = lane_flavor_hooks("ai")
    assert any("PLANET EXPRESS" in h and "NEW DELIVERY" in h for h in hooks)


def test_lane_flavor_hooks_never_touch_footer_or_bot_usernames():
    """These are pure hooks — no footer marker, no invented bot usernames. Callers are
    responsible for appending a footer separately."""
    for h in lane_flavor_hooks("ai"):
        assert FOOTER_MARKER not in h
    allowed_bots = ("@aofsubscriptions_bot", "@aof_lootgod_bot", "@aof_secretary_bot")
    for h in vip_flavor_hooks():
        if "@" in h:
            assert any(b in h for b in allowed_bots)


def test_vip_flavor_hooks_meet_minimum_and_all_used():
    hooks = vip_flavor_hooks()
    assert len(hooks) >= 15
    assert len(hooks) == len(set(hooks))
    appended = _append_vip_flavor_variations([], FOOTER)
    assert len(appended) == len(hooks)  # every body actually lands in rotation, not [:1]


def test_gate_flavor_hooks_meet_minimum_and_all_used():
    hooks = gate_flavor_hooks()
    assert len(hooks) >= 15
    assert len(hooks) == len(set(hooks))
    appended = _append_gate_flavor_variations([], FOOTER)
    assert len(appended) == len(hooks)


def test_append_lane_flavor_variations_pairs_one_footer_per_hook_not_every_footer():
    """Regression test for reintroducing the Phase 1 padding bug at lane-bank scale:
    N hooks x M sponsor footers must still yield N variations, not N*M."""
    footer_variants = [FOOTER] + [FOOTER + f"SPONSOR{i}" for i in range(6)]
    out = _append_lane_flavor_variations([], "ai", footer_variants)
    assert len(out) == len(lane_flavor_hooks("ai"))
    hooks = {unique_flavor_hook(v) for v in out}
    assert len(hooks) == len(out)  # every entry has a distinct hook


def _build_full_lane_pipeline(network_key: str, footer_variants: list[str]) -> list[str]:
    """Mirrors sync_network_schedulers's per-lane merge sequence (minus DB-only steps
    like goblin teaser / prompt-drop injection) so the end-to-end unique-hook count can
    be asserted without standing up a full Channel/ContentPool/ScheduledTextPost fixture."""
    from app.data.aof_network import network_channel_by_key

    net_ch = network_channel_by_key(network_key)
    base_footer = footer_variants[0]
    promo_footer = _select_promo_footer(footer_variants, seed=network_key)
    promo = net_ch.promo_html + promo_footer
    merged = _merge_variations("AOF LINKS HUB bulletin stub", promo, [])
    merged = _append_gate_flavor_variations(merged, base_footer)
    merged = _append_gumroad_vip_variations(merged, base_footer)
    merged = _append_vip_flavor_variations(merged, base_footer)
    merged = _append_lane_flavor_variations(merged, network_key, footer_variants)
    merged = _sanitize_variations(merged, clean_footer=base_footer, skip_bulletin=True)
    return _dedupe_by_flavor_hook(merged)


def test_full_lane_pipeline_reaches_fifty_unique_hooks_per_lane():
    for key in LANE_KEYS:
        merged = _build_full_lane_pipeline(key, [FOOTER])
        unique_hooks = {unique_flavor_hook(v) for v in merged}
        assert len(unique_hooks) >= 50, f"lane {key} only reached {len(unique_hooks)} unique hooks"
        assert len(merged) == len(unique_hooks)  # zero duplicate-hook padding


def test_full_lane_pipeline_stable_variation_count_with_many_sponsor_candidates():
    """The exact scenario Phase 1 fixed, re-verified at Phase 2 scale: adding more
    affiliate footer candidates must not inflate the variation count."""
    footer_variants = [FOOTER] + [FOOTER + f"SPONSOR{i}" for i in range(6)]
    merged_one_sponsor = _build_full_lane_pipeline("ai", [FOOTER, FOOTER + "SPONSOR0"])
    merged_many_sponsors = _build_full_lane_pipeline("ai", footer_variants)
    assert len(merged_one_sponsor) == len(merged_many_sponsors)


def test_full_lane_pipeline_collapses_real_padded_existing_rows():
    """Simulates the actual island scenario: an old scheduler row with one hook cloned
    across 40 fake affiliate footers already sitting in content_variations. Confirms the
    resync path (existing + fresh additions, then dedupe) collapses it to one slot."""
    from app.data.aof_network import network_channel_by_key
    from app.services.aof_growth_hub import _strip_regenerated_promo_variations

    net_ch = network_channel_by_key("ai")
    padded_existing = [
        f"Skip the gates old hook.{FOOTER}\n\nhttps://sponsor{i}.example" for i in range(40)
    ]
    existing = _strip_regenerated_promo_variations(padded_existing, net_ch.promo_html)

    footer_variants = [FOOTER]
    promo_footer = _select_promo_footer(footer_variants, seed="ai")
    promo = net_ch.promo_html + promo_footer
    merged = _merge_variations("AOF LINKS HUB bulletin stub", promo, existing)
    merged = _append_gate_flavor_variations(merged, FOOTER)
    merged = _append_gumroad_vip_variations(merged, FOOTER)
    merged = _append_vip_flavor_variations(merged, FOOTER)
    merged = _append_lane_flavor_variations(merged, "ai", footer_variants)
    merged = _sanitize_variations(merged, clean_footer=FOOTER, skip_bulletin=True)
    before = len(merged)
    merged = _dedupe_by_flavor_hook(merged)

    assert before > len(merged)  # the 40 padded copies did exist before dedupe
    assert len(merged) == len({unique_flavor_hook(v) for v in merged})
    assert len(merged) >= 50
