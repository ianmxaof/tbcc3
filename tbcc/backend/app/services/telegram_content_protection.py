"""Telegram content protection for channel preview posts (noforwards / protect_content)."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def channel_protect_content_enabled() -> bool:
    """Block forwarding/saving on preview channel posts (default on)."""
    raw = (os.getenv("TBCC_CHANNEL_PROTECT_CONTENT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def bot_protect_content_kw() -> dict[str, Any]:
    """Bot API kwargs for send_photo / send_media_group / etc."""
    if channel_protect_content_enabled():
        return {"protect_content": True}
    return {}


def bot_protect_content_form_fields() -> dict[str, str]:
    """Multipart form fields for httpx Bot API calls (e.g. sendPhoto)."""
    if channel_protect_content_enabled():
        return {"protect_content": "true"}
    return {}


@contextlib.asynccontextmanager
async def telethon_protect_context(client: Any):
    """
    Patch Telethon ``__call__`` so SendMedia / SendMultiMedia / SendMessage set noforwards.

    Telethon user-session send_file does not expose noforwards yet; this injects it at dispatch.
  """
    if not channel_protect_content_enabled():
        yield
        return

    from telethon.tl.functions.messages import (
        SendMediaRequest,
        SendMessageRequest,
        SendMultiMediaRequest,
    )

    protect_types = (SendMediaRequest, SendMultiMediaRequest, SendMessageRequest)
    original_call = client.__call__

    async def protected_call(request, ordered=False, flood_sleep_threshold=None):
        if isinstance(request, protect_types):
            try:
                request.noforwards = True
            except (AttributeError, TypeError):
                logger.debug("telethon noforwards inject skipped for %s", type(request).__name__)
        return await original_call(
            request,
            ordered=ordered,
            flood_sleep_threshold=flood_sleep_threshold,
        )

    client.__call__ = protected_call
    try:
        yield
    finally:
        client.__call__ = original_call
