"""AOF PACKS post copy + preview pairing."""

from app.models.loot import LootModifier
from app.services.aof_packs_post_copy import (
    build_pack_drop_caption,
    display_pack_name,
    format_pack_size_line,
    merge_pack_source_note,
    parse_pack_source_note,
    pack_meta_from_modifier,
)


def test_display_pack_name_strips_url():
    assert display_pack_name("Irisadamsone — https://gofile.io/d/abc") == "Irisadamsone"
    assert display_pack_name("AOF pack — https://epicload.com/x") == "AOF Pack"


def test_parse_pack_source_note_roundtrip():
    note = merge_pack_source_note(
        "mega_inventory|dest=https://x",
        size_gb=17.5,
        preview_ids=[10, 11, 12],
        theme="Milf vault",
    )
    meta = parse_pack_source_note(note)
    assert meta.size_gb == 17.5
    assert meta.preview_media_ids == (10, 11, 12)
    assert meta.theme == "Milf vault"


def test_build_pack_drop_caption_includes_name_and_size():
    mod = LootModifier(
        kind="mega_pack",
        label="Mihanika",
        target_url="https://link-center.net/abc",
        source_note="mega_inventory|size_gb=60|gate_adm=https://speedy-links.com/s?x",
    )
    cap = build_pack_drop_caption(mod, "https://link-center.net/abc", "")
    assert "Mihanika" in cap
    assert "60 GB" in cap
    assert "Linkvertise" in cap
    assert "AdMaven" in cap


def test_parse_pack_gate_tokens():
    note = merge_pack_source_note(
        "mega_pipeline",
        gate_lv_url="https://link-target.net/1/Slug",
        gate_adm_url="https://speedy-links.com/s?abc",
        destination_url="https://mega.nz/folder/x",
    )
    meta = parse_pack_source_note(note)
    assert meta.gate_lv_url == "https://link-target.net/1/Slug"
    assert meta.gate_adm_url == "https://speedy-links.com/s?abc"
    assert meta.destination_url == "https://mega.nz/folder/x"


def test_format_pack_size_unknown():
    assert "see folder" in format_pack_size_line(None)
