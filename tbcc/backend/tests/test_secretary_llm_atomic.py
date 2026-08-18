"""Sequential-call Pilot triad (complete_secretary_chat_atomic) — order, precedent
chaining, and that a mid-chain failure propagates so the caller can fall back to the
single-blob JSON path (secretary_bot.py wires that fallback; TBCC_SECRETARY_PILOT_ATOMIC_LLM
gates which path runs)."""

from __future__ import annotations

import asyncio

import pytest

from app.models.secretary_settings import SecretarySettings  # noqa: F401 — registers table for `db` fixture
from app.services.secretary_llm import complete_secretary_chat_atomic
from app.services.secretary_settings_effective import get_effective_secretary_settings


def test_atomic_chain_runs_natural_clear_close_in_order(monkeypatch):
    calls: list[dict] = []

    async def fake_complete(messages, *, extra_system_suffix="", max_tokens_override=None):
        calls.append({"extra_system_suffix": extra_system_suffix, "max_tokens_override": max_tokens_override})
        return ["hey what's up", "It's 500 Stars for 30 days.", "Grab it in the payment bot when ready."][
            len(calls) - 1
        ]

    monkeypatch.setattr("app.services.secretary_llm.complete_secretary_chat", fake_complete)

    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "how much is VIP?"},
    ]
    result = asyncio.run(complete_secretary_chat_atomic(messages, extra_system_suffix="FE context"))

    assert len(calls) == 3
    assert result == {
        "natural": "hey what's up",
        "clear": "It's 500 Stars for 30 days.",
        "close": "Grab it in the payment bot when ready.",
    }

    assert calls[0]["max_tokens_override"] == 120
    assert "Reply casually. 1 sentence. No price." in calls[0]["extra_system_suffix"]
    assert "FE context" in calls[0]["extra_system_suffix"]
    assert "Earlier draft" not in calls[0]["extra_system_suffix"]

    assert calls[1]["max_tokens_override"] == 80
    assert "hey what's up" in calls[1]["extra_system_suffix"]
    assert "Reply directly and helpful. 1-2 sentences." in calls[1]["extra_system_suffix"]

    assert calls[2]["max_tokens_override"] == 60
    assert "hey what's up" in calls[2]["extra_system_suffix"]
    assert "It's 500 Stars for 30 days." in calls[2]["extra_system_suffix"]
    assert "Steer to payment bot for checkout. 1 sentence." in calls[2]["extra_system_suffix"]


def test_atomic_chain_stops_and_raises_on_mid_chain_failure(monkeypatch):
    calls: list[int] = []

    async def fake_complete(messages, *, extra_system_suffix="", max_tokens_override=None):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("provider down")
        return "ok"

    monkeypatch.setattr("app.services.secretary_llm.complete_secretary_chat", fake_complete)

    with pytest.raises(RuntimeError, match="provider down"):
        asyncio.run(complete_secretary_chat_atomic([{"role": "user", "content": "hi"}]))

    # natural (1) ran, clear (2) raised — close never ran, and the exception
    # propagates uncaught so the caller (secretary_bot.py) can fall back.
    assert len(calls) == 2


def test_atomic_disabled_by_default(db, monkeypatch):
    monkeypatch.delenv("TBCC_SECRETARY_PILOT_ATOMIC_LLM", raising=False)
    eff = get_effective_secretary_settings(db)
    assert eff["pilot_atomic_llm"] is False


def test_atomic_flag_reads_env_true(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_PILOT_ATOMIC_LLM", "1")
    eff = get_effective_secretary_settings(db)
    assert eff["pilot_atomic_llm"] is True
