"""Run multiple python-telegram-bot Applications on one asyncio event loop.

Phase 1 co-host spike: ``run_polling()`` is single-bot only. This module follows
PTB's manual lifecycle (initialize → start → updater.start_polling → … → shutdown)
so N bots with distinct tokens can share one process without Telegram 409.

Do not wire into tray until Phase 2. Live co-host must not run while a separate
tray process polls the same token.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Sequence

from telegram.ext import Application

logger = logging.getLogger(__name__)


async def run_applications(
    apps: Sequence[Application],
    *,
    stop_event: asyncio.Event | None = None,
    drop_pending_updates: bool = False,
) -> None:
    """Start all apps' pollers, wait until stop_event (or forever), then shut down."""
    if not apps:
        raise ValueError("run_applications requires at least one Application")

    owned_stop = stop_event is None
    if stop_event is None:
        stop_event = asyncio.Event()

    started: list[Application] = []
    try:
        for app in apps:
            await app.initialize()
            await app.start()
            if app.updater is None:
                raise RuntimeError("Application has no updater; cannot start_polling")
            await app.updater.start_polling(
                drop_pending_updates=drop_pending_updates,
                allowed_updates=None,
            )
            started.append(app)
            bot = app.bot
            uname = getattr(bot, "username", None) or "?"
            logger.info("zeus multi-app: polling started for bot @%s", uname)

        loop = asyncio.get_running_loop()
        if owned_stop:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except (NotImplementedError, RuntimeError, ValueError):
                    # Windows ProactorEventLoop: signals via KeyboardInterrupt in run()
                    pass

        await stop_event.wait()
    finally:
        for app in reversed(started):
            try:
                if app.updater and app.updater.running:
                    await app.updater.stop()
            except Exception:
                logger.exception("zeus multi-app: updater.stop failed")
            try:
                if app.running:
                    await app.stop()
            except Exception:
                logger.exception("zeus multi-app: application.stop failed")
            try:
                await app.shutdown()
            except Exception:
                logger.exception("zeus multi-app: application.shutdown failed")


def run_applications_sync(apps: Sequence[Application], **kwargs) -> None:
    """Blocking entry for ``python -m`` scripts (Windows-friendly)."""
    asyncio.run(run_applications(apps, **kwargs))
