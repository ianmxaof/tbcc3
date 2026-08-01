"""Import worker asyncio loop runs on a dedicated thread (no nested run_until_complete)."""

from __future__ import annotations

import asyncio

from app.services import import_job_runner as ijr


def test_run_on_worker_loop_uses_dedicated_thread():
    async def _ping() -> str:
        await asyncio.sleep(0)
        return "pong"

    assert ijr._run_on_worker_loop(_ping()) == "pong"
    loop = ijr._ensure_worker_loop_thread()
    assert loop.is_running()
    assert ijr._worker_loop_thread is not None
    assert ijr._worker_loop_thread.is_alive()
