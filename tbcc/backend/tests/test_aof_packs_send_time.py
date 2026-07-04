"""Tests for AOF PACKS send-time picker and caption templates."""

from unittest.mock import MagicMock

from app.models.loot import LootModifier
from app.services.aof_packs_caption_templates import (
    PACK_BODY_PLACEHOLDER,
    list_pack_strategy_ids,
    pack_caption_template_variations,
    pack_strategy_for_index,
)
from app.services.aof_packs_post_copy import format_pack_contents_block, merge_pack_source_note, parse_pack_source_note
from app.services.aof_packs_send_time import _inject_pack_body, pick_pack_modifier_for_send


def test_pack_caption_templates_reach_fifty():
    templates = pack_caption_template_variations()
    assert len(templates) == 50
    assert all(PACK_BODY_PLACEHOLDER in t for t in templates)


def test_pack_strategies_cycle_distinct_lanes():
    ids = list_pack_strategy_ids()
    assert "extinction" in ids
    assert "scarcity" in ids
    assert "early_access" in ids
    assert "addlist_punch" in ids
    assert len(ids) >= 10
    s0 = pack_strategy_for_index(0)
    s1 = pack_strategy_for_index(1)
    assert s0["id"] != s1["id"]


def test_pack_template_leaves_body_placeholder_for_gates():
    """Strategy intro only — gates/footer injected via build_pack_drop_caption."""
    templates = pack_caption_template_variations()
    assert all("Linkvertise" not in t for t in templates)
    assert all("addlist" not in t.lower() for t in templates)


def test_inject_pack_body_placeholder():
    body = "📦 <b>Test Pack</b>"
    out = _inject_pack_body(f"Header\n\n{PACK_BODY_PLACEHOLDER}", body)
    assert "Header" in out
    assert "Test Pack" in out
    assert PACK_BODY_PLACEHOLDER not in out


def test_format_pack_contents_block_from_token():
    note = merge_pack_source_note("master_archive", contents=["YukiiKitty", "Cyberpetgirl"])
    meta = parse_pack_source_note(note)
    mod = LootModifier(kind="mega_pack", label="YukiiKitty")
    block = format_pack_contents_block(meta, mod)
    assert "NEW PACK CONTENTS" in block
    assert "YukiiKitty" in block
    assert "Cyberpetgirl" in block


def test_pick_pack_modifier_prefers_unseen(monkeypatch):
    mods = [
        LootModifier(id=1, kind="mega_pack", active=True, target_url="https://link-center.net/a", source_note="master_archive"),
        LootModifier(id=2, kind="mega_pack", active=True, target_url="https://link-center.net/b", source_note="master_archive"),
    ]
    monkeypatch.setattr(
        "app.services.aof_packs_send_time.list_active_pack_pool_modifiers",
        lambda db: mods,
    )
    monkeypatch.setattr(
        "app.services.aof_packs_send_time.recently_dropped_pack_modifier_ids",
        lambda db, **kw: {1},
    )
    db = MagicMock()
    picked = pick_pack_modifier_for_send(db, scheduled_post_id=99)
    assert picked is not None
    assert picked.id == 2
