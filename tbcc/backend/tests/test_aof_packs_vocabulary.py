"""Tests for AOF PACKS vocabulary sanitizer."""

from app.services.aof_packs_vocabulary import pick_pack_parcel_synonym, sanitize_pack_copy
from app.services.aof_packs_post_copy import build_pack_drop_caption, display_pack_name
from app.models.loot import LootModifier


def test_sanitize_pack_copy_replaces_bento():
    out = sanitize_pack_copy("ELITE BENTO PACKS", seed="elite-bento")
    assert "bento" not in out.lower()
    assert "ELITE" in out
    assert pick_pack_parcel_synonym("elite-bento:bento") in out.lower()


def test_display_pack_name_strips_bento():
    assert "bento" not in display_pack_name("Elite Bento Pack — https://mega.nz/x").lower()


def test_build_pack_drop_caption_scrubs_bento_label():
    mod = LootModifier(
        kind="mega_pack",
        label="Elite Bento Packs",
        target_url="https://link-center.net/abc",
        source_note="mega_inventory|size_gb=24|gate_adm=https://speedy-links.com/s?x",
    )
    cap = build_pack_drop_caption(mod, "https://link-center.net/abc", "")
    assert "bento" not in cap.lower()
    assert "24 GB" in cap
