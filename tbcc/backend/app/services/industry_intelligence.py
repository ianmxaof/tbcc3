"""Industry intelligence — IIU-style benchmarks, RAG corpus import, benchmark-informed signals."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.industry_benchmark import IndustryBenchmark
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.services.secretary_rag import fetch_embedding
from app.services.secretary_settings_effective import get_effective_secretary_settings

logger = logging.getLogger(__name__)

_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BENCHMARKS_JSON = _TBCC_ROOT / "data" / "industry_benchmarks.json"
_IUI_CORPUS_JSON = _TBCC_ROOT / "data" / "iui_industry_corpus.json"


def _load_benchmarks_file() -> dict[str, Any]:
    if not _BENCHMARKS_JSON.is_file():
        return {}
    return json.loads(_BENCHMARKS_JSON.read_text(encoding="utf-8"))


def _load_iui_corpus_file() -> dict[str, Any]:
    if not _IUI_CORPUS_JSON.is_file():
        return {}
    return json.loads(_IUI_CORPUS_JSON.read_text(encoding="utf-8"))


def seed_industry_benchmarks(db: Session) -> dict[str, Any]:
    """Upsert macro + category rows from tbcc/data/industry_benchmarks.json."""
    payload = _load_benchmarks_file()
    if not payload:
        return {"ok": False, "error": "industry_benchmarks.json missing", "upserted": 0}

    year = int(payload.get("effective_year") or 2026)
    upserted = 0

    for row in payload.get("macro") or []:
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        _upsert_benchmark(db, slug=slug, row=row, topic_type=str(row.get("topic_type") or "macro"), year=year)
        upserted += 1

    for row in payload.get("categories") or []:
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        _upsert_benchmark(
            db,
            slug=slug,
            row={
                **row,
                "topic_type": "category",
                "source_url": row.get("source_url") or "https://inside.theporn.com/topic/trends/",
                "source_label": payload.get("source") or "IIU",
            },
            topic_type="category",
            year=year,
        )
        upserted += 1

    db.commit()
    return {"ok": True, "upserted": upserted, "effective_year": year}


def _upsert_benchmark(
    db: Session,
    *,
    slug: str,
    row: dict[str, Any],
    topic_type: str,
    year: int,
) -> None:
    bench_json = row.get("benchmark_json")
    if bench_json is not None and not isinstance(bench_json, str):
        bench_json = json.dumps(bench_json)

    existing = db.query(IndustryBenchmark).filter(IndustryBenchmark.slug == slug).one_or_none()
    fields = {
        "title": str(row.get("title") or slug),
        "topic_type": topic_type,
        "summary": str(row.get("summary") or ""),
        "demand_index": float(row["demand_index"]) if row.get("demand_index") is not None else None,
        "benchmark_json": bench_json,
        "source_url": row.get("source_url"),
        "source_label": row.get("source_label") or "IIU",
        "effective_year": year,
        "is_active": True,
    }
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(IndustryBenchmark(slug=slug, **fields))


def list_industry_benchmarks(
    db: Session,
    *,
    topic_type: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    q = db.query(IndustryBenchmark).order_by(IndustryBenchmark.demand_index.desc())
    if active_only:
        q = q.filter(IndustryBenchmark.is_active.is_(True))
    if topic_type:
        q = q.filter(IndustryBenchmark.topic_type == topic_type)
    out: list[dict[str, Any]] = []
    for row in q.all():
        bench = None
        if row.benchmark_json:
            try:
                bench = json.loads(row.benchmark_json)
            except json.JSONDecodeError:
                bench = row.benchmark_json
        out.append(
            {
                "id": row.id,
                "slug": row.slug,
                "title": row.title,
                "topic_type": row.topic_type,
                "summary": row.summary,
                "demand_index": row.demand_index,
                "benchmark": bench,
                "source_url": row.source_url,
                "source_label": row.source_label,
                "effective_year": row.effective_year,
            }
        )
    return out


def import_iui_corpus(db: Session) -> dict[str, Any]:
    """Import IIU SFW topic summaries into secretary_knowledge for RAG."""
    payload = _load_iui_corpus_file()
    topics = payload.get("topics") or []
    if not topics:
        return {"ok": False, "error": "iui_industry_corpus.json missing or empty", "chunks": 0}

    use_emb = bool(get_effective_secretary_settings(db).get("rag_embeddings"))
    source_prefix = "data/iui_industry_corpus.json"
    db.query(SecretaryKnowledgeEntry).filter(
        SecretaryKnowledgeEntry.source_path.like(f"{source_prefix}#%")
    ).delete(synchronize_session=False)

    chunks = 0
    for topic in topics:
        slug = str(topic.get("slug") or "").strip()
        body = str(topic.get("body") or "").strip()
        if not slug or not body:
            continue
        title = str(topic.get("title") or slug)
        tags = str(topic.get("tags") or "iui,industry-research")
        rel = f"{source_prefix}#{slug}"
        emb_json = None
        if use_emb:
            emb = fetch_embedding(f"{title}\n{body}")
            if emb:
                emb_json = json.dumps(emb)
        db.add(
            SecretaryKnowledgeEntry(
                title=title,
                body=body,
                tags=tags,
                source_path=rel,
                chunk_index=0,
                is_active=True,
                embedding_json=emb_json,
            )
        )
        chunks += 1

    db.commit()
    return {"ok": True, "chunks": chunks, "source_label": payload.get("source_label") or "IIU"}


def benchmark_informed_signals(db: Session) -> list[dict[str, Any]]:
    """Emit content_signals-compatible priors from industry_benchmarks (macro only)."""
    rows = (
        db.query(IndustryBenchmark)
        .filter(IndustryBenchmark.is_active.is_(True), IndustryBenchmark.topic_type.in_(("macro", "demographic")))
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "signal_type": "industry_benchmark",
                "strength": 0.45,
                "confidence": "medium",
                "benchmark_slug": row.slug,
                "title": row.title,
                "recommendation": (
                    f"Industry prior ({row.source_label or 'IIU'}): {row.summary} "
                    f"— cross-check against TBCC first-party signals before scheduling shifts."
                ),
            }
        )
    return out[:4]
