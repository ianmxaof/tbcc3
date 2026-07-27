"""Phase 7 — prompt_gate placement + cannibalization guards."""

from __future__ import annotations

import pytest

from app.services.aof_loot_goblin_promo import (
    GOBLIN_FREE_DEEP_LINK,
    build_goblin_teaser_with_footer,
    build_prompt_drop_html,
)
from app.services.buffer_native_queue_refill import _caption_allowed_for_x
from app.services.prompt_gate_placement import (
    VIOLATION_CHANNEL_GATE_AND_PROMPT,
    VIOLATION_DUAL_LV,
    VIOLATION_GATE_PROTECTED_URL,
    VIOLATION_LV_ON_X,
    assert_telegram_placement_ok,
    is_protected_clearnet_url,
    linkvertise_urls_in_text,
    telegram_placement_violations,
    validate_prompt_drop_html,
    x_placement_violations,
)
from app.services.prompt_gate_registry import apply_provision_success, upsert_catalog_row
from app.services.prompt_gate_lookup import active_prompt_gate_row, hash_prompt_body


CHANNEL_GATE = "https://link-center.net/1367336/channelAddlist"
PROMPT_GATE = "https://link-target.net/1367336/promptSku"


def test_linkvertise_dual_destination_is_violation() -> None:
    body = f"gate one {CHANNEL_GATE} and gate two {PROMPT_GATE}"
    assert VIOLATION_DUAL_LV in telegram_placement_violations(body)


def test_prompt_drop_single_lv_passes() -> None:
    body = build_prompt_drop_html(gate_url=PROMPT_GATE, title="border v1", tier_label="promo")
    validate_prompt_drop_html(body)
    assert telegram_placement_violations(body, channel_gate_urls=()) == []


def test_prompt_drop_plus_channel_gate_footer_is_cannibalized() -> None:
    drop = build_prompt_drop_html(gate_url=PROMPT_GATE, title="border v1")
    footer = f"\n\n📌 <b>Join the full AOF stack</b>\n{CHANNEL_GATE}"
    violations = telegram_placement_violations(drop + footer, channel_gate_urls={CHANNEL_GATE})
    assert VIOLATION_CHANNEL_GATE_AND_PROMPT in violations


def test_goblin_claim_url_is_protected_clearnet() -> None:
    assert is_protected_clearnet_url(GOBLIN_FREE_DEEP_LINK)
    assert is_protected_clearnet_url("https://t.me/aofsubscriptions_bot?start=loot")
    assert not is_protected_clearnet_url("https://telegram.me/aofmainhub")


def test_gated_checkout_anchor_is_violation() -> None:
    wrapped = "https://link-center.net/1367336/wrappedCheckout"
    bad = f'<a href="{wrapped}">https://t.me/aofsubscriptions_bot?start=loot_free</a>'
    assert VIOLATION_GATE_PROTECTED_URL in telegram_placement_violations(bad)


def test_goblin_teaser_has_no_lv_host() -> None:
    body = build_goblin_teaser_with_footer("📌 footer")
    assert linkvertise_urls_in_text(body) == []
    assert telegram_placement_violations(body) == []


def test_x_placement_blocks_lv_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    assert VIOLATION_LV_ON_X in x_placement_violations(f"unlock {CHANNEL_GATE}")
    assert x_placement_violations("hub https://telegram.me/aof_lootgod_bot") == []


def test_x_placement_allows_lv_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "1")
    assert x_placement_violations(f"unlock {CHANNEL_GATE}") == []


def test_caption_allowed_for_x_rejects_lv_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    assert not _caption_allowed_for_x(f"gate {CHANNEL_GATE} · hub https://telegram.me/aofmainhub")
    assert _caption_allowed_for_x("hub https://telegram.me/aofmainhub · affiliate https://nodress.io")


def test_wrap_url_for_x_passthrough_when_lv_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.buffer_x_outbound_guard import wrap_url_for_x_outbound

    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    url = "https://telegram.me/aofmainhub"
    assert wrap_url_for_x_outbound(url, gate_key="mainhub") == url


def test_body_hash_supersede_keeps_single_active_slug() -> None:
    from app.database.session import SessionLocal, engine
    from app.models.base import Base
    from app.models.prompt_gate import PROMPT_GATE_STATUS_PENDING, PROMPT_GATE_STATUS_PROVISIONED, PromptGate

    PromptGate.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine, tables=[PromptGate.__table__])
    db = SessionLocal()
    try:
        body_v1 = "SFW border prompt v1"
        body_v2 = "SFW border prompt v2"
        pending_v1, action_v1 = upsert_catalog_row(db, "border_v1", body_v1)
        assert action_v1 == "queued_new"
        assert pending_v1.status == PROMPT_GATE_STATUS_PENDING
        apply_provision_success(db, pending_v1, PROMPT_GATE, probe={"flags": ["LV_SHELL"]})

        new_row, action = upsert_catalog_row(db, "border_v1", body_v2)
        assert action == "queued_drift"
        apply_provision_success(
            db,
            new_row,
            "https://link-target.net/1367336/promptSkuV2",
            probe={"flags": ["LV_SHELL"]},
        )
        db.commit()

        active = active_prompt_gate_row(db, "border_v1")
        assert active.lv_url.endswith("/promptSkuV2")
        assert active.status == PROMPT_GATE_STATUS_PROVISIONED
        assert active.body_hash == hash_prompt_body(body_v2)
    finally:
        db.close()


def test_assert_telegram_placement_raises_on_dual_lv() -> None:
    with pytest.raises(ValueError, match="dual_lv_destination"):
        assert_telegram_placement_ok(f"{CHANNEL_GATE} {PROMPT_GATE}")
