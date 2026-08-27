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
    _pastebin_preset,
    _shrinkme_preset,
    add_slot,
    call_slot,
    get_slot,
    list_slots,
    parse_slot_source,
    remove_slot,
    suggest_slot,
)
from app.services.llm_model_index import set_credential as set_llm_credential
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
    auth_env_key: str | None = Field(None, max_length=128)


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


def register_slot_from_paste(
    value: str,
    *,
    page_url: str = "",
    id: str = "",  # noqa: A002 — mirrors RegisterSlotBody.id / suggest_slot's id_override
    category: str | None = None,
    base_url: str | None = None,
    openapi_url: str | None = None,
    auth_style: str | None = None,
    auth_env_key: str | None = None,
) -> dict[str, Any]:
    """Paste-and-go registration: classify -> write .env -> back up Credential
    Manager -> register the slot, in one call. Shared by the extension/API
    route below and the operator TUI's Keys pane so a freshly-pasted key is
    immediately callable from either surface. Raises ValueError (not
    HTTPException — this is a plain function, not a route) on a bad key or a
    missing .env file.

    When the slot classifies as category "llm" (env-key or base-url hint —
    see api_slot_registry._LLM_ENV_HINTS/_LLM_URL_HINTS) and a base_url is
    known, this ALSO registers the same id as an LLM rotator provider
    (llm_model_index.set_credential) — the "API Pocket" slot registry and the
    rotator's own credential store are two separate systems, and previously
    nothing bridged them: a key registered here was callable via `slots call`
    but invisible to `llm ask` / the operator TUI's Ask pane. Deferred since
    the original API Pocket phases (see tbcc/docs/handoffs/
    2026-08-22_api-pocket-phase2_report.md, "LLM-category bridge") — built
    now because a real registration (Venice/OrcaRouter) hit exactly this gap:
    landed in the slot registry with no base_url and the wrong category,
    silently unusable for Ask.

    An explicit base_url always wins for classification too, not just the
    final stored value — prepended ahead of the pasted text so parse_slot_source
    picks it up as "the" URL. Without this, a bare key with no URL in the
    paste itself (the exact case that produced the broken tbcc-generic slot)
    would still classify as generic-rest / TBCC_GENERIC_API_KEY even with the
    field filled in, since suggest_slot's own text-parsing never saw it.

    id / category / base_url / auth_style / auth_env_key are all optional
    overrides on top of auto-detection — every one of them was previously
    settable only via suggest_slot's internal heuristics with no way to
    correct a wrong guess short of removing and re-adding the slot from the
    CLI. auth_env_key specifically had no override at all before this."""
    raw = (value or "").strip()
    classify_source = f"{base_url}\n{raw}" if base_url else raw
    suggestion = suggest_slot(
        classify_source, page_url=page_url, id_override=id, auth_env_key_override=auth_env_key or ""
    )
    parsed = parse_slot_source(classify_source)
    key_value = parsed.get("key") or raw
    if not looks_like_api_key(key_value):
        raise ValueError("value does not look like an API key")

    auth_env_key_final = auth_env_key or suggestion["auth_env_key"]
    slot_id_final = id or suggestion["id"]
    base_url_final = base_url or suggestion.get("base_url") or ""
    auth_style_final = auth_style or suggestion["auth_style"]
    method_final = "GET"
    path_final = ""

    preset = _pastebin_preset(
        base_url=base_url_final or "",
        auth_env_key=auth_env_key_final,
        slot_id=slot_id_final,
    ) or _shrinkme_preset(
        base_url=base_url_final or "",
        auth_env_key=auth_env_key_final,
        slot_id=slot_id_final,
    )
    if preset:
        base_url_final = preset["base_url"]
        path_final = preset["path_template"]
        method_final = preset["method"]
        auth_style_final = preset["auth_style"]
        if not id:
            slot_id_final = preset["id"]
        if "pastebin" in str(slot_id_final) and auth_env_key_final in (
            "TBCC_PASTEBIN_API",
            "TBCC_PASTEBIN_API_KEY",
            "TBCC_GENERIC_API_KEY",
        ):
            auth_env_key_final = "TBCC_PASTEBIN_API_DEV_KEY"

    write_env_secret(auth_env_key_final, key_value)
    backed_up = backup_credential_manager(auth_env_key_final, key_value)

    slot = add_slot(
        slot_id=slot_id_final,
        category=category or suggestion["category"],
        base_url=base_url_final,
        auth_env_key=auth_env_key_final,
        auth_style=auth_style_final,
        openapi_url=openapi_url or "",
        method=method_final,
        path_template=path_final,
    )

    llm_provider_registered = False
    if slot["category"] == "llm" and slot.get("base_url"):
        set_llm_credential(slot["id"], key_value, base_url=slot["base_url"])
        llm_provider_registered = True

    return {
        "ok": True,
        "id": slot["id"],
        "key": auth_env_key_final,
        "backed_up_credential_manager": backed_up,
        "llm_provider_registered": llm_provider_registered,
        "slot": slot,
    }


@router.post("")
def register_slot(body: RegisterSlotBody) -> dict[str, Any]:
    try:
        return register_slot_from_paste(
            body.value,
            page_url=body.page_url or "",
            id=body.id or "",
            category=body.category,
            base_url=body.base_url,
            openapi_url=body.openapi_url,
            auth_style=body.auth_style,
            auth_env_key=body.auth_env_key,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
