"""Telegram-oriented defaults for tile encoding."""

from __future__ import annotations

# Custom emoji packs require exactly 100×100 per tile (not 512 sticker size).
DEFAULT_TILE_PX = 100
DEFAULT_AUTHOR_TILE_PX = 512  # master canvas cells when designing at full res
DEFAULT_FPS = 30
DEFAULT_LOOP_SEC = 3.0
DEFAULT_MARGIN_PCT = 8.0
DEFAULT_CRF = 44
# Telegram rejects video stickers above 256 KB in CreateStickerSetRequest.
MAX_TILE_BYTES_TELEGRAM = 256 * 1024
MAX_TILE_BYTES_TARGET = 240 * 1024  # re-encode until under this (safety margin)
MAX_TILE_BYTES_SOFT = MAX_TILE_BYTES_TARGET
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".gif"}
