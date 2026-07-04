"""Tests for companion gate channel-admin probe."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import companion_gate_health as cgh


@pytest.mark.asyncio
async def test_probe_all_admin(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_BOT_TOKEN", "test-token")
    cgh._CACHE.clear()

    async def fake_get(url, **kwargs):
        class Resp:
            def json(self):
                if url.endswith("/getMe"):
                    return {"ok": True, "result": {"id": 111}}
                return {"ok": True, "result": {"status": "administrator"}}

        return Resp()

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get = AsyncMock(side_effect=fake_get)
        client_cls.return_value = client

        out = await cgh.probe_companion_bot_channel_admin(force=True)
        assert out["ok"]
        assert out["bot_admin_all_channels"]


@pytest.mark.asyncio
async def test_probe_missing_admin(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_BOT_TOKEN", "test-token")
    cgh._CACHE.clear()

    calls = {"n": 0}

    async def fake_get(url, **kwargs):
        class Resp:
            def json(self):
                if url.endswith("/getMe"):
                    return {"ok": True, "result": {"id": 111}}
                calls["n"] += 1
                if calls["n"] == 1:
                    return {"ok": True, "result": {"status": "administrator"}}
                return {"ok": False, "description": "Bad Request: chat not found"}

        return Resp()

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get = AsyncMock(side_effect=fake_get)
        client_cls.return_value = client

        out = await cgh.probe_companion_bot_channel_admin(force=True)
        assert out["ok"]
        assert not out["bot_admin_all_channels"]
        assert out["missing_channels"]
