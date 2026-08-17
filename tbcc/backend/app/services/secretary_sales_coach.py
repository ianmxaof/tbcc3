"""Sales-strategy coach suffix for secretary drafts (FAQ RAG + funnel DM playbook)."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.services.funnel_rag import search_funnel_strategies
from app.services.secretary_rag import search_knowledge
from app.services.secretary_settings_effective import get_effective_secretary_settings

SALES_TAG = "sales_strategy"
COACH_MIN_SCORE = float(os.getenv("TBCC_SECRETARY_COACH_MIN_SCORE", "0.55"))
COACH_MAX_CHARS = int(os.getenv("TBCC_SECRETARY_COACH_MAX_CHARS", "600"))


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
            strong = [x for x in out if float(x.get("score") or 0) >= 1.0]
            return (strong or out)[:top_k]

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
        q = (query or "").lower()
        tokens = [t for t in q.split() if len(t) > 2]
        scored: list[dict[str, Any]] = []
        for r in tagged_rows:
            hay = f"{r.title or ''} {r.body or ''} {r.tags or ''}".lower()
            if not tokens or not any(t in hay for t in tokens):
                continue
            scored.append(
                {
                    "id": r.id,
                    "title": r.title,
                    "body": r.body,
                    "tags": r.tags,
                    "score": 1.0,
                }
            )
        return scored[:top_k]
    finally:
        if own_db and db is not None:
            db.close()


def _phase_allowed_coach_titles(phase: str | None) -> set[str] | None:
    """Title allow-list for the sales-coach suffix (Gap G9). None = no title filter."""
    key = (phase or "").strip().lower()
    if key == "introduction":
        return {"soft open", "price objection"}
    if key in ("engagement", ""):
        return None
    if key == "support":
        return {"recovery", "vip vs packs"}
    if key == "recovery":
        return {"recovery", "silence bump", "compare tiers"}
    return None


def _coach_title_allowed(title: str, allowed: set[str]) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return False
    for raw in allowed:
        key = (raw or "").strip().lower()
        if key and (t == key or key in t):
            return True
    return False


def _candidate_block(kind: str, index: int, title: str, body: str) -> str:
    head = f"[{kind}{index}] {(title or 'Play').strip()}"
    text = (body or "").strip()
    return f"{head}\n{text}" if text else head


def build_sales_coach_suffix(
    user_text: str,
    *,
    db: Session | None = None,
    top_k: int = 3,
    current_phase: str | None = None,
) -> tuple[str, str]:
    """
    Build LLM system suffix + one-line coach hint for draft cards.

    Returns (suffix, coach_hint_title). Empty strings match the noise early-return.
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        from app.services.secretary_intent import classify_intent

        if classify_intent(user_text) == "noise":
            return "", ""
        sales_hits = search_sales_knowledge(user_text, db=db, top_k=top_k)
        funnel_rows = search_funnel_strategies(
            db, surface="dm", query=user_text, limit=top_k
        )

        candidates: list[dict[str, Any]] = []
        for h in sales_hits or []:
            try:
                score = float(h.get("score") or 0)
            except (TypeError, ValueError):
                score = 0.0
            if score < COACH_MIN_SCORE:
                continue
            candidates.append(
                {
                    "kind": "S",
                    "title": str(h.get("title") or "").strip(),
                    "body": str(h.get("body") or "").strip(),
                    "score": score,
                }
            )
        for row in funnel_rows or []:
            title = str(getattr(row, "title", None) or getattr(row, "pattern", None) or "funnel").strip()
            copy = str(getattr(row, "copy_template", None) or "").strip()
            notes = str(getattr(row, "visual_notes", None) or "").strip()
            body = "\n".join(p for p in (copy, notes) if p)
            candidates.append({"kind": "F", "title": title, "body": body, "score": 1.0})

        if not candidates:
            return "", ""

        allowed = _phase_allowed_coach_titles(current_phase)
        if allowed is not None:
            candidates = [c for c in candidates if _coach_title_allowed(str(c.get("title") or ""), allowed)]
        if not candidates:
            return "", ""

        candidates.sort(key=lambda c: float(c.get("score") or 0), reverse=True)

        def _blocks_for(rows: list[dict[str, Any]]) -> list[str]:
            out: list[str] = []
            s_i = f_i = 0
            for row in rows:
                if row.get("kind") == "F":
                    f_i += 1
                    idx, kind = f_i, "F"
                else:
                    s_i += 1
                    idx, kind = s_i, "S"
                out.append(_candidate_block(kind, idx, str(row.get("title") or ""), str(row.get("body") or "")))
            return out

        blocks = _blocks_for(candidates)
        assembled = "\n".join(blocks)
        if len(assembled) > COACH_MAX_CHARS:
            top = dict(candidates[0])
            top["body"] = str(top.get("body") or "")[:COACH_MAX_CHARS]
            candidates = [top]
            blocks = _blocks_for(candidates)

        hint = str(candidates[0].get("title") or "sales playbook").strip()
        lines = [
            "--- Sales coach (strategy; guide toward checkout, never invent prices) ---",
            "Steer gently to the payment bot for /subscribe /packs /shop. No fake scarcity or impersonation.",
            *blocks,
            "--- end Sales coach ---",
        ]
        return "\n".join(lines), hint
    finally:
        if own_db and db is not None:
            db.close()
