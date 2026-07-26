"""Zeus multi-Application host — lifecycle unit tests (no live Telegram)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bots.zeus_multi_app import run_applications


def _fake_app(name: str) -> MagicMock:
    app = MagicMock(name=f"app_{name}")
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.running = True
    app.bot = MagicMock(username=name)
    updater = MagicMock()
    updater.start_polling = AsyncMock()
    updater.stop = AsyncMock()
    updater.running = True
    app.updater = updater
    return app


def test_run_applications_starts_and_stops_in_order():
    a = _fake_app("sec")
    b = _fake_app("llm")
    stop = asyncio.Event()
    stop.set()
    asyncio.run(run_applications([a, b], stop_event=stop))

    a.initialize.assert_awaited()
    b.initialize.assert_awaited()
    a.start.assert_awaited()
    b.start.assert_awaited()
    a.updater.start_polling.assert_awaited()
    b.updater.start_polling.assert_awaited()

    assert b.updater.stop.await_count == 1
    assert a.updater.stop.await_count == 1
    assert b.stop.await_count == 1
    assert a.stop.await_count == 1
    assert b.shutdown.await_count == 1
    assert a.shutdown.await_count == 1


def test_run_applications_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        asyncio.run(run_applications([]))


def test_cohost_spike_requires_env_flag(monkeypatch):
    monkeypatch.delenv("TBCC_ZEUS_COHOST_SPIKE", raising=False)
    from bots import zeus_cohost_spike as spike

    with pytest.raises(SystemExit) as ei:
        spike.main()
    assert ei.value.code == 2


def test_macro_search_build_application_none_without_token(monkeypatch):
    monkeypatch.delenv("TBCC_MACRO_SEARCH_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MACRO_SEARCH_BOT_TOKEN", raising=False)
    from bots.macro_search_bot import build_application

    assert build_application("") is None


def test_secretary_build_application_none_without_token(monkeypatch):
    monkeypatch.setattr(
        "bots.secretary_bot._secretary_token",
        lambda: "",
    )
    from bots.secretary_bot import build_application

    assert build_application("") is None
