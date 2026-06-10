"""FAQ retrieval for secretary bot — keyword scoring with optional OpenAI embeddings."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.services.secretary_settings_effective import get_effective_secretary_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _embedding_model() -> str:
    return (os.getenv("TBCC_SECRETARY_RAG_EMBEDDING_MODEL") or "text-embedding-3-small").strip()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_score(query_tokens: set[str], title: str, body: str, tags: str | None) -> float:
    if not query_tokens:
        return 0.0
    title_t = _tokenize(title)
    body_t = _tokenize(body)
    tag_t = _tokenize(tags or "")
    title_hits = len(query_tokens & title_t)
    body_hits = len(query_tokens & body_t)
    tag_hits = len(query_tokens & tag_t)
    return title_hits * 3.0 + tag_hits * 2.0 + body_hits * 1.0


def _load_embedding(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [float(x) for x in data]
    except Exception:
        return None
    return None


def fetch_embedding(text: str) -> list[float] | None:
    key = _openai_key()
    if not key:
        return None
    snippet = (text or "").strip()[:8000]
    if not snippet:
        return None
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": _embedding_model(), "input": snippet},
            )
            if not r.is_success:
                logger.warning("RAG embedding HTTP %s", r.status_code)
                return None
            data = r.json()
        emb = ((data.get("data") or [{}])[0].get("embedding") or [])
        return [float(x) for x in emb]
    except Exception as e:
        logger.warning("RAG embedding failed: %s", e)
        return None


def search_knowledge(
    query: str,
    *,
    db: Session | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Return top matching FAQ chunks with scores."""
    eff = get_effective_secretary_settings(db)
    if not eff.get("rag_enabled"):
        return []
    k = top_k if top_k is not None else int(eff.get("rag_top_k") or 4)
    q_tokens = _tokenize(query)
    if not q_tokens and not query.strip():
        return []

    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        rows = (
            db.query(SecretaryKnowledgeEntry)
            .filter(SecretaryKnowledgeEntry.is_active.is_(True))
            .order_by(SecretaryKnowledgeEntry.id.desc())
            .all()
        )
        if not rows:
            return []

        query_emb: list[float] | None = None
        use_emb = bool(eff.get("rag_embeddings")) and _openai_key()
        if use_emb:
            query_emb = fetch_embedding(query)

        scored: list[tuple[float, SecretaryKnowledgeEntry]] = []
        for row in rows:
            kw = _keyword_score(q_tokens, row.title or "", row.body or "", row.tags)
            emb_score = 0.0
            if query_emb:
                row_emb = _load_embedding(row.embedding_json)
                if row_emb:
                    emb_score = _cosine(query_emb, row_emb) * 10.0
            total = kw + emb_score
            if total > 0 or (not q_tokens and row.id):
                scored.append((total, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        for score, row in scored[:k]:
            if score <= 0 and q_tokens:
                continue
            out.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "body": row.body,
                    "tags": row.tags,
                    "source_path": row.source_path,
                    "score": round(score, 3),
                }
            )
        return out
    finally:
        if own_db and db is not None:
            db.close()


def build_rag_context_suffix(query: str, *, db: Session | None = None) -> str:
    """Format retrieved chunks for injection into secretary LLM system suffix."""
    hits = search_knowledge(query, db=db)
    if not hits:
        return ""
    lines = ["--- FAQ knowledge (retrieved) ---", "Use these facts when relevant; do not invent policies."]
    for i, h in enumerate(hits, 1):
        title = (h.get("title") or "FAQ").strip()
        body = (h.get("body") or "").strip()[:1200]
        lines.append(f"[{i}] {title}\n{body}")
    lines.append("--- end FAQ knowledge ---")
    return "\n".join(lines)


def _split_markdown(text: str, *, source_path: str) -> list[dict[str, str]]:
    """Split markdown by ## headers into chunks."""
    chunks: list[dict[str, str]] = []
    parts = re.split(r"(?m)^##\s+", text)
    if len(parts) <= 1:
        body = text.strip()
        if body:
            chunks.append({"title": Path(source_path).stem, "body": body[:16000]})
        return chunks
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        title = lines[0].strip()[:256]
        body = lines[1].strip() if len(lines) > 1 else part
        if body:
            chunks.append({"title": title or Path(source_path).stem, "body": body[:16000]})
    return chunks


def import_docs_from_tbcc(*, db: Session, docs_dir: Path | None = None) -> dict[str, int]:
    """Import / refresh chunks from tbcc/docs/*.md."""
    if docs_dir is None:
        docs_dir = Path(__file__).resolve().parent.parent.parent.parent / "docs"
    if not docs_dir.is_dir():
        return {"files": 0, "chunks": 0, "error": "docs dir missing"}

    files = sorted(docs_dir.glob("*.md"))
    total_chunks = 0
    use_emb = get_effective_secretary_settings(db).get("rag_embeddings") and _openai_key()

    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("RAG import skip %s: %s", fp, e)
            continue
        rel = str(fp.relative_to(docs_dir.parent)).replace("\\", "/")
        db.query(SecretaryKnowledgeEntry).filter(SecretaryKnowledgeEntry.source_path == rel).delete(
            synchronize_session=False
        )
        for idx, chunk in enumerate(_split_markdown(text, source_path=rel)):
            emb_json = None
            if use_emb:
                emb = fetch_embedding(f"{chunk['title']}\n{chunk['body']}")
                if emb:
                    emb_json = json.dumps(emb)
            db.add(
                SecretaryKnowledgeEntry(
                    title=chunk["title"],
                    body=chunk["body"],
                    tags="auto-import,docs",
                    source_path=rel,
                    chunk_index=idx,
                    is_active=True,
                    embedding_json=emb_json,
                )
            )
            total_chunks += 1
    db.commit()
    return {"files": len(files), "chunks": total_chunks}


def reindex_embeddings(db: Session) -> dict[str, int]:
    """Compute embeddings for all active entries missing them."""
    if not _openai_key():
        return {"updated": 0, "error": "no OpenAI key"}
    rows = db.query(SecretaryKnowledgeEntry).filter(SecretaryKnowledgeEntry.is_active.is_(True)).all()
    n = 0
    for row in rows:
        text = f"{row.title or ''}\n{row.body or ''}".strip()
        emb = fetch_embedding(text)
        if emb:
            row.embedding_json = json.dumps(emb)
            n += 1
    db.commit()
    return {"updated": n, "total": len(rows)}
