"""Sales-strategy coach suffix for secretary drafts (FAQ RAG + funnel DM playbook)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.services.funnel_rag import search_funnel_strategies
from app.services.secretary_rag import search_knowledge
from app.services.secretary_settings_effective import get_effective_secretary_settings

SALES_TAG = "sales_strategy"


def _tag_has_sales(tags: str | None) -> bool:
    return SALES_TAG in (tags or "").lower().replace(" ", "_")


def search_sales_knowledge(
    query: str,
    *,
    db: Session | None = None,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """Prefer knowledge rows tagged sales_strategy; fall back to general RAG hits."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        eff = get_effective_secretary_settings(db)
        if not eff.get("rag_enabled"):
            # Still allow tagged sales rows even if general RAG is off — coach is intentional.
            rows = (
                db.query(SecretaryKnowledgeEntry)
                .filter(SecretaryKnowledgeEntry.is_active.is_(True))
                .order_by(SecretaryKnowledgeEntry.id.desc())
                .limit(80)
                .all()
            )
            tagged = [r for r in rows if _tag_has_sales(r.tags)]
            out: list[dict[str, Any]] = []
            q = (query or "").lower()
            for row in tagged:
                hay = f"{row.title or ''} {row.body or ''} {row.tags or ''}".lower()
                score = 1.0 if any(t in hay for t in q.split() if len(t) > 2) else 0.5
                out.append(
                    {
                        "id": row.id,
                        "title": row.title,
                        "body": row.body,
                        "tags": row.tags,
                        "score": score,
                    }
                )
            out.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
            return out[:top_k]

        hits = search_knowledge(query, db=db, top_k=max(top_k * 3, 8))
        tagged = [h for h in hits if _tag_has_sales(h.get("tags"))]
        if tagged:
            return tagged[:top_k]
        # Boost: scan all tagged rows if general search missed them
        rows = (
            db.query(SecretaryKnowledgeEntry)
            .filter(SecretaryKnowledgeEntry.is_active.is_(True))
            .order_by(SecretaryKnowledgeEntry.id.desc())
            .limit(100)
            .all()
        )
        tagged_rows = [r for r in rows if _tag_has_sales(r.tags)]
        if not tagged_rows:
            return hits[:top_k]
        out = [
            {
                "id": r.id,
                "title": r.title,
                "body": r.body,
                "tags": r.tags,
                "score": 1.0,
            }
            for r in tagged_rows[:top_k]
        ]
        return out
    finally:
        if own_db and db is not None:
            db.close()


def build_sales_coach_suffix(
    user_text: str,
    *,
    db: Session | None = None,
    top_k: int = 3,
) -> tuple[str, str]:
    """
    Build LLM system suffix + one-line coach hint for draft cards.

    Returns (suffix, coach_hint_title).
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        sales_hits = search_sales_knowledge(user_text, db=db, top_k=top_k)
        funnel_rows = search_funnel_strategies(
            db, surface="dm", query=user_text, limit=top_k
        )
        hint = ""
        if sales_hits:
            hint = str(sales_hits[0].get("title") or "sales playbook").strip()
        elif funnel_rows:
            hint = str(funnel_rows[0].title or funnel_rows[0].pattern or "dm funnel").strip()

        if not sales_hits and not funnel_rows:
            return "", ""

        lines = [
            "--- Sales coach (strategy; guide toward checkout, never invent prices) ---",
            "Steer gently to the payment bot for /subscribe /packs /shop. No fake scarcity or impersonation.",
        ]
        for i, h in enumerate(sales_hits, 1):
            title = (h.get("title") or "Play").strip()
            body = (h.get("body") or "").strip()[:900]
            lines.append(f"[S{i}] {title}\n{body}")
        for i, row in enumerate(funnel_rows, 1):
            title = (row.title or row.pattern or "funnel").strip()
            copy = (row.copy_template or "").strip()[:500]
            notes = (row.visual_notes or "").strip()[:300]
            lines.append(f"[F{i}] {title}" + (f"\n{copy}" if copy else "") + (f"\n{notes}" if notes else ""))
        lines.append("--- end Sales coach ---")
        return "\n".join(lines), hint
    finally:
        if own_db and db is not None:
            db.close()
