"""Shared watermark option payloads (API, album bot, dashboard)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WatermarkOptions(BaseModel):
    """Per-request / per-session overrides. None fields inherit effective global settings."""

    enabled: bool | None = None
    skip: bool = False
    text: str | None = Field(None, max_length=120)
    text_secondary: str | None = Field(None, max_length=120)
    text_tertiary: str | None = Field(None, max_length=120)
    opacity: float | None = Field(None, ge=0.15, le=1.0)
    color: str | None = Field(None, max_length=16, description="#RRGGBB hex")
    strip_previous: bool | None = None

    def applies(self) -> bool:
        if self.skip:
            return False
        if self.enabled is False:
            return False
        return True
