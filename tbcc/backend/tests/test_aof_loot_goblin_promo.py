"""Loot Goblin promo — teaser cadence, prompt-drop footer suppression markers."""

from __future__ import annotations

from app.services.aof_loot_goblin_promo import (
    GOBLIN_FREE_DEEP_LINK,
    PROMPT_DROP_MARKER,
    append_prompt_drop_variations,
    build_goblin_teaser_with_footer,
    build_loot_room_goblin_bulletin_html,
    build_prompt_drop_html,
    inject_goblin_teaser_variations,
    is_goblin_teaser_variation,
    is_prompt_drop_variation,
    strip_prompt_drop_footer,
)


def test_goblin_teaser_is_clearnet_no_lv_host() -> None:
    body = build_goblin_teaser_with_footer("📌 footer")
    assert GOBLIN_FREE_DEEP_LINK in body
    assert "linkvertise" not in body.lower()
    assert "link-target" not in body.lower()
    assert is_goblin_teaser_variation(body)


def test_inject_goblin_teaser_every_sixth_slot() -> None:
    bulletin = "📌 AOF LINKS HUB\nhub"
    promo = "channel promo"
    filler = [f"slot {i}" for i in range(10)]
    variations = [bulletin, promo, *filler]
    teaser = build_goblin_teaser_with_footer("📌 footer")
    merged = inject_goblin_teaser_variations(variations, [teaser], every_nth=6)
    teasers = [v for v in merged if is_goblin_teaser_variation(v)]
    assert len(teasers) >= 1
    assert merged[0] == bulletin


def test_prompt_drop_single_gate_link() -> None:
    body = build_prompt_drop_html(
        gate_url="https://link-target.net/1367336/abc",
        title="border v1",
        tier_label="promo",
    )
    assert PROMPT_DROP_MARKER in body
    assert body.count("href=") == 1
    assert is_prompt_drop_variation(body)


def test_strip_prompt_drop_footer_skips_addlist() -> None:
    drop = build_prompt_drop_html(
        gate_url="https://link-target.net/1367336/abc",
        title="test",
    )
    footer = "\n\n📌 <b>Join the full AOF stack</b>\naddlist"
    out = strip_prompt_drop_footer(drop, footer)
    assert "Join the full AOF stack" not in out
    assert PROMPT_DROP_MARKER in out


def test_loot_room_bulletin_mentions_no_lv_on_goblin() -> None:
    html = build_loot_room_goblin_bulletin_html()
    assert "Loot Goblin" in html
    assert "No Linkvertise on goblin" in html


def test_append_prompt_drop_variations_appends_provisioned_rows() -> None:
    from app.database.session import SessionLocal
    from app.models.prompt_gate import PROMPT_GATE_STATUS_PROVISIONED, PromptGate

    db = SessionLocal()
    try:
        base = ["a", "b"]
        count = (
            db.query(PromptGate)
            .filter(
                PromptGate.status == PROMPT_GATE_STATUS_PROVISIONED,
                PromptGate.superseded_by_id.is_(None),
                PromptGate.lv_url.isnot(None),
            )
            .count()
        )
        merged = append_prompt_drop_variations(db, base)
        if count == 0:
            assert merged == base
        else:
            assert len(merged) == len(base) + count
            assert any(is_prompt_drop_variation(v) for v in merged)
    finally:
        db.close()
