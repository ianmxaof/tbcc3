"""Tests for creative RAG search."""

from __future__ import annotations

from app.models.creative_catalog import CreativeCatalogEntry
from app.services.creative_rag import search_creative


def test_search_creative_by_query(db):
    row = CreativeCatalogEntry(
        entry_type="image_prompt",
        campaign="jackal_tapes",
        catalog_key="jackal_tapes_interview",
        title="Jackal Interview",
        body="war noir betacam interview scene",
        is_active=True,
    )
    db.add(row)
    db.commit()
    hits = search_creative(db, entry_type="image_prompt", query="betacam interview", limit=3)
    assert len(hits) == 1
    assert hits[0].catalog_key == "jackal_tapes_interview"
