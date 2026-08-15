"""DB-backed secretary Pilot draft queue — persistence, redo suffix, suggest-mode history.

Covers blueprint gaps G5 (redo strips FE/coach/RAG), G6 (Pilot ignores FE DB history), and
G8 (drafts are RAM-only, lost on restart) from tbcc/docs/SECRETARY_SYSTEM_BLUEPRINT.md.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.secretary_pending_draft import SecretaryPendingDraft
from app.services.secretary_drafts import (
    build_redo_suffix,
    count_drafts,
    delete_draft,
    get_draft,
    list_drafts,
    save_draft,
    suggest_customer_lines,
    update_draft_reply,
)
from app.services.secretary_llm import REDO_STYLE_HINTS, complete_secretary_chat

STORED_SUFFIX = "FE context: phase=engagement. Sales coach: ladder VIP vs packs."


def _draft_kwargs(**overrides):
    base = dict(
        draft_id="ABC123",
        chat_id=555,
        business_connection_id="bc_1",
        user_id=9_003_001,
        who="lead_user",
        customer_preview="hi, how much is VIP?",
        reply="VIP is 500 Stars for 30 days.",
        llm_messages=[
            {"role": "system", "content": "base system prompt"},
            {"role": "user", "content": "hi, how much is VIP?"},
        ],
        extra_system_suffix=STORED_SUFFIX,
        coach_hint="VIP vs packs ladder",
        reply_mode="pilot",
    )
    base.update(overrides)
    return base


# --- 1. Draft round-trip: save -> new session -> load still has extra_system_suffix ---


def test_draft_round_trip_survives_new_session(db):
    """New sessionmaker bound to the same engine simulates a fresh process picking the row
    back up after restart — proves the DB (not the dict) is now the source of truth."""
    save_draft(db, **_draft_kwargs())

    Session2 = sessionmaker(bind=db.get_bind())
    fresh = Session2()
    try:
        loaded = get_draft(fresh, "ABC123")
    finally:
        fresh.close()

    assert loaded is not None
    assert loaded["extra_system_suffix"] == STORED_SUFFIX
    assert loaded["llm_messages"] == [
        {"role": "system", "content": "base system prompt"},
        {"role": "user", "content": "hi, how much is VIP?"},
    ]
    assert loaded["coach_hint"] == "VIP vs packs ladder"
    assert loaded["reply"] == "VIP is 500 Stars for 30 days."


def test_update_draft_reply_keeps_suffix_and_messages(db):
    save_draft(db, **_draft_kwargs())
    updated = update_draft_reply(db, "ABC123", "New casual reply text.")
    assert updated is not None
    assert updated["reply"] == "New casual reply text."
    assert updated["extra_system_suffix"] == STORED_SUFFIX
    assert len(updated["llm_messages"]) == 2


def test_update_draft_reply_missing_draft_returns_none(db):
    assert update_draft_reply(db, "NOPE00", "text") is None


def test_delete_and_list_drafts(db):
    save_draft(db, **_draft_kwargs(draft_id="AAA111"))
    save_draft(db, **_draft_kwargs(draft_id="BBB222"))

    items = list_drafts(db)
    ids = {i["draft_id"] for i in items}
    assert {"AAA111", "BBB222"} <= ids
    assert count_drafts(db) >= 2

    assert delete_draft(db, "AAA111") is True
    assert get_draft(db, "AAA111") is None
    assert delete_draft(db, "AAA111") is False


def test_ttl_prunes_expired_rows_on_read(db):
    save_draft(db, **_draft_kwargs(draft_id="OLD001"))
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == "OLD001").one()
    row.created_at = datetime.utcnow() - timedelta(hours=49)
    db.commit()

    assert get_draft(db, "OLD001") is None


# --- 2. Redo helper uses stored extra_system_suffix + style hint (never style-only) ---


def test_build_redo_suffix_keeps_stored_context_casual():
    suffix = build_redo_suffix(STORED_SUFFIX, "casual")
    assert STORED_SUFFIX in suffix
    assert REDO_STYLE_HINTS["casual"] in suffix


@pytest.mark.parametrize("style", ["pro", "short"])
def test_build_redo_suffix_keeps_stored_context_other_styles(style):
    suffix = build_redo_suffix(STORED_SUFFIX, style)
    assert STORED_SUFFIX in suffix
    assert REDO_STYLE_HINTS[style] in suffix


def test_build_redo_suffix_custom_instruction():
    suffix = build_redo_suffix(STORED_SUFFIX, "custom", "mention the loyalty discount")
    assert STORED_SUFFIX in suffix
    assert "mention the loyalty discount" in suffix


def test_build_redo_suffix_unknown_style_falls_back_to_pro():
    suffix = build_redo_suffix(STORED_SUFFIX, "not_a_real_style")
    assert REDO_STYLE_HINTS["pro"] in suffix


def test_build_redo_suffix_without_stored_context_still_asks_json_triad():
    suffix = build_redo_suffix("", "casual")
    assert REDO_STYLE_HINTS["casual"] in suffix
    from app.services.secretary_drafts import TRIAGE_JSON_INSTRUCTION

    assert TRIAGE_JSON_INSTRUCTION in suffix


def test_redo_suffix_reaches_llm_system_message(monkeypatch):
    """Mock the LLM call and assert the system message the model actually sees carries both
    the original FE/coach suffix and the tone hint — the concrete fix for blueprint gap G5.

    No pytest-asyncio plugin is installed in this repo (see test_companion_access.py, which
    has the same pre-existing gap) — drive the coroutine with asyncio.run() instead.
    """
    captured: dict = {}

    async def fake_complete_chat_text_async(messages, **kwargs):
        captured["messages"] = messages
        return "rewritten reply"

    monkeypatch.setattr(
        "app.services.llm_completions.complete_chat_text_async",
        fake_complete_chat_text_async,
    )
    monkeypatch.setattr(
        "app.services.secretary_llm_config.resolve_secretary_text_llm_runtime",
        lambda: object(),
    )

    llm_messages = [
        {"role": "system", "content": "base system prompt"},
        {"role": "user", "content": "still mad about my order"},
    ]
    suffix = build_redo_suffix(STORED_SUFFIX, "casual")
    reply = asyncio.run(complete_secretary_chat(llm_messages, extra_system_suffix=suffix))

    assert reply == "rewritten reply"
    sent_system = captured["messages"][0]["content"]
    assert STORED_SUFFIX in sent_system
    assert REDO_STYLE_HINTS["casual"] in sent_system


# --- 3. Suggest-mode history builder prefers FE DB user messages when memory empty ---


def test_suggest_customer_lines_prefers_live_memory_when_present():
    prev_lines = ["hi", "how much for VIP"]
    db_history = [{"role": "user", "content": "a completely different DB line"}]
    assert suggest_customer_lines(prev_lines, db_history) == prev_lines


def test_suggest_customer_lines_falls_back_to_db_when_memory_empty():
    db_history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey, what can I help with?"},
        {"role": "user", "content": "how much for VIP"},
    ]
    assert suggest_customer_lines([], db_history) == ["hi", "how much for VIP"]


def test_suggest_customer_lines_empty_both():
    assert suggest_customer_lines([], []) == []


def test_clamp_and_parse_triage_json():
    from app.services.secretary_drafts import clamp_candidate, parse_triage_candidates, pick_candidate

    long = "First sentence. Second sentence. Third should drop."
    assert clamp_candidate(long) == "First sentence. Second sentence."
    huge = "A" * 400
    assert len(clamp_candidate(huge)) <= 280

    raw = '{"natural":"hey what are you looking for?","clear":"VIP is in the payment bot.","close":"Open the payment bot and tap /subscribe."}'
    cands = parse_triage_candidates(raw)
    assert cands["natural"].startswith("hey")
    assert "payment bot" in cands["clear"]
    item = {"reply": cands["natural"], "candidates": cands}
    assert pick_candidate(item, "x") == cands["close"]
    assert pick_candidate(item, "n") == cands["natural"]


def test_save_draft_persists_candidates(db):
    from app.services.secretary_drafts import parse_triage_candidates

    cands = parse_triage_candidates(
        '{"natural":"hey","clear":"facts here.","close":"tap /subscribe in the payment bot."}'
    )
    save_draft(db, **_draft_kwargs(candidates=cands, reply=cands["natural"]))
    loaded = get_draft(db, "ABC123")
    assert loaded is not None
    assert loaded["candidates"]["close"].startswith("tap")
