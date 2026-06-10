"""Effective secretary settings: DB overrides with env fallbacks."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.models.secretary_settings import ROW_ID, SecretarySettings

ROW_ID = ROW_ID


def _env_bool(key: str, default: bool) -> bool:
    raw = (os.getenv(key) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(key: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def ensure_settings_row(db: Session) -> SecretarySettings:
    row = db.query(SecretarySettings).filter(SecretarySettings.id == ROW_ID).first()
    if row:
        return row
    row = SecretarySettings(id=ROW_ID)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_effective_secretary_settings(db: Session | None = None) -> dict:
    row = None
    if db is not None:
        row = db.query(SecretarySettings).filter(SecretarySettings.id == ROW_ID).first()

    format_on = _env_bool("TBCC_FORMAT_ENGINE_ENABLED", True)
    llm_refine = _env_bool("TBCC_FORMAT_ENGINE_LLM_REFINE", False)
    rag_on = _env_bool("TBCC_SECRETARY_RAG_ENABLED", True)
    rag_top_k = _env_int("TBCC_SECRETARY_RAG_TOP_K", 4, lo=1, hi=12)
    prompt_extra = (os.getenv("TBCC_SECRETARY_SYSTEM_PROMPT_EXTRA") or "").strip()

    if row:
        if row.format_engine_enabled is not None:
            format_on = bool(row.format_engine_enabled)
        if row.llm_refine_on_phase_change is not None:
            llm_refine = bool(row.llm_refine_on_phase_change)
        if row.rag_enabled is not None:
            rag_on = bool(row.rag_enabled)
        if row.rag_top_k is not None:
            rag_top_k = max(1, min(12, int(row.rag_top_k)))
        if row.system_prompt_extra:
            prompt_extra = row.system_prompt_extra.strip()

    return {
        "format_engine_enabled": format_on,
        "llm_refine_on_phase_change": llm_refine,
        "rag_enabled": rag_on,
        "rag_top_k": rag_top_k,
        "system_prompt_extra": prompt_extra,
        "message_retention": _env_int("TBCC_FORMAT_ENGINE_MESSAGE_RETENTION", 80, lo=10, hi=500),
        "llm_history": _env_int("TBCC_FORMAT_ENGINE_LLM_HISTORY", 8, lo=2, hi=24),
        "rag_embeddings": _env_bool("TBCC_SECRETARY_RAG_EMBEDDINGS", False),
    }
