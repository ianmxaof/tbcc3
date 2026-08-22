"""Regression: async lock-acquire wrappers must mark the hold on the CALLING thread.

`_held_lock_labels` is threading.local. The sync acquire functions run inside
`asyncio.to_thread(...)`, i.e. on a real separate OS thread — a mark set there
never reaches the event-loop thread that later calls `require_telethon_session_lock`.
Every channel-import job failed with "Redis session lock not held (held=none)"
on the island because of exactly this gap (2026-08-22).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "kind,acquire_fn,release_fn,acquire_async,release_async",
    [
        ("admin", "acquire_admin_session_lock", "release_admin_session_lock",
         "acquire_admin_session_lock_async", "release_admin_session_lock_async"),
        ("import", "acquire_import_session_lock", "release_import_session_lock",
         "acquire_import_session_lock_async", "release_import_session_lock_async"),
        ("poster", "acquire_poster_session_lock", "release_poster_session_lock",
         "acquire_poster_session_lock_async", "release_poster_session_lock_async"),
    ],
)
def test_async_acquire_marks_lock_visible_on_calling_thread(
    kind, acquire_fn, release_fn, acquire_async, release_async, monkeypatch
):
    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REQUIRE_TELETHON_SESSION_LOCK", "1")
    tsl._held_set().clear()

    async def run():
        with patch.object(tsl, acquire_fn, return_value="tok-123"):
            token = await getattr(tsl, acquire_async)(30.0)
        # This is the real bug reproduction: require_telethon_session_lock runs on
        # THIS (event-loop) thread, same as the caller of the async wrapper above —
        # asyncio.to_thread ran the mocked acquire on a different OS thread entirely.
        tsl.require_telethon_session_lock(kind)  # must not raise
        with patch.object(tsl, release_fn, return_value=None):
            await getattr(tsl, release_async)(token)
        with pytest.raises(RuntimeError, match="Redis session lock not held"):
            tsl.require_telethon_session_lock(kind)

    asyncio.run(run())


def test_async_acquire_actually_runs_sync_half_on_a_different_thread(monkeypatch):
    """Sanity check the reproduction is real: to_thread must not be the calling thread."""
    import threading

    from app.services import telethon_session_lock as tsl

    monkeypatch.setenv("TBCC_REQUIRE_TELETHON_SESSION_LOCK", "1")
    tsl._held_set().clear()
    calling_thread = threading.get_ident()
    seen_thread = {}

    def fake_acquire(timeout_s=None):
        seen_thread["id"] = threading.get_ident()
        return "tok"

    async def run():
        with patch.object(tsl, "acquire_import_session_lock", side_effect=fake_acquire):
            await tsl.acquire_import_session_lock_async(30.0)

    asyncio.run(run())
    assert seen_thread["id"] != calling_thread
