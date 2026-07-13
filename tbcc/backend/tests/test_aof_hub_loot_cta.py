"""Public hub CTA defaults to loot overseer after AOF Main ban."""

from __future__ import annotations

from app.services.aof_social_links import (
    aof_hub_invite_url,
    loot_paid_checkout_url,
    loot_public_cta_url,
)


def test_loot_public_cta_default(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_PUBLIC_CTA_URL", raising=False)
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    assert loot_public_cta_url() == "https://t.me/aof_lootgod_bot?start=loot_free"


def test_aof_hub_defaults_to_loot_not_banned_main(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_HUB_INVITE_URL", raising=False)
    monkeypatch.delenv("TBCC_LOOT_PUBLIC_CTA_URL", raising=False)
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    hub = aof_hub_invite_url()
    assert "loot_free" in hub
    assert "hMQzGsBFjF02MDkx" not in hub


def test_aof_hub_env_override(monkeypatch):
    monkeypatch.setenv("TBCC_AOF_HUB_INVITE_URL", "https://t.me/custom_hub")
    assert aof_hub_invite_url() == "https://t.me/custom_hub"


def test_loot_paid_checkout_url(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    assert loot_paid_checkout_url() == "https://t.me/aofsubscriptions_bot?start=loot"
