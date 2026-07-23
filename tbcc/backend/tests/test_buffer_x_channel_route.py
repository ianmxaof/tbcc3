"""Buffer X primary vs secondary routing (Loot vs VIP lanes)."""

from __future__ import annotations

from app.data.aof_network import AOF_VIP_IDENT
from app.services.buffer_x_channel_route import (
    buffer_mirror_x_only_for_telegram_identifier,
    buffer_x_channel_for_telegram_identifier,
    buffer_x_secondary_channel_id,
)


def test_vip_uses_secondary_x(monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_CHANNEL_ID_PRIMARY", "primary-x")
    monkeypatch.setenv("TBCC_BUFFER_CHANNEL_ID_X_SECONDARY", "powercore-x")
    assert buffer_x_secondary_channel_id() == "powercore-x"
    assert buffer_x_channel_for_telegram_identifier(AOF_VIP_IDENT) == "powercore-x"
    assert buffer_x_channel_for_telegram_identifier("-1003927742839") == "primary-x"
    assert buffer_mirror_x_only_for_telegram_identifier(AOF_VIP_IDENT) is True
    assert buffer_mirror_x_only_for_telegram_identifier("-1003927742839") is False


def test_vip_falls_back_to_primary_without_secondary(monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_CHANNEL_ID_PRIMARY", "primary-x")
    monkeypatch.delenv("TBCC_BUFFER_CHANNEL_ID_X_SECONDARY", raising=False)
    assert buffer_x_channel_for_telegram_identifier(AOF_VIP_IDENT) == "primary-x"
    assert buffer_mirror_x_only_for_telegram_identifier(AOF_VIP_IDENT) is False


def test_explicit_tg_map_overrides(monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_CHANNEL_ID_PRIMARY", "primary-x")
    monkeypatch.setenv("TBCC_BUFFER_CHANNEL_ID_X_SECONDARY", "powercore-x")
    monkeypatch.setenv("TBCC_BUFFER_X_BY_TG_CHANNEL", "-100111:custom-x")
    assert buffer_x_channel_for_telegram_identifier("-100111") == "custom-x"
    assert buffer_mirror_x_only_for_telegram_identifier("-100111") is True
