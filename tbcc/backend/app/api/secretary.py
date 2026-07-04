"""Secretary bot admin: Format Engine contexts, settings, FAQ knowledge (RAG), test playground."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.models.secretary_settings import ROW_ID, SecretarySettings
from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext
from app.services.format_engine import PHASES, _load_format, _save_format, context_to_dict, reset_user_context
from app.services.secretary_llm import complete_secretary_chat, default_system_prompt
from app.services.secretary_llm_config import secretary_llm_configured, secretary_llm_status
from app.services.secretary_rag import build_rag_context_suffix, import_docs_from_tbcc, reindex_embeddings, search_knowledge
from app.services.secretary_settings_effective import ensure_settings_row, get_effective_secretary_settings

router = APIRouter()


class SecretarySettingsPatch(BaseModel):
    format_engine_enabled: bool | None = None
    fe_verbosity: Literal["compact", "standard"] | None = None
    public_faq_enabled: bool | None = None
    llm_refine_on_phase_change: bool | None = None
    llm_provider: Literal["openai", "openrouter"] | None = None
    llm_api_key: str | None = Field(None, max_length=512)
    clear_llm_api_key: bool | None = None
    llm_model: str | None = Field(None, max_length=128)
    llm_base_url: str | None = Field(None, max_length=256)
    rag_enabled: bool | None = None
    rag_top_k: int | None = Field(None, ge=1, le=12)
    system_prompt: str | None = Field(None, max_length=12000)
    clear_system_prompt: bool | None = None
    system_prompt_extra: str | None = None


class KnowledgeCreate(BaseModel):
    title: str | None = Field(None, max_length=256)
    body: str = Field(..., min_length=1)
    tags: str | None = Field(None, max_length=500)
    is_active: bool = True


class KnowledgeBulkIn(BaseModel):
    items: list[KnowledgeCreate] = Field(..., min_length=1, max_length=200)


class ContextPhasePatch(BaseModel):
    current_phase: str = Field(..., min_length=1, max_length=32)


class TestReplyIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    telegram_user_id: int | None = None
    include_format_engine: bool = True
    include_rag: bool = True


def _settings_overrides(row: SecretarySettings) -> dict[str, Any]:
    return {
        "format_engine_enabled": row.format_engine_enabled,
        "fe_verbosity": row.fe_verbosity,
        "public_faq_enabled": row.public_faq_enabled,
        "llm_refine_on_phase_change": row.llm_refine_on_phase_change,
        "llm_provider": row.llm_provider,
        "llm_model": row.llm_model,
        "llm_base_url": row.llm_base_url,
        "llm_api_key_set": bool((row.llm_api_key or "").strip()),
        "rag_enabled": row.rag_enabled,
        "rag_top_k": row.rag_top_k,
        "system_prompt_set": bool((row.system_prompt or "").strip()),
        "system_prompt_extra": row.system_prompt_extra,
    }


def _settings_response(db: Session) -> dict[str, Any]:
    row = ensure_settings_row(db)
    eff = get_effective_secretary_settings(db)
    llm = secretary_llm_status(db)
    public_eff = {k: v for k, v in eff.items() if k != "llm_api_key"}
    public_eff["llm"] = llm
    return {"effective": public_eff, "overrides": _settings_overrides(row)}


@router.get("/secretary-settings")
def get_secretary_settings(db: Session = Depends(get_db)):
    return _settings_response(db)


@router.patch("/secretary-settings")
def patch_secretary_settings(body: SecretarySettingsPatch, db: Session = Depends(get_db)):
    row = ensure_settings_row(db)
    data = body.model_dump(exclude_unset=True)
    clear_key = bool(data.pop("clear_llm_api_key", False))
    clear_prompt = bool(data.pop("clear_system_prompt", False))
    api_key = data.pop("llm_api_key", None)
    system_prompt = data.pop("system_prompt", None)
    for k, v in data.items():
        if k == "system_prompt_extra" and v is not None:
            v = str(v).strip() or None
        if k == "llm_model" and v is not None:
            v = str(v).strip() or None
        if k == "llm_base_url" and v is not None:
            v = str(v).strip() or None
        setattr(row, k, v)
    if clear_key:
        row.llm_api_key = None
    elif api_key is not None:
        row.llm_api_key = str(api_key).strip() or None
    if clear_prompt:
        row.system_prompt = None
    elif system_prompt is not None:
        cleaned = str(system_prompt).strip() or None
        if cleaned and len(cleaned) > 12000:
            raise HTTPException(status_code=400, detail="system_prompt too long (max 12000)")
        row.system_prompt = cleaned
    db.commit()
    db.refresh(row)
    return {"ok": True, **_settings_response(db)}


@router.post("/secretary-settings/test-llm")
def test_secretary_llm_endpoint(db: Session = Depends(get_db)):
    from app.services.secretary_llm_config import test_secretary_llm

    return test_secretary_llm(db=db)


@router.get("/secretary-contexts")
def list_secretary_contexts(
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=128),
    phase: str | None = Query(None, max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = db.query(SecretaryUserContext)
    if phase:
        query = query.filter(SecretaryUserContext.current_phase == phase.strip())
    if q:
        qs = q.strip().lstrip("@")
        if qs.isdigit():
            query = query.filter(SecretaryUserContext.telegram_user_id == int(qs))
        else:
            query = query.filter(SecretaryUserContext.telegram_username.ilike(f"%{qs}%"))
    total = query.count()
    rows = query.order_by(SecretaryUserContext.updated_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [context_to_dict(r) for r in rows]}


@router.get("/secretary-contexts/{context_id}")
def get_secretary_context(context_id: int, db: Session = Depends(get_db), message_limit: int = Query(40, ge=1, le=200)):
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one_or_none()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    msgs = (
        db.query(SecretaryMessageRecord)
        .filter(SecretaryMessageRecord.context_id == context_id)
        .order_by(SecretaryMessageRecord.created_at.desc())
        .limit(message_limit)
        .all()
    )
    out = context_to_dict(ctx)
    out["messages"] = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "emotion": json.loads(m.emotion_json) if m.emotion_json else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in reversed(msgs)
    ]
    return out


@router.post("/secretary-contexts/{context_id}/reset")
def reset_secretary_context(context_id: int, db: Session = Depends(get_db)):
    if not reset_user_context(db, context_id):
        raise HTTPException(status_code=404, detail="Context not found")
    db.commit()
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one()
    return {"ok": True, "context": context_to_dict(ctx)}


@router.patch("/secretary-contexts/{context_id}")
def patch_secretary_context(context_id: int, body: ContextPhasePatch, db: Session = Depends(get_db)):
    phase = body.current_phase.strip().lower()
    if phase not in PHASES:
        raise HTTPException(status_code=400, detail=f"phase must be one of: {', '.join(PHASES)}")
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one_or_none()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    fmt = _load_format(ctx.interaction_format_json)
    fmt["phase"] = phase
    ctx.current_phase = phase
    ctx.interaction_format_json = _save_format(fmt)
    db.commit()
    db.refresh(ctx)
    return {"ok": True, "context": context_to_dict(ctx)}


@router.get("/secretary-knowledge")
def list_knowledge(db: Session = Depends(get_db), q: str | None = Query(None, max_length=128)):
    query = db.query(SecretaryKnowledgeEntry).order_by(SecretaryKnowledgeEntry.id.desc())
    rows = query.limit(500).all()
    if q:
        qs = q.strip().lower()
        rows = [
            r
            for r in rows
            if qs in (r.title or "").lower()
            or qs in (r.body or "").lower()
            or qs in (r.tags or "").lower()
            or qs in (r.source_path or "").lower()
        ]
    return [
        {
            "id": r.id,
            "title": r.title,
            "body": r.body,
            "tags": r.tags,
            "source_path": r.source_path,
            "chunk_index": r.chunk_index,
            "is_active": r.is_active,
            "has_embedding": bool(r.embedding_json),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/secretary-knowledge")
def create_knowledge(body: KnowledgeCreate, db: Session = Depends(get_db)):
    row = SecretaryKnowledgeEntry(
        title=(body.title or "").strip() or None,
        body=body.body.strip()[:16000],
        tags=(body.tags or "").strip() or None,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "title": row.title}


@router.post("/secretary-knowledge/bulk")
def bulk_knowledge(body: KnowledgeBulkIn, db: Session = Depends(get_db)):
    n = 0
    for it in body.items:
        text = (it.body or "").strip()
        if not text:
            continue
        db.add(
            SecretaryKnowledgeEntry(
                title=(it.title or "").strip() or None,
                body=text[:16000],
                tags=(it.tags or "").strip() or None,
                is_active=it.is_active,
            )
        )
        n += 1
    db.commit()
    return {"created": n}


@router.delete("/secretary-knowledge/{entry_id}")
def delete_knowledge(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(SecretaryKnowledgeEntry).filter(SecretaryKnowledgeEntry.id == entry_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": entry_id}


@router.post("/secretary-knowledge/import-docs")
def import_knowledge_docs(db: Session = Depends(get_db)):
    return import_docs_from_tbcc(db=db)


@router.post("/secretary-knowledge/import-iui-corpus")
def import_iui_knowledge_corpus(db: Session = Depends(get_db)):
    """Import IIU SFW industry research summaries into secretary RAG."""
    from app.services.industry_intelligence import import_iui_corpus

    return import_iui_corpus(db)


@router.post("/secretary-knowledge/reindex-embeddings")
def reindex_knowledge_embeddings(db: Session = Depends(get_db)):
    return reindex_embeddings(db)


@router.post("/secretary-knowledge/search")
def search_knowledge_api(body: dict, db: Session = Depends(get_db)):
    q = str(body.get("q") or "").strip()
    top_k = body.get("top_k")
    if not q:
        raise HTTPException(status_code=400, detail="q required")
    hits = search_knowledge(q, db=db, top_k=int(top_k) if top_k else None)
    return {"query": q, "hits": hits}


@router.post("/secretary-settings/test-reply")
async def test_secretary_reply(body: TestReplyIn, db: Session = Depends(get_db)):
    if not secretary_llm_configured():
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    eff = get_effective_secretary_settings(db)
    extra_parts: list[str] = []
    if body.include_format_engine and eff.get("format_engine_enabled"):
        from app.services.format_engine import preview_user_turn

        if body.telegram_user_id:
            fe_suffix = preview_user_turn(body.telegram_user_id, body.message)
        else:
            from app.services.format_engine import analyze_message, build_context_suffix, _default_format

            a = analyze_message(body.message)
            fe_suffix = build_context_suffix(
                SecretaryUserContext(telegram_user_id=0, current_phase="introduction"),
                a,
                _default_format(),
            )
        if fe_suffix:
            extra_parts.append(fe_suffix)
    if body.include_rag and eff.get("rag_enabled"):
        rag = build_rag_context_suffix(body.message, db=db)
        if rag:
            extra_parts.append(rag)
    if eff.get("system_prompt_extra"):
        extra_parts.append(eff["system_prompt_extra"])

    messages = [
        {"role": "system", "content": default_system_prompt()},
        {"role": "user", "content": body.message.strip()},
    ]
    suffix = "\n\n".join(extra_parts)
    reply = await complete_secretary_chat(messages, extra_system_suffix=suffix)
    return {
        "reply": reply,
        "context_suffix_preview": suffix[:4000] if suffix else "",
        "rag_hits": search_knowledge(body.message, db=db) if eff.get("rag_enabled") else [],
    }
