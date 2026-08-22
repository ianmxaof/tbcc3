"""Extension + local tools: API Pocket — thin HTTP wrapper over the PC-local
slot registry (app/services/api_slot_registry.py). All business logic lives
in that service module; routes here only validate input and translate
service results/ValueErrors into HTTP responses.

POST "" (register) mirrors extension_capture_secret.py's capture flow: it
writes the key to tbcc/.env + Windows Credential Manager AND registers a
slot row in one call, so a freshly-pasted key is immediately callable —
that's the point of API Pocket over the plain capture-secret path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.api_slot_registry import (
    add_slot,
    call_slot,
    get_slot,
    list_slots,
    parse_slot_source,
    remove_slot,
    suggest_slot,
)
from app.services.tbcc_env_secret_store import (
    backup_credential_manager,
    looks_like_api_key,
    write_env_secret,
)

router = APIRouter()


class SuggestSlotBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    page_url: str | None = Field(None, max_length=2048)
    id: str | None = Field(None, max_length=64)


class RegisterSlotBody(BaseModel):
    value: str = Field(..., min_length=1, max_length=4000, description="Pasted key, or multiline url+key")
    page_url: str | None = Field(None, max_length=2048)
    id: str | None = Field(None, max_length=64)
    category: str | None = Field(None, max_length=32)
    base_url: str | None = Field(None, max_length=2048)
    openapi_url: str | None = Field(None, max_length=2048)
    auth_style: str | None = Field(None, max_length=16)


class CallSlotBody(BaseModel):
    body: Any = None
    method: str | None = Field(None, max_length=8)
    path: str | None = Field(None, max_length=512)
    timeout: float = Field(20.0, gt=0, le=120)


@router.get("")
def list_slots_route() -> dict[str, Any]:
    return {"slots": list_slots()}


@router.post("/suggest")
def suggest_slot_route(body: SuggestSlotBody) -> dict[str, Any]:
    return suggest_slot(body.text.strip(), page_url=body.page_url or "", id_override=body.id or "")


@router.post("")
def register_slot(body: RegisterSlotBody) -> dict[str, Any]:
    raw = body.value.strip()
    suggestion = suggest_slot(raw, page_url=body.page_url or "", id_override=body.id or "")
    parsed = parse_slot_source(raw)
    key_value = parsed.get("key") or raw
    if not looks_like_api_key(key_value):
        raise HTTPException(status_code=400, detail="value does not look like an API key")

    auth_env_key = suggestion["auth_env_key"]
    try:
        write_env_secret(auth_env_key, key_value)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    backed_up = backup_credential_manager(auth_env_key, key_value)

    try:
        slot = add_slot(
            slot_id=body.id or suggestion["id"],
            category=body.category or suggestion["category"],
            base_url=body.base_url or suggestion.get("base_url") or "",
            auth_env_key=auth_env_key,
            auth_style=body.auth_style or suggestion["auth_style"],
            openapi_url=body.openapi_url or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "ok": True,
        "id": slot["id"],
        "key": auth_env_key,
        "backed_up_credential_manager": backed_up,
        "slot": slot,
    }


@router.get("/{slot_id}")
def get_slot_route(slot_id: str) -> dict[str, Any]:
    slot = get_slot(slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail=f"slot {slot_id!r} not found")
    return slot


@router.post("/{slot_id}/call")
def call_slot_route(slot_id: str, payload: CallSlotBody) -> dict[str, Any]:
    return call_slot(slot_id, body=payload.body, method=payload.method, path=payload.path, timeout=payload.timeout)


@router.delete("/{slot_id}")
def remove_slot_route(slot_id: str) -> dict[str, Any]:
    if not remove_slot(slot_id):
        raise HTTPException(status_code=404, detail=f"slot {slot_id!r} not found")
    return {"ok": True}
