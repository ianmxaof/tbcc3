"""Gap G11 — operator Telegram Business messages as silent FE assistant turns."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext
from app.services.format_engine import (
    _default_format,
    _load_format,
    _save_format,
    record_external_assistant_turn,
)


def test_record_external_assistant_turn_increments_and_stores(db, monkeypatch):
    monkeypatch.setattr("app.services.format_engine.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    fmt = _default_format()
    fmt["phase"] = "engagement"
    ctx = SecretaryUserContext(
        telegram_user_id=7_011_001,
        telegram_username="biz_customer",
        current_phase="engagement",
        interaction_format_json=_save_format(fmt),
    )
    db.add(ctx)
    db.commit()

    before_emotions = list(fmt.get("dominant_emotions") or [])
    before_triggers = list(fmt.get("observed_triggers") or [])
    record_external_assistant_turn(7_011_001, "I'll take this thread.", "bc_abc")

    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == 7_011_001).one()
    loaded = _load_format(row.interaction_format_json)
    assert loaded["metrics"]["assistant_messages"] == 1
    assert row.last_assistant_at is not None
    assert (datetime.utcnow() - row.last_assistant_at).total_seconds() < 10
    assert row.current_phase == "engagement"
    assert loaded["phase"] == "engagement"
    assert loaded.get("last_intent") is None
    assert loaded.get("dominant_emotions") == before_emotions
    assert loaded.get("observed_triggers") == before_triggers

    history = loaded.get("phase_history") or []
    assert history
    assert history[-1]["marker"] == "manual_assistant"
    assert history[-1]["phase"] == "engagement"
    assert history[-1].get("ts")
    assert loaded["interaction_guidelines"].get("operator_intervened_at")

    recs = db.query(SecretaryMessageRecord).filter(SecretaryMessageRecord.context_id == row.id).all()
    assert len(recs) == 1
    assert recs[0].role == "assistant"
    assert recs[0].content == "I'll take this thread."
    assert recs[0].emotion_json is None


def test_handler_skips_customer_and_echo(monkeypatch):
    from bots import secretary_bot as sb

    called: list[tuple] = []

    def _fake_record(uid, text, bc=None):
        called.append((uid, text, bc))

    monkeypatch.setattr(sb, "record_external_assistant_turn", _fake_record)
    monkeypatch.setattr(sb, "_schedule_format_live", lambda *a, **k: None)
    sb._sent_business_msg_ids.clear()

    async def _run():
        customer = SimpleNamespace(id=111)
        inbound = SimpleNamespace(
            business_connection_id="bc1",
            from_user=customer,
            text="hi from customer",
            chat_id=111,
            message_id=1,
        )
        await sb.on_business_outbound(
            SimpleNamespace(message=inbound, business_message=None),
            MagicMock(),
        )
        assert called == []

        sb._sent_business_msg_ids[99] = time.time()
        operator = SimpleNamespace(id=222)
        echo = SimpleNamespace(
            business_connection_id="bc1",
            from_user=operator,
            text="bot draft echo",
            chat_id=111,
            message_id=99,
        )
        await sb.on_business_outbound(
            SimpleNamespace(message=echo, business_message=None),
            MagicMock(),
        )
        assert 99 not in sb._sent_business_msg_ids
        assert called == []

        outbound = SimpleNamespace(
            business_connection_id="bc1",
            from_user=operator,
            text="I'll handle this",
            chat_id=111,
            message_id=100,
        )
        await sb.on_business_outbound(
            SimpleNamespace(message=outbound, business_message=None),
            MagicMock(),
        )
        assert called == [(111, "I'll handle this", "bc1")]

    asyncio.run(_run())
