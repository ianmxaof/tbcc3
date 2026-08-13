"""Sales coach suffix + playbook tag retrieval."""

from __future__ import annotations

from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.services.secretary_sales_coach import build_sales_coach_suffix, search_sales_knowledge


def test_search_sales_knowledge_prefers_tagged(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_RAG_ENABLED", "1")
    db.add(
        SecretaryKnowledgeEntry(
            title="Price objection — value then ladder",
            body="Acknowledge price, offer pack trial, send to payment bot.",
            tags="sales_strategy,objection,price",
            source_path="seed:sales_playbook",
            is_active=True,
        )
    )
    db.add(
        SecretaryKnowledgeEntry(
            title="Unrelated FAQ",
            body="How do channel invites work in general.",
            tags="faq,access",
            source_path="seed:other",
            is_active=True,
        )
    )
    db.commit()

    # Force rag_enabled via settings effective may read DB — seed path still works
    hits = search_sales_knowledge("too expensive for VIP", db=db, top_k=3)
    assert hits
    assert any("sales_strategy" in (h.get("tags") or "") for h in hits)
    assert any("Price" in (h.get("title") or "") for h in hits)


def test_build_sales_coach_suffix_includes_playbook(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_RAG_ENABLED", "0")
    db.add(
        SecretaryKnowledgeEntry(
            title="Ready to buy — handoff to payment bot",
            body="Give payment bot username and /subscribe.",
            tags="sales_strategy,close,checkout",
            source_path="seed:sales_playbook",
            is_active=True,
        )
    )
    db.commit()
    suffix, hint = build_sales_coach_suffix("I want to buy now", db=db)
    assert "Sales coach" in suffix
    assert "Ready to buy" in suffix or "Ready to buy" in hint
    assert hint
