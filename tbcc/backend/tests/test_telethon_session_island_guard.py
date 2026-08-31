"""
Local-vs-island Telethon session guard (2026-08-31 incident).

A local process (backend/Celery/local_lane_hub_worker) and the revenue island both
held a live MTProto connection on the same auth key at once. Telegram forced the
island's connection out with AuthKeyDuplicatedError, breaking live scheduled posting
until the operator manually re-synced sessions and recreated the island containers.

``assert_safe_to_open_telethon_session()`` must be a no-op on the island itself
(TBCC_REVENUE_ISLAND_ACTIVE=1, set unconditionally in
docker-compose.revenue-island.yml) and must refuse everywhere else unless the
operator explicitly opts in.
"""

from __future__ import annotations

import pytest


def test_refuses_by_default_off_island(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.delenv("TBCC_REVENUE_ISLAND_ACTIVE", raising=False)
    monkeypatch.delenv("TBCC_LOCAL_TELETHON_ALLOWED", raising=False)

    with pytest.raises(RuntimeError, match="Refusing to open the local Telethon"):
        tsl.assert_safe_to_open_telethon_session("admin")


def test_allows_on_the_island(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    monkeypatch.delenv("TBCC_LOCAL_TELETHON_ALLOWED", raising=False)

    tsl.assert_safe_to_open_telethon_session("admin")  # no raise
    tsl.assert_safe_to_open_telethon_session("import")  # no raise


def test_allows_with_explicit_local_override(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.delenv("TBCC_REVENUE_ISLAND_ACTIVE", raising=False)
    monkeypatch.setenv("TBCC_LOCAL_TELETHON_ALLOWED", "1")

    tsl.assert_safe_to_open_telethon_session("admin")  # no raise


def test_refuses_for_every_session_kind(monkeypatch):
    from app.services import telethon_session_lock as tsl

    monkeypatch.delenv("TBCC_REVENUE_ISLAND_ACTIVE", raising=False)
    monkeypatch.delenv("TBCC_LOCAL_TELETHON_ALLOWED", raising=False)

    for kind in ("admin", "import", "album", "poster"):
        with pytest.raises(RuntimeError, match="Refusing to open the local Telethon"):
            tsl.assert_safe_to_open_telethon_session(kind)


def test_revenue_island_active_env_variants(monkeypatch):
    from app.services import telethon_session_lock as tsl

    for truthy in ("1", "true", "True", "yes", "on"):
        monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", truthy)
        assert tsl.revenue_island_active() is True

    for falsy in ("0", "false", "", "no", "off"):
        monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", falsy)
        assert tsl.revenue_island_active() is False
