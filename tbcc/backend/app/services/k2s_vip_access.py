"""VIP direct K2S download URLs for pack modifiers."""

from __future__ import annotations

import logging

from app.models.loot import LootModifier
from app.services.keep2share_client import get_direct_download_url, k2s_configured
from app.services.k2s_lane_folders import vip_direct_enabled
from app.services.k2s_mirror_service import parse_k2s_tokens

logger = logging.getLogger(__name__)


def resolve_k2s_vip_download_url(mod: LootModifier) -> tuple[str | None, str | None]:
    """
    Return a temp direct download URL for VIP subscribers when a mirrored K2S file exists.
    """
    if not k2s_configured() or not vip_direct_enabled():
        return None, "disabled"
    tokens = parse_k2s_tokens(mod.source_note)
    file_id = tokens.get("k2s_file_id")
    if not file_id:
        return None, "no_k2s_file"
    url, err = get_direct_download_url(file_id)
    if url:
        return url, None
    return None, err or "getUrl_failed"
