"""Textual TUI over the local LLM model index (scripts/llm_tui.py). Uses
Textual's headless run_test() Pilot — no real terminal needed. Requires
`textual` (tbcc/backend/requirements-dev.txt); skipped if not installed,
same as the CLI's own lazy-import fallback."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing

import pytest

pytest.importorskip("textual")

from app.services import llm_model_index as idx
from scripts.llm_tui import LlmModelIndexApp, _fmt_row


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "tui_test.sqlite3"))


def _seed_one_model():
    with closing(idx._connect()) as conn:
        conn.execute(
            "INSERT INTO models (provider, model_id, raw_json, stale, fetched_at) VALUES (?, ?, ?, 0, ?)",
            ("openrouter", "some/model", json.dumps({"context_length": 32000, "owned_by": "some-org"}), idx._now_iso()),
        )
        idx._upsert_provider_state(conn, "openrouter", usage_remaining=12.5, usage_limit=100.0)
        conn.commit()


def test_fmt_row_handles_missing_metadata():
    row = {
        "provider": "mistral", "model_id": "codestral", "context_length": None,
        "owned_by": None, "stale": False, "exhausted": False,
        "usage_remaining": None, "usage_limit": None, "fetched_at": "2026-08-21T00:00:00+00:00",
    }
    out = _fmt_row(row)
    assert out[0] == "mistral"
    assert out[2] == "—"
    assert out[6] == "—"


def test_fmt_row_shows_usage_and_context():
    row = {
        "provider": "openrouter", "model_id": "some/model", "context_length": 32000,
        "owned_by": "some-org", "stale": True, "exhausted": True,
        "usage_remaining": 12.5, "usage_limit": 100.0, "fetched_at": "2026-08-21T00:00:00+00:00",
    }
    out = _fmt_row(row)
    assert "32,000" in out
    assert "12.50 / 100.00" in out
    assert "yes" in out  # stale
    assert out.count("yes") == 2  # stale + exhausted


def test_app_mount_populates_table_from_index():
    _seed_one_model()

    async def _run():
        app = LlmModelIndexApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table")
            assert table.row_count == 1

    asyncio.run(_run())


def test_action_advance_sets_sticky(monkeypatch):
    from app.services.llm_completions import TextLlmRuntime

    monkeypatch.setattr(
        idx, "resolve_text_llm_runtime",
        lambda provider, model=None: TextLlmRuntime(provider=provider, api_key="k", model=model or "x"),
    )
    idx.set_sticky("zlm", None)

    async def _run():
        app = LlmModelIndexApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_advance()
            await pilot.pause()

    asyncio.run(_run())
    sticky = idx.get_sticky()
    assert sticky is not None
    assert sticky["provider"] != "zlm"
