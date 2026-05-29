"""Interpret Buffer GraphQL createPost responses."""

from __future__ import annotations

from typing import Any


def buffer_create_post_succeeded(res: dict[str, Any]) -> bool:
    if res.get("error"):
        return False
    cp = (res.get("data") or {}).get("createPost") if isinstance(res.get("data"), dict) else None
    if isinstance(cp, dict) and cp.get("post"):
        return True
    return False


def buffer_create_post_error_message(res: dict[str, Any]) -> str | None:
    if res.get("error"):
        return str(res["error"])
    cp = (res.get("data") or {}).get("createPost") if isinstance(res.get("data"), dict) else None
    if isinstance(cp, dict) and cp.get("message"):
        return str(cp["message"])
    return None
