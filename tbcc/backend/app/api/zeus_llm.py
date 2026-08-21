"""Zeus v1 — LLM ask endpoint.

Agent/CLI-facing wrapper over the existing provider fallback chain
(app/services/llm_completions.py + llm_provider_fallback.py) — no new provider
logic, just exposes what already exists over HTTP so any process (or a human via
scripts/tbcc_cli.py ask, or an MCP tool) can reach it without importing backend
internals directly. Sibling of zeus_v1.py's read-only facade — this is the one
endpoint in the namespace that does work rather than reporting status, but it's
still bounded: no Start/Stop, no Telethon, no DB mutation.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/zeus/v1", tags=["zeus-v1"])


class AskBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    system: str | None = None
    provider: str | None = None
    model: str | None = None
    max_tokens: int = Field(default=600, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    no_fallback: bool = False


@router.get("/ask/providers")
def zeus_ask_providers() -> dict[str, Any]:
    """Which of the 12 configured providers currently resolve — no network call."""
    from app.services.llm_provider_fallback import DEFAULT_CHAIN, try_resolve_provider

    rows = []
    for pid in (*DEFAULT_CHAIN, "openai"):
        rt = try_resolve_provider(pid)
        rows.append({"provider": pid, "configured": rt is not None, "model": rt.model if rt else None})
    return {"providers": rows}


@router.post("/ask")
async def zeus_ask_llm(body: AskBody) -> dict[str, Any]:
    """One-shot LLM completion. provider unset = walk the full fallback chain;
    provider set = try it first, then fall back through the rest of the chain
    unless no_fallback is true."""
    from app.services.llm_completions import (
        TextLlmRuntime,
        complete_chat_text_sync,
        resolve_text_llm_runtime,
    )
    from app.services.llm_provider_fallback import complete_chat_text_with_fallback

    messages: list[dict[str, str]] = []
    if body.system:
        messages.append({"role": "system", "content": body.system})
    messages.append({"role": "user", "content": body.prompt})

    primary: TextLlmRuntime | None = None
    if body.provider:
        try:
            primary = resolve_text_llm_runtime(provider=body.provider, model=body.model)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        if body.no_fallback:
            text = await asyncio.to_thread(
                complete_chat_text_sync,
                messages,
                model=body.model,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                runtime=primary,
            )
        else:
            text = await complete_chat_text_with_fallback(
                messages,
                primary=primary,
                model=body.model,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {"ok": True, "provider": body.provider or "auto", "reply": text}
