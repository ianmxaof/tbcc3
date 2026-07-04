"""Effective secretary settings: DB overrides with env fallbacks."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.secretary_settings import ROW_ID, SecretarySettings
from app.services.secretary_llm import resolve_system_prompt

ROW_ID = ROW_ID

FE_VERBOSITY_VALUES = ("compact", "standard")
LLM_PROVIDERS = ("openai", "openrouter")


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
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        row = db.query(SecretarySettings).filter(SecretarySettings.id == ROW_ID).first()

        format_on = _env_bool("TBCC_FORMAT_ENGINE_ENABLED", True)
        fe_verbosity = (os.getenv("TBCC_FORMAT_ENGINE_VERBOSITY") or "compact").strip().lower()
        if fe_verbosity not in FE_VERBOSITY_VALUES:
            fe_verbosity = "compact"
        public_faq = _env_bool("TBCC_SECRETARY_PUBLIC_FAQ", True)
        llm_refine = _env_bool("TBCC_FORMAT_ENGINE_LLM_REFINE", False)
        rag_on = _env_bool("TBCC_SECRETARY_RAG_ENABLED", True)
        rag_top_k = _env_int("TBCC_SECRETARY_RAG_TOP_K", 4, lo=1, hi=12)
        prompt_extra = (os.getenv("TBCC_SECRETARY_SYSTEM_PROMPT_EXTRA") or "").strip()
        llm_provider = (os.getenv("TBCC_LLM_PROVIDER") or "openai").strip().lower()
        llm_model = (os.getenv("TBCC_SECRETARY_LLM_MODEL") or os.getenv("TBCC_LLM_MODEL") or "").strip()
        llm_base_url = (os.getenv("TBCC_OPENROUTER_BASE_URL") or "").strip() or None
        llm_api_key = ""

        if row:
            if row.format_engine_enabled is not None:
                format_on = bool(row.format_engine_enabled)
            if row.fe_verbosity:
                v = str(row.fe_verbosity).strip().lower()
                if v in FE_VERBOSITY_VALUES:
                    fe_verbosity = v
            if row.public_faq_enabled is not None:
                public_faq = bool(row.public_faq_enabled)
            if row.llm_refine_on_phase_change is not None:
                llm_refine = bool(row.llm_refine_on_phase_change)
            if row.rag_enabled is not None:
                rag_on = bool(row.rag_enabled)
            if row.rag_top_k is not None:
                rag_top_k = max(1, min(12, int(row.rag_top_k)))
            if row.system_prompt_extra:
                prompt_extra = row.system_prompt_extra.strip()
            if row.llm_provider:
                p = str(row.llm_provider).strip().lower()
                if p in LLM_PROVIDERS:
                    llm_provider = p
            if row.llm_model:
                llm_model = str(row.llm_model).strip()
            if row.llm_base_url:
                llm_base_url = str(row.llm_base_url).strip() or None
            if row.llm_api_key:
                llm_api_key = str(row.llm_api_key).strip()

        system_prompt, system_prompt_source = resolve_system_prompt(db)

        return {
            "format_engine_enabled": format_on,
            "fe_verbosity": fe_verbosity,
            "public_faq_enabled": public_faq,
            "llm_refine_on_phase_change": llm_refine,
            "rag_enabled": rag_on,
            "rag_top_k": rag_top_k,
            "system_prompt": system_prompt,
            "system_prompt_source": system_prompt_source,
            "system_prompt_extra": prompt_extra,
            "message_retention": _env_int("TBCC_FORMAT_ENGINE_MESSAGE_RETENTION", 80, lo=10, hi=500),
            "llm_history": _env_int("TBCC_FORMAT_ENGINE_LLM_HISTORY", 8, lo=2, hi=24),
            "rag_embeddings": _env_bool("TBCC_SECRETARY_RAG_EMBEDDINGS", False),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
        }
    finally:
        if own_db and db is not None:
            db.close()
