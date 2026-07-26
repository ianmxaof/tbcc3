"""Listening relay destination resolution."""

from unittest.mock import MagicMock

from app.data.aof_network import AOF_VIP_IDENT, MAIN_GROUP_IDENT
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_target import (
    pick_random_aof_network_channel_id,
    relay_has_send_target,
    relay_random_network_enabled,
    resolve_listening_relay_send_target,
)


def test_random_network_enabled_without_channel_id():
    row = ListeningRelaySettings(id=1, relay_random_network_channel=True, channel_id=None)
    assert relay_has_send_target(row) is True
    assert relay_random_network_enabled(row) is True


def test_resolve_random_picks_from_network_ids(monkeypatch):
    row = ListeningRelaySettings(id=1, relay_random_network_channel=True)
    db = MagicMock()

    monkeypatch.setattr(
        "app.services.listening_relay_target.pick_random_aof_network_channel_id",
        lambda _db: 42,
    )
    ch_id, thread_id = resolve_listening_relay_send_target(db, row)
    assert ch_id == 42
    assert thread_id is None


def test_resolve_fixed_channel_and_thread():
    row = ListeningRelaySettings(
        id=1,
        relay_random_network_channel=False,
        channel_id=9,
        message_thread_id=17,
    )
    db = MagicMock()
    ch_id, thread_id = resolve_listening_relay_send_target(db, row)
    assert ch_id == 9
    assert thread_id == 17


def test_loot_and_vip_idents_are_stable():
    assert MAIN_GROUP_IDENT.endswith("3927742839")
    assert AOF_VIP_IDENT.endswith("3982098745")
