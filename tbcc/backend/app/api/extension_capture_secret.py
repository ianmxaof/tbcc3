"""Extension + local tools: capture API keys into tbcc/.env."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.tbcc_env_secret_store import (
    backup_credential_manager,
    list_env_secret_keys,
    looks_like_api_key,
    normalize_env_key,
    suggest_env_key,
    write_env_secret,
)

router = APIRouter()


class CaptureSecretBody(BaseModel):
    value: str = Field(..., min_length=1, max_length=600)
    key: str | None = Field(None, max_length=128)
    page_url: str | None = Field(None, max_length=2048)


@router.get("/keys")
def list_keys() -> dict[str, Any]:
    keys = list_env_secret_keys()
    return {"keys": keys}


@router.post("/suggest")
def suggest(body: CaptureSecretBody) -> dict[str, Any]:
    value = body.value.strip()
    suggested = suggest_env_key(value=value, page_url=body.page_url or "")
    return {
        "suggested_key": suggested,
        "looks_like_api_key": looks_like_api_key(value),
        "keys": list_env_secret_keys(),
    }


@router.post("")
def capture_secret(body: CaptureSecretBody) -> dict[str, Any]:
    value = body.value.strip()
    key = normalize_env_key(body.key or "") or suggest_env_key(value=value, page_url=body.page_url or "")
    if not key:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "key_required",
                "message": "Could not guess env var — pass key or use Windows desktop menu.",
                "keys": list_env_secret_keys(),
            },
        )
    if not looks_like_api_key(value):
        raise HTTPException(status_code=400, detail="value does not look like an API key")
    try:
        write_env_secret(key, value)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    backed_up = backup_credential_manager(key, value)
    return {"ok": True, "key": key, "backed_up_credential_manager": backed_up}
