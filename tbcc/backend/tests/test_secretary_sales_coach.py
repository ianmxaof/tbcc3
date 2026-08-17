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
    hits = search_sales_knowledge("this VIP price is too expensive", db=db, top_k=3)
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


def _mock_hits(*rows: dict) -> list[dict]:
    return [dict(r) for r in rows]


def test_no_coach_when_below_threshold(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_sales_knowledge",
        lambda *a, **k: _mock_hits(
            {"title": "soft open", "body": "hi", "score": 0.4, "tags": "sales_strategy"},
            {"title": "recovery", "body": "later", "score": 0.2, "tags": "sales_strategy"},
        ),
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_funnel_strategies",
        lambda *a, **k: [],
    )
    suffix, hint = build_sales_coach_suffix("how much is VIP", db=db, current_phase="engagement")
    assert suffix == ""
    assert hint == ""


def test_phase_introduction_filters_titles(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_sales_knowledge",
        lambda *a, **k: _mock_hits(
            {"title": "soft open", "body": "qualify interest first", "score": 0.9, "tags": "sales_strategy"},
            {"title": "VIP vs packs", "body": "ladder dump", "score": 0.88, "tags": "sales_strategy"},
            {"title": "silence bump", "body": "follow up", "score": 0.8, "tags": "sales_strategy"},
        ),
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_funnel_strategies",
        lambda *a, **k: [],
    )
    suffix, hint = build_sales_coach_suffix("hey what is this about VIP", db=db, current_phase="introduction")
    assert suffix
    assert "qualify interest first" in suffix
    assert "soft open" in suffix.lower()
    assert "ladder dump" not in suffix
    assert "follow up" not in suffix
    assert "VIP vs packs" not in suffix
    assert "silence bump" not in suffix
    assert hint.lower() == "soft open"


def test_phase_recovery_filters_titles(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_sales_knowledge",
        lambda *a, **k: _mock_hits(
            {"title": "recovery", "body": "ack frustration", "score": 0.91, "tags": "sales_strategy"},
            {"title": "silence bump", "body": "one short bump", "score": 0.8, "tags": "sales_strategy"},
            {"title": "soft open", "body": "greet and qualify", "score": 0.79, "tags": "sales_strategy"},
            {"title": "compare tiers", "body": "high level diffs", "score": 0.7, "tags": "sales_strategy"},
        ),
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_funnel_strategies",
        lambda *a, **k: [],
    )
    suffix, _hint = build_sales_coach_suffix("I am still waiting for VIP access", db=db, current_phase="recovery")
    assert suffix
    assert "ack frustration" in suffix
    assert "one short bump" in suffix
    assert "high level diffs" in suffix
    assert "greet and qualify" not in suffix
    assert "soft open" not in suffix.lower()


def test_engagement_keeps_all_titles(db, monkeypatch):
    rows = _mock_hits(
        {"title": "soft open", "body": "open body", "score": 0.9, "tags": "sales_strategy"},
        {"title": "VIP vs packs", "body": "ladder body", "score": 0.85, "tags": "sales_strategy"},
        {"title": "silence bump", "body": "bump body", "score": 0.8, "tags": "sales_strategy"},
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_sales_knowledge",
        lambda *a, **k: rows,
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_funnel_strategies",
        lambda *a, **k: [],
    )
    for phase in ("engagement", None):
        suffix, _hint = build_sales_coach_suffix("how much is VIP", db=db, current_phase=phase)
        assert "open body" in suffix
        assert "ladder body" in suffix
        assert "bump body" in suffix


def test_max_chars_truncates_to_top_row(db, monkeypatch):
    import app.services.secretary_sales_coach as coach

    monkeypatch.setattr(coach, "COACH_MAX_CHARS", 80)
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_sales_knowledge",
        lambda *a, **k: _mock_hits(
            {"title": "alpha play", "body": "A" * 400, "score": 0.99, "tags": "sales_strategy"},
            {"title": "beta play", "body": "B" * 400, "score": 0.9, "tags": "sales_strategy"},
        ),
    )
    monkeypatch.setattr(
        "app.services.secretary_sales_coach.search_funnel_strategies",
        lambda *a, **k: [],
    )
    suffix, hint = build_sales_coach_suffix("I want to join", db=db, current_phase="engagement")
    assert "alpha play" in suffix
    assert hint == "alpha play"
    assert "beta play" not in suffix
    assert "B" not in suffix
    assert "A" * 80 in suffix
    assert "A" * 81 not in suffix
