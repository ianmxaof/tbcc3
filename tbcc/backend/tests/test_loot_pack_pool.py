"""AOF packs promo pool + scheduler wiring."""

from app.services.loot_pack_pool import build_packs_album_variants


def test_build_packs_album_variants_cycles_full_pool():
    promo = [10, 11, 12, 13, 14]
    variants, pool_only = build_packs_album_variants(promo, 8, link_slot_offset=0)
    assert pool_only is False
    assert len(variants) == 8
    assert [v["media_ids"][0] for v in variants] == [10, 11, 12, 13, 14, 10, 11, 12]


def test_build_packs_album_variants_offset_stagger():
    promo = [1, 2, 3]
    variants, pool_only = build_packs_album_variants(promo, 4, link_slot_offset=2)
    assert pool_only is False
    assert [v["media_ids"][0] for v in variants] == [3, 1, 2, 3]


def test_build_packs_album_variants_empty_pool_falls_back():
    variants, pool_only = build_packs_album_variants([], 8)
    assert variants == []
    assert pool_only is True
