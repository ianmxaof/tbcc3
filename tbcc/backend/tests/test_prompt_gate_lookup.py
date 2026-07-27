"""prompt_gate registry lookup + body hash helpers."""

from __future__ import annotations

from app.database.session import SessionLocal, engine
from app.models.base import Base
from app.models.prompt_gate import (
    PROMPT_GATE_STATUS_PROVISIONED,
    PROMPT_GATE_STATUS_SUPERSEDED,
    PromptGate,
)
from app.services.prompt_gate_lookup import (
    active_prompt_gate_row,
    hash_prompt_body,
    normalize_prompt_body,
    prompt_gate_url,
)


def _ensure_table() -> None:
    PromptGate.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine, tables=[PromptGate.__table__])


def test_normalize_prompt_body_collapses_whitespace() -> None:
    raw = "  line one  \r\n\r\n  line two \n\n\nline three  "
    assert normalize_prompt_body(raw) == "line one\n\nline two\n\nline three"


def test_hash_prompt_body_stable_across_whitespace() -> None:
    a = "CENTER: goblin\n\nNEGATIVE: no text"
    b = "  CENTER: goblin  \n\n  NEGATIVE: no text  "
    assert hash_prompt_body(a) == hash_prompt_body(b)


def test_prompt_gate_url_returns_none_when_missing() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        assert prompt_gate_url("missing_key", db=db) is None
    finally:
        db.close()


def test_prompt_gate_url_returns_latest_provisioned() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        old = PromptGate(
            key="goblin_boombox_v1",
            body_hash="abc",
            lv_url="https://link-center.net/1367336/oldSlug",
            status=PROMPT_GATE_STATUS_SUPERSEDED,
        )
        current = PromptGate(
            key="goblin_boombox_v1",
            body_hash="def",
            lv_url="https://link-center.net/1367336/newSlug",
            status=PROMPT_GATE_STATUS_PROVISIONED,
        )
        db.add_all([old, current])
        db.commit()

        row = active_prompt_gate_row(db, "goblin_boombox_v1")
        assert row is not None
        assert row.lv_url.endswith("newSlug")

        assert prompt_gate_url("goblin_boombox_v1", db=db) == "https://link-center.net/1367336/newSlug"
        assert prompt_gate_url("GOBLIN_BOOMBOX_V1", db=db) == "https://link-center.net/1367336/newSlug"
    finally:
        db.close()
