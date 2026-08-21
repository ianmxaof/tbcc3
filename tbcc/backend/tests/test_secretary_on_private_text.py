"""Integration coverage for bots.secretary_bot.on_private_text — the largest, most
mode-sensitive function in the bot (~350 lines: admin/customer x direct/business x
pilot/auto). Every service it calls already has its own unit tests; this handler
itself had none, so a cross-wired mode branch (e.g. a customer reply leaking to the
customer instead of going through the draft queue) could ship silently.

All DB/Telegram/LLM dependencies are monkeypatched at the bots.secretary_bot (or,
where the real code does a function-local import, the source module) level — no
real database, no real network, no real LLM call.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bots import secretary_bot as sb

ADMIN_ID = 900001
CUSTOMER_ID = 700001


def _msg(*, chat_id: int, text: str, business_connection_id: str | None = None, message_id: int = 1):
    return SimpleNamespace(
        chat_id=chat_id,
        chat=SimpleNamespace(type="private"),
        text=text,
        message_id=message_id,
        business_connection_id=business_connection_id,
        reply_text=AsyncMock(),
    )


def _user(uid: int, username: str | None = "customer"):
    return SimpleNamespace(id=uid, username=username)


def _context():
    ctx = MagicMock()
    ctx.bot = AsyncMock()
    ctx.user_data = {}
    return ctx


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """These are plain module-level dicts, not per-Application state (see review) —
    clear them so one test's rate-limit/dedupe hits can't bleed into the next."""
    sb._rate_log.clear()
    sb._business_msg_seen.clear()
    sb._sent_business_msg_ids.clear()
    yield


@pytest.fixture
def base_mocks(monkeypatch):
    """Common deterministic stand-ins shared by every mode-matrix case.

    Matrix tests use "hi" (classify_intent -> noise) so the real intent gate skips
    the catalog-fetch / sales-coach / RAG block entirely -- this test is about
    admin/customer x direct/business x pilot/auto routing, not intent handling
    (already covered by test_secretary_intent.py). fetch_subscription_catalog_snippet
    and build_sales_coach_suffix are still stubbed as a defense-in-depth net so a
    text change can't silently reintroduce a real network/DB call (see: the
    zeus_cohost_spike incident earlier this session).
    """
    monkeypatch.setattr(sb, "_allow_rate_limit", lambda uid: True)
    monkeypatch.setattr(sb, "get_effective_secretary_settings", lambda *a, **k: {"public_faq_enabled": True, "rag_enabled": False, "system_prompt_extra": ""})
    monkeypatch.setattr(sb, "format_engine_enabled", lambda: False)
    monkeypatch.setattr(sb, "secretary_llm_configured", lambda: True)
    monkeypatch.setattr(sb, "corpus_candidates", lambda *a, **k: None)  # force LLM path, not scripted
    monkeypatch.setattr(sb, "_schedule_format_live", lambda *a, **k: None)
    monkeypatch.setattr(sb, "finalize_assistant_turn", MagicMock())
    monkeypatch.setattr(sb, "finalize_assistant_turn_for_user", MagicMock())
    monkeypatch.setattr(sb, "complete_secretary_chat", AsyncMock(return_value="Sure, here's the answer."))
    monkeypatch.setattr(sb, "default_system_prompt", lambda: "You are a person DMing on Telegram for AOF.")
    monkeypatch.setattr(sb, "fetch_subscription_catalog_snippet", AsyncMock(return_value=""))
    monkeypatch.setattr(sb, "build_sales_coach_suffix", AsyncMock(return_value=("", None)))
    monkeypatch.setattr(sb, "_draft_notify_chat_ids", lambda: [ADMIN_ID])
    monkeypatch.setattr(sb, "_save_draft", MagicMock(return_value={}))
    monkeypatch.setattr("app.services.admin_inbox.push_admin_inbox_event", MagicMock())
    return monkeypatch


def _run(update, context):
    asyncio.run(sb.on_private_text(update, context))


# ---------------------------------------------------------------------------
# Cheap guard-clause tests — no LLM/draft mocking needed.
# ---------------------------------------------------------------------------


def test_llm_not_configured_customer_gets_offline_message(monkeypatch):
    monkeypatch.setattr(sb, "_allow_rate_limit", lambda uid: True)
    monkeypatch.setattr(sb, "_can_manage_drafts", lambda update: False)
    monkeypatch.setattr(sb, "get_effective_secretary_settings", lambda *a, **k: {"public_faq_enabled": True})
    monkeypatch.setattr(sb, "secretary_llm_configured", lambda: False)

    msg = _msg(chat_id=CUSTOMER_ID, text="hi")
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_awaited_once()
    assert "offline" in msg.reply_text.await_args.args[0].lower()


def test_public_faq_disabled_blocks_non_admin_direct(monkeypatch):
    monkeypatch.setattr(sb, "_allow_rate_limit", lambda uid: True)
    monkeypatch.setattr(sb, "_can_manage_drafts", lambda update: False)
    monkeypatch.setattr(sb, "get_effective_secretary_settings", lambda *a, **k: {"public_faq_enabled": False})
    monkeypatch.setattr(sb, "_payment_bot_username", lambda: None)

    msg = _msg(chat_id=CUSTOMER_ID, text="hello")
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_awaited_once()
    assert "admin-only" in msg.reply_text.await_args.args[0].lower()


def test_business_message_dedupe_skips_repeat(monkeypatch):
    monkeypatch.setattr(sb, "_can_manage_drafts", lambda update: False)
    bc_id = "bc123"
    sb._already_processed_business_msg(bc_id, CUSTOMER_ID, 42)  # prime the dedupe cache

    msg = _msg(chat_id=CUSTOMER_ID, text="hi again", business_connection_id=bc_id, message_id=42)
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_not_awaited()
    context.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# The core mode matrix: customer/admin x direct/business x pilot/auto.
# ---------------------------------------------------------------------------


def test_customer_direct_pilot_creates_draft_not_direct_reply(base_mocks):
    base_mocks.setattr(sb, "_can_manage_drafts", lambda update: False)
    base_mocks.setattr(sb, "_customer_reply_mode", lambda uid, is_business: "pilot")

    msg = _msg(chat_id=CUSTOMER_ID, text="hi")
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_not_awaited()  # customer must never see it directly
    sb._save_draft.assert_called_once()
    assert sb._save_draft.call_args.kwargs["user_id"] == CUSTOMER_ID
    assert sb._save_draft.call_args.kwargs["business_connection_id"] is None
    context.bot.send_message.assert_awaited()  # admin got the draft card
    assert context.bot.send_message.await_args.kwargs["chat_id"] == ADMIN_ID


def test_customer_direct_auto_sends_reply_directly(base_mocks):
    base_mocks.setattr(sb, "_can_manage_drafts", lambda update: False)
    base_mocks.setattr(sb, "_customer_reply_mode", lambda uid, is_business: "auto")

    msg = _msg(chat_id=CUSTOMER_ID, text="hi")
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_awaited_once()
    assert "Sure, here's the answer." in msg.reply_text.await_args.args[0]
    sb._save_draft.assert_not_called()
    context.bot.send_message.assert_not_awaited()


def test_customer_business_pilot_creates_draft(base_mocks):
    bc_id = "bc_biz_1"
    base_mocks.setattr(sb, "_can_manage_drafts", lambda update: False)
    base_mocks.setattr(sb, "_customer_reply_mode", lambda uid, is_business: "pilot")

    msg = _msg(chat_id=CUSTOMER_ID, text="hi", business_connection_id=bc_id)
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_not_awaited()
    sb._save_draft.assert_called_once()
    assert sb._save_draft.call_args.kwargs["business_connection_id"] == bc_id
    # the only send_message call must be the admin draft card, not a customer send
    assert context.bot.send_message.await_args.kwargs["chat_id"] == ADMIN_ID


def test_customer_business_auto_sends_via_bot_send_message(base_mocks):
    bc_id = "bc_biz_2"
    base_mocks.setattr(sb, "_can_manage_drafts", lambda update: False)
    base_mocks.setattr(sb, "_customer_reply_mode", lambda uid, is_business: "auto")

    msg = _msg(chat_id=CUSTOMER_ID, text="hi", business_connection_id=bc_id)
    user = _user(CUSTOMER_ID)
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_not_awaited()  # business chats must go through bot.send_message
    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == CUSTOMER_ID
    assert kwargs["business_connection_id"] == bc_id
    sb._save_draft.assert_not_called()


def test_admin_direct_message_bypasses_draft_flow_even_in_pilot(base_mocks):
    """Admin chat forces suggest_mode=False regardless of any stored reply_mode —
    the operator's own testing/admin traffic must never get queued as a draft."""
    base_mocks.setattr(sb, "_can_manage_drafts", lambda update: True)
    base_mocks.setattr(sb, "_customer_reply_mode", lambda uid, is_business: "pilot")

    msg = _msg(chat_id=ADMIN_ID, text="hi")
    user = _user(ADMIN_ID, username="operator")
    context = _context()
    _run(SimpleNamespace(effective_message=msg, effective_user=user), context)

    msg.reply_text.assert_awaited_once()
    sb._save_draft.assert_not_called()
