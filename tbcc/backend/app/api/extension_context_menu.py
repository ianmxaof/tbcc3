"""Dashboard + extension sync for context menu item visibility."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.extension_context_menu import (
    get_extension_context_menu_settings,
    patch_extension_context_menu_settings,
)

router = APIRouter()


class ExtensionContextMenuPatch(BaseModel):
    pageMenu: dict[str, bool] | None = Field(None, description="Page media menu item toggles")


@router.get("")
def get_context_menu_settings() -> dict[str, Any]:
    return get_extension_context_menu_settings()


@router.patch("")
def patch_context_menu_settings(body: ExtensionContextMenuPatch) -> dict[str, Any]:
    out = patch_extension_context_menu_settings(body.pageMenu)
    out["saved"] = True
    return out
