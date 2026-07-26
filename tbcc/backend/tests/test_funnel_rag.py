"""Funnel strategy RAG seed + search."""

from app.database.session import SessionLocal, engine
from app.models.base import Base
from app.models.funnel_strategy import FunnelStrategyEntry
from app.services.funnel_rag import build_funnel_context, search_funnel_strategies, seed_default_funnel_strategies


def test_seed_default_funnel_strategies_idempotent():
    Base.metadata.create_all(engine, tables=[FunnelStrategyEntry.__table__])
    db = SessionLocal()
    try:
        n1 = seed_default_funnel_strategies(db)
        n2 = seed_default_funnel_strategies(db)
        assert n1 >= 5
        assert n2 == 0
        rows = search_funnel_strategies(db, surface="mainhub", limit=5)
        assert len(rows) >= 2
        ctx = build_funnel_context(db, surface="mainhub", goal="pin liveness")
        assert "Funnel playbook" in ctx or ctx == ""
    finally:
        db.close()
