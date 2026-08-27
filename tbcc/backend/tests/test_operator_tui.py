"""Unified operator TUI (scripts/operator_tui.py) — Textual's headless
run_test() Pilot, no real terminal needed. Requires `textual`, same
importorskip as test_llm_tui.py.

Isolation, layered same as the existing pieces this app wraps:
  - LLM index / API slot registry: throwaway sqlite via env-var override
    (same as test_llm_tui.py / test_tools_slots_api.py).
  - .env writes + Credential Manager backup: same monkeypatches as
    test_tools_slots_api.py — a test run must never touch the real .env or
    the real Windows Credential Manager.
  - promo_affiliate_links: `httpx.get`/`httpx.post` are monkeypatched at
    the operator_tui module level — this pane talks to the island's public
    API (revenue-primary data, see REVENUE_ISLAND.md), never a local DB
    connection, so a test run never makes a real network call.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import closing

import httpx
import pytest

pytest.importorskip("textual")

from app.api import tools_slots
from app.services import api_slot_registry as reg
from app.services import llm_model_index as idx
from app.services import tbcc_env_secret_store as secret_store
from textual.widgets import DataTable, Static, TabbedContent

import scripts.operator_tui as tui_mod
from scripts.operator_tui import OperatorTuiApp, TruncatingDataTable, _truncate


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "tui_llm_index.sqlite3"))
    monkeypatch.setenv("TBCC_API_SLOT_DB", str(tmp_path / "tui_api_slots.sqlite3"))
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(secret_store, "env_file_path", lambda: env_file)
    monkeypatch.setattr(tools_slots, "backup_credential_manager", lambda key, value: False)

    # research_scanner_sources.json is a real, git-tracked repo file (not
    # gitignored .tbcc-run state) — point add_source/list_sources at a
    # throwaway copy so a test run never edits it. add_source() splices new
    # entries in via raw text insertion after the last existing "}" (to
    # preserve hand-curated formatting), so it needs at least one seed entry
    # to anchor on — a genuinely empty list isn't a real-world shape (the
    # actual file always has entries) but would raise ValueError here.
    sources_path = tmp_path / "research_scanner_sources.json"
    sources_path.write_text(
        json.dumps({"sources": [{"id": "seed", "url": "https://example.com/seed.xml", "label": "seed", "lane": "dev"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("TBCC_RESEARCH_SCANNER_SOURCES", str(sources_path))

    # Default: affiliate pane sees an empty island list, never hits real network.
    monkeypatch.setattr(tui_mod.httpx, "get", lambda *a, **k: _FakeResponse(200, []))

    return env_file


def _seed_one_model(model_id: str = "some/model", provider: str = "openrouter"):
    with closing(idx._connect()) as conn:
        conn.execute(
            "INSERT INTO models (provider, model_id, raw_json, stale, fetched_at) VALUES (?, ?, ?, 0, ?)",
            (provider, model_id, json.dumps({"context_length": 32000, "owned_by": "some-org"}), idx._now_iso()),
        )
        conn.commit()


def test_mount_builds_all_seven_panes():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            for table_id in ("models-table", "keys-table", "aff-table", "rss-table", "archive-table"):
                assert app.query_one(f"#{table_id}", DataTable) is not None
            assert app.query_one("#ask-prompt", tui_mod.TextArea) is not None

    asyncio.run(_run())


def test_layout_fits_62x28_with_no_outer_scroll():
    """The operator's actual ask: the main layout must never need a
    scrollbar at their launch size. Checked per tab since each pane has
    different content height."""

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test(size=(62, 28)) as pilot:
            await pilot.pause()
            for pane_id in (
                "pane-ask", "pane-models", "pane-keys", "pane-affiliate", "pane-scan", "pane-rss", "pane-archive",
            ):
                app.query_one(TabbedContent).active = pane_id
                await pilot.pause()
                assert app.screen.virtual_size.height <= app.screen.size.height, pane_id
                assert app.screen.virtual_size.width <= app.screen.size.width, pane_id

    asyncio.run(_run())


def test_layout_fits_54x24_with_no_outer_scroll():
    """A smaller target grid than the 62x28 default — the compaction pass
    (banner capped to 4 lines, TabPane padding removed, paste boxes shrunk to
    3 rows) should keep every pane fitting without an outer scroll here too."""

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test(size=(54, 24)) as pilot:
            await pilot.pause()
            for pane_id in (
                "pane-ask", "pane-models", "pane-keys", "pane-affiliate", "pane-scan", "pane-rss", "pane-archive",
            ):
                app.query_one(TabbedContent).active = pane_id
                await pilot.pause()
                assert app.screen.virtual_size.height <= app.screen.size.height, pane_id
                assert app.screen.virtual_size.width <= app.screen.size.width, pane_id

    asyncio.run(_run())


def test_truncate_helper():
    assert _truncate("short", 20) == "short"
    assert _truncate(None, 10) == ""
    assert _truncate("a" * 50, 10) == "a" * 7 + "..."
    assert len(_truncate("a" * 50, 10)) == 10


def test_ask_pane_shows_reply_and_status(monkeypatch):
    monkeypatch.setattr(
        idx, "ask_with_rotation",
        lambda prompt, **k: {"ok": True, "provider": "groq", "model": "gpt-oss-120b", "reply": "42", "notices": []},
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask-prompt", tui_mod.TextArea).text = "what is the answer"
            app.action_run_ask()
            for _ in range(60):
                await pilot.pause(0.05)
                if app._last_ask_reply:
                    break
            assert "groq/gpt-oss-120b" in str(app.query_one("#ask-status", Static).content)
            assert app._last_ask_reply == "42"
            assert "42" in "\n".join(app.query_one("#ask-log", tui_mod.Log).lines)

    asyncio.run(_run())


def test_ask_pane_shows_error(monkeypatch):
    monkeypatch.setattr(
        idx, "ask_with_rotation",
        lambda prompt, **k: {"ok": False, "error": "No configured provider available", "notices": []},
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask-prompt", tui_mod.TextArea).text = "hello"
            app.action_run_ask()
            for _ in range(60):
                await pilot.pause(0.05)
                if "error" in str(app.query_one("#ask-status", Static).content):
                    break
            assert "No configured provider available" in str(app.query_one("#ask-status", Static).content)
            assert app._last_ask_reply == ""

    asyncio.run(_run())


def test_ask_pane_shows_cycle_notice_in_log(monkeypatch):
    monkeypatch.setattr(
        idx, "ask_with_rotation",
        lambda prompt, **k: {
            "ok": True, "provider": "groq", "model": "gpt-oss-120b", "reply": "ok",
            "notices": ["deepinfra: quota exhausted, cycling to next provider…"],
        },
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask-prompt", tui_mod.TextArea).text = "hello"
            app.action_run_ask()
            for _ in range(60):
                await pilot.pause(0.05)
                if app._last_ask_reply:
                    break
            assert "cycling to next provider" in "\n".join(app.query_one("#ask-log", tui_mod.Log).lines)

    asyncio.run(_run())


def test_ask_pane_empty_prompt_shows_prompt_message():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_run_ask()
            await pilot.pause()
            assert "enter a prompt" in str(app.query_one("#ask-status", Static).content).lower()

    asyncio.run(_run())


def test_ask_prompt_ctrl_enter_submits(monkeypatch):
    """Enter must stay a newline in the prompt box (a real prompt can be
    multi-line) — Ctrl+Enter is the submit binding instead. Bound to both
    ctrl+enter and ctrl+j since most terminals send the same byte for both."""
    monkeypatch.setattr(
        idx, "ask_with_rotation",
        lambda prompt, **k: {"ok": True, "provider": "groq", "model": "m", "reply": "pong", "notices": []},
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            prompt_box = app.query_one("#ask-prompt", tui_mod.TextArea)
            prompt_box.text = "ping"
            prompt_box.focus()
            await pilot.pause()
            await pilot.press("ctrl+j")
            for _ in range(60):
                await pilot.pause(0.05)
                if app._last_ask_reply:
                    break
            assert app._last_ask_reply == "pong"

    asyncio.run(_run())


def test_ask_prompt_plain_enter_inserts_newline_not_submit():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            prompt_box = app.query_one("#ask-prompt", tui_mod.TextArea)
            prompt_box.text = "line one"
            prompt_box.focus()
            prompt_box.move_cursor(prompt_box.document.end)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert "\n" in prompt_box.text
            assert app._last_ask_reply == ""

    asyncio.run(_run())


def test_copy_ask_reply_to_clipboard():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._last_ask_reply = "the reply text"
            app.action_copy_ask_reply()
            await pilot.pause()
            assert app._clipboard == "the reply text"
            assert "copied" in str(app.query_one("#ask-status", Static).content).lower()

    asyncio.run(_run())


def test_copy_ask_reply_without_a_reply_yet():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_copy_ask_reply()
            await pilot.pause()
            assert "no reply" in str(app.query_one("#ask-status", Static).content).lower()

    asyncio.run(_run())


def test_models_pane_populates_table():
    _seed_one_model()

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#models-table", DataTable)
            assert table.row_count == 1

    asyncio.run(_run())


def test_models_table_truncates_long_model_id_and_keeps_full_text():
    long_id = "some-vendor-with-a-genuinely-very-long-model-identifier-string-far-past-30-chars"
    full_key = f"openrouter/{long_id}"
    _seed_one_model(model_id=long_id, provider="openrouter")

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#models-table", TruncatingDataTable)
            assert table.get_full_text(full_key) == full_key
            row = list(table.rows.keys())[0]
            model_cell = table.get_cell(row, list(table.columns.keys())[1])
            assert model_cell.endswith("...")
            assert len(model_cell) <= 30
            assert model_cell != long_id

    asyncio.run(_run())


def test_models_row_highlight_shows_full_id_in_status():
    long_id = "some-vendor-with-a-genuinely-very-long-model-identifier-string"
    _seed_one_model(model_id=long_id, provider="openrouter")

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            status = str(app.query_one("#models-status", Static).content)
            assert f"openrouter/{long_id}" in status

    asyncio.run(_run())


def test_copy_model_to_clipboard():
    _seed_one_model(model_id="copy-me-model", provider="openrouter")

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._selected_model_id = "openrouter/copy-me-model"
            app.action_copy_model()
            await pilot.pause()
            assert app._clipboard == "openrouter/copy-me-model"

    asyncio.run(_run())


def test_copy_model_without_selection_shows_prompt():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_copy_model()
            await pilot.pause()
            assert "select a model" in str(app.query_one("#models-status", Static).content).lower()
            assert not app._clipboard

    asyncio.run(_run())


def test_hover_over_model_row_sets_tooltip_to_full_id():
    _seed_one_model(model_id="hover-target-model", provider="openrouter")

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = "pane-models"
            await pilot.pause()
            table = app.query_one("#models-table", TruncatingDataTable)
            await pilot.hover("#models-table", offset=(2, 1))
            await pilot.pause()
            assert table.tooltip == "openrouter/hover-target-model"

    asyncio.run(_run())


def test_register_key_writes_env_and_lists_slot(_isolated):
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "https://httpbin.org\nsome-random-token-value-12345"
            app.action_register_key()
            await pilot.pause()
            table = app.query_one("#keys-table", DataTable)
            assert table.row_count == 1
            msg = str(app.query_one("#keys-msg", Static).content)
            assert "httpbin" in msg

    asyncio.run(_run())
    assert "TBCC_HTTPBIN_API_KEY=some-random-token-value-12345" in _isolated.read_text(encoding="utf-8")


def test_register_key_with_explicit_endpoint_bridges_into_ask(_isolated, monkeypatch):
    """Reproduces the operator's real failure: pasting a bare key alone (no
    URL in the paste) used to lose the endpoint entirely and land as an
    unusable generic-rest slot. The explicit Endpoint field is the fix —
    filling it in should register a working, Ask-usable LLM provider even
    when the paste box has just the key. Registering an LLM provider now also
    auto-verifies it (idx.refresh_provider_models) — stubbed here so this
    test never makes a real network call to the real OrcaRouter API."""
    monkeypatch.setattr(idx, "refresh_provider_models", lambda provider, **k: {"ok": True, "model_count": 3})

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "sk-orca-abcdefghijklmnop"
            app.query_one("#keys-endpoint", tui_mod.Input).value = "https://api.orcarouter.ai/v1"
            app.action_register_key()
            for _ in range(60):
                await pilot.pause(0.05)
                if "verified" in str(app.query_one("#keys-msg", Static).content):
                    break
            table = app.query_one("#keys-table", DataTable)
            assert table.row_count == 1
            msg = str(app.query_one("#keys-msg", Static).content)
            assert "orcarouter: key verified, 3 models pulled" in msg
            # endpoint field clears after a successful register, same as the paste box
            assert app.query_one("#keys-endpoint", tui_mod.Input).value == ""

    asyncio.run(_run())
    assert idx.custom_provider_ids() == ("orcarouter",)
    assert idx._get_credential("orcarouter")["base_url"] == "https://api.orcarouter.ai/v1"


def test_register_key_id_endpoint_and_auth_env_key_fields_are_explicit_overrides():
    """The operator's exact confusion: no visible field for id/auth env
    key/endpoint, no way to override auto-detection. All three now exist and
    win over whatever suggest_slot would have guessed. Category is
    deliberately NOT a field — classify_category only ever emits "llm" or
    "generic-rest" (always lowercase, exactly two values), so a free-text
    override would be the only way to actually produce an inconsistent tag."""

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "sk-not-a-recognized-prefix-abc123"
            app.query_one("#keys-id", tui_mod.Input).value = "my-provider"
            app.query_one("#keys-endpoint", tui_mod.Input).value = "https://example.com/v1"
            app.query_one("#keys-auth-env-key", tui_mod.Input).value = "MY_PROVIDER_KEY"
            app.action_register_key()
            await pilot.pause()
            table = app.query_one("#keys-table", DataTable)
            assert table.row_count == 1
            msg = str(app.query_one("#keys-msg", Static).content)
            assert "my-provider" in msg
            assert "MY_PROVIDER_KEY" in msg
            for fid in ("#keys-id", "#keys-endpoint", "#keys-auth-env-key"):
                assert app.query_one(fid, tui_mod.Input).value == ""

    asyncio.run(_run())


def test_keys_field_enter_advances_focus_id_to_auth_env_key_to_endpoint():
    """Enter-to-advance chain the operator asked for: Id -> Auth env key ->
    Endpoint. The multi-line paste box deliberately keeps Enter=newline (curl
    blobs need it) and isn't part of this chain."""

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            id_input = app.query_one("#keys-id", tui_mod.Input)
            auth_input = app.query_one("#keys-auth-env-key", tui_mod.Input)
            endpoint_input = app.query_one("#keys-endpoint", tui_mod.Input)

            id_input.focus()
            id_input.value = "whatever"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is auth_input

            auth_input.value = "SOME_KEY"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is endpoint_input

    asyncio.run(_run())


def test_keys_endpoint_field_enter_triggers_register():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "https://httpbin.org\nsome-token-value-12345"
            endpoint_input = app.query_one("#keys-endpoint", tui_mod.Input)
            endpoint_input.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#keys-table", DataTable).row_count == 1

    asyncio.run(_run())


def test_register_llm_key_auto_verify_failure_shows_error(monkeypatch):
    monkeypatch.setattr(idx, "refresh_provider_models", lambda provider, **k: {"ok": False, "error": "bad key"})

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "sk-orca-abcdefghijklmnop"
            app.query_one("#keys-endpoint", tui_mod.Input).value = "https://api.orcarouter.ai/v1"
            app.action_register_key()
            for _ in range(60):
                await pilot.pause(0.05)
                msg_widget = app.query_one("#keys-msg", Static)
                if "verify failed" in str(msg_widget.content):
                    break
            assert msg_widget.has_class("error")
            assert "bad key" in str(msg_widget.content)

    asyncio.run(_run())


def test_register_key_rejects_junk_shows_error():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#keys-paste", tui_mod.TextArea).text = "short"
            app.action_register_key()
            await pilot.pause()
            msg_widget = app.query_one("#keys-msg", Static)
            assert msg_widget.has_class("error")
            assert app.query_one("#keys-table", DataTable).row_count == 0

    asyncio.run(_run())


def test_keys_highlight_updates_selected_slot():
    """Arrow highlight must set _selected_slot_id (not only Enter/RowSelected)."""

    class _Evt:
        def __init__(self):
            self.data_table = type("T", (), {"id": "keys-table"})()
            self.row_key = type("K", (), {"value": "pastebin"})()

    app = OperatorTuiApp()
    app._selected_slot_id = "tbcc-generic"
    app.on_data_table_row_highlighted(_Evt())  # type: ignore[arg-type]
    assert app._selected_slot_id == "pastebin"


def test_test_key_calls_selected_slot(monkeypatch):
    reg.add_slot(
        auth_env_key="TBCC_SMOKE_API_KEY", base_url="https://httpbin.org",
        slot_id="smoke", method="POST", path_template="/post",
    )
    monkeypatch.setenv("TBCC_SMOKE_API_KEY", "sk-test")

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(reg.httpx, "request", lambda *a, **k: _FakeResponse())

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._selected_slot_id = "smoke"
            app.action_test_key()
            await pilot.pause()
            msg = str(app.query_one("#keys-msg", Static).content)
            assert '"ok": true' in msg.lower()

    asyncio.run(_run())


def test_test_key_method_path_overrides_reach_call_slot(monkeypatch):
    """Real bug this fixes: a freshly-registered generic-rest slot defaults
    to GET with no path (nothing about the key reveals the real request
    shape) — Pastebin's actual endpoint needs POST, producing a 405 with no
    way to test the right call short of removing and re-adding via the CLI's
    `slots call --method --path`. These fields expose the same per-call
    override call_slot already supports, in the TUI."""
    reg.add_slot(auth_env_key="TBCC_PASTEBIN_API_KEY", base_url="https://pastebin.com", slot_id="pastebin")
    monkeypatch.setenv("TBCC_PASTEBIN_API_KEY", "sk-test")

    seen_calls = []

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    def _fake_request(method, url, **kwargs):
        seen_calls.append((method, url))
        return _FakeResponse()

    monkeypatch.setattr(reg.httpx, "request", _fake_request)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._selected_slot_id = "pastebin"
            app.query_one("#keys-test-method", tui_mod.Input).value = "POST"
            app.query_one("#keys-test-path", tui_mod.Input).value = "/api/api_post.php"
            app.action_test_key()
            await pilot.pause()

    asyncio.run(_run())
    assert seen_calls == [("POST", "https://pastebin.com/api/api_post.php")]


def test_copy_affiliate_url_to_clipboard(monkeypatch):
    row = {"id": 42, "label": "Cloud Farm Wallet", "url": "https://t.me/CloudFarmWalletBot", "payout_kind": "other", "priority_tier": 10, "active": True}
    monkeypatch.setattr(tui_mod.httpx, "get", lambda *a, **k: _FakeResponse(200, [row]))

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._selected_affiliate_id = 42
            app.action_copy_affiliate_url()
            await pilot.pause()
            assert app._clipboard == "https://t.me/CloudFarmWalletBot"
            assert "copied" in str(app.query_one("#aff-msg", Static).content)

    asyncio.run(_run())


def test_copy_affiliate_url_without_selection_shows_error():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_copy_affiliate_url()
            await pilot.pause()
            assert app.query_one("#aff-msg", Static).has_class("error")

    asyncio.run(_run())


def test_add_affiliate_link_creates_row(monkeypatch):
    added = {"id": 1, "label": "Cloud Farm Wallet", "url": "https://t.me/CloudFarmWalletBot", "payout_kind": "other", "priority_tier": 10, "active": True}
    monkeypatch.setattr(tui_mod.httpx, "post", lambda *a, **k: _FakeResponse(200, added))
    monkeypatch.setattr(tui_mod.httpx, "get", lambda *a, **k: _FakeResponse(200, [added]))

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#aff-label", tui_mod.Input).value = "Cloud Farm Wallet"
            app.query_one("#aff-url", tui_mod.Input).value = "https://t.me/CloudFarmWalletBot"
            app.action_add_affiliate()
            await pilot.pause()
            table = app.query_one("#aff-table", DataTable)
            assert table.row_count == 1
            assert "added" in str(app.query_one("#aff-msg", Static).content)

    asyncio.run(_run())


def test_add_affiliate_link_rejected_by_island_shows_detail(monkeypatch):
    monkeypatch.setattr(
        tui_mod.httpx, "post", lambda *a, **k: _FakeResponse(400, {"detail": "Unknown placements: bogus"})
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#aff-label", tui_mod.Input).value = "Bad Link"
            app.query_one("#aff-url", tui_mod.Input).value = "https://example.com"
            app.query_one("#aff-placements", tui_mod.Input).value = "bogus"
            app.action_add_affiliate()
            await pilot.pause()
            msg_widget = app.query_one("#aff-msg", Static)
            assert msg_widget.has_class("error")
            assert "Unknown placements" in str(msg_widget.content)
            assert app.query_one("#aff-table", DataTable).row_count == 0

    asyncio.run(_run())


def test_mount_survives_unreachable_island_api(monkeypatch):
    """Reproduces the real failure the operator hit: the affiliate pane used
    to dial a local Postgres directly, which isn't running (cloud-only
    runtime, CLAUDE.md). Now it goes through the island API instead — this
    still exercises the same "one pane's outage must not crash the app"
    guarantee for whenever the island itself is unreachable (no network,
    DNS hiccup, island down)."""

    def _boom(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(tui_mod.httpx, "get", _boom)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#aff-table", DataTable).row_count == 0
            assert app.query_one("#aff-msg", Static).has_class("error")
            assert "unreachable" in str(app.query_one("#aff-msg", Static).content)
            # other panes still work — the outage didn't take the whole app down.
            assert app.query_one("#models-table", DataTable) is not None
            assert app.query_one("#keys-table", DataTable) is not None

    asyncio.run(_run())


def test_add_affiliate_link_when_island_unreachable_shows_message(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(tui_mod.httpx, "post", _boom)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#aff-label", tui_mod.Input).value = "Cloud Farm Wallet"
            app.query_one("#aff-url", tui_mod.Input).value = "https://t.me/CloudFarmWalletBot"
            app.action_add_affiliate()
            await pilot.pause()
            msg_widget = app.query_one("#aff-msg", Static)
            assert msg_widget.has_class("error")
            assert "unreachable" in str(msg_widget.content)

    asyncio.run(_run())


def test_add_affiliate_link_requires_label_and_url():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_add_affiliate()
            await pilot.pause()
            assert app.query_one("#aff-msg", Static).has_class("error")
            assert app.query_one("#aff-table", DataTable).row_count == 0

    asyncio.run(_run())


def test_add_feed_creates_row_and_picked_up_by_list_sources():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#rss-id", tui_mod.Input).value = "hnrss-agents"
            app.query_one("#rss-label", tui_mod.Input).value = "HN: agents"
            app.query_one("#rss-url", tui_mod.Input).value = "https://hnrss.org/newest?q=agent"
            app.query_one("#rss-lane", tui_mod.Select).value = "dev"
            app.action_add_feed()
            await pilot.pause()
            table = app.query_one("#rss-table", DataTable)
            assert table.row_count == 2  # the fixture's seed entry + this one
            msg = str(app.query_one("#rss-msg", Static).content)
            assert "hnrss-agents" in msg

    asyncio.run(_run())
    assert sorted(s["id"] for s in tui_mod.list_sources()) == ["hnrss-agents", "seed"]


def test_add_feed_rejects_duplicate_id():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(2):
                app.query_one("#rss-id", tui_mod.Input).value = "dup-feed"
                app.query_one("#rss-label", tui_mod.Input).value = "Dup"
                app.query_one("#rss-url", tui_mod.Input).value = "https://example.com/feed.xml"
                app.action_add_feed()
                await pilot.pause()
            assert app.query_one("#rss-msg", Static).has_class("error")
            assert app.query_one("#rss-table", DataTable).row_count == 2  # seed + the one successful add

    asyncio.run(_run())


def test_add_feed_requires_fields():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_add_feed()
            await pilot.pause()
            assert app.query_one("#rss-msg", Static).has_class("error")
            assert app.query_one("#rss-table", DataTable).row_count == 1  # unchanged from the fixture's seed

    asyncio.run(_run())


def _archive_row(row_id=1, kind="url", summary="A cool gallery", value="https://example.com/g/1", tags="erome"):
    return {"id": row_id, "kind": kind, "summary": summary, "value": value, "tags": tags}


def test_archive_pane_lists_entries_from_island(monkeypatch):
    monkeypatch.setattr(
        tui_mod.httpx, "get",
        lambda url, **k: _FakeResponse(200, {"items": [_archive_row()]}) if "/archive/" in url else _FakeResponse(200, []),
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#archive-table", DataTable).row_count == 1

    asyncio.run(_run())


def test_archive_search_reloads_with_query(monkeypatch):
    seen_params = {}

    def _fake_get(url, **k):
        if "/archive/" in url:
            seen_params.update(k.get("params") or {})
            return _FakeResponse(200, {"items": [_archive_row()]})
        return _FakeResponse(200, [])

    monkeypatch.setattr(tui_mod.httpx, "get", _fake_get)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#archive-search", tui_mod.Input).value = "erome"
            app.action_search_archive()
            await pilot.pause()
            assert "result" in str(app.query_one("#archive-msg", Static).content)

    asyncio.run(_run())
    assert seen_params.get("q") == "erome"


def test_archive_mount_survives_unreachable_island(monkeypatch):
    def _fake_get(url, **k):
        if "/archive/" in url:
            raise httpx.ConnectError("connection refused")
        return _FakeResponse(200, [])

    monkeypatch.setattr(tui_mod.httpx, "get", _fake_get)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#archive-table", DataTable).row_count == 0
            msg = app.query_one("#archive-msg", Static)
            assert msg.has_class("error")
            assert "unreachable" in str(msg.content)
            # other panes still work
            assert app.query_one("#models-table", DataTable) is not None

    asyncio.run(_run())


def test_add_archive_urls_posts_bulk_and_reloads(monkeypatch):
    added_row = _archive_row(row_id=2, value="https://bunkr.si/a/xyz")
    post_calls = []

    def _fake_post(url, **k):
        post_calls.append((url, k.get("json")))
        return _FakeResponse(200, {"added": 1, "total": 1, "auto_tag": {"enriched": 1}})

    monkeypatch.setattr(tui_mod.httpx, "post", _fake_post)
    monkeypatch.setattr(
        tui_mod.httpx, "get",
        lambda url, **k: _FakeResponse(200, {"items": [added_row]}) if "/archive/" in url else _FakeResponse(200, []),
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#archive-paste", tui_mod.TextArea).text = "https://bunkr.si/a/xyz\nnot a url"
            app.action_add_archive_urls()
            await pilot.pause()
            assert app.query_one("#archive-table", DataTable).row_count == 1
            msg = str(app.query_one("#archive-msg", Static).content)
            assert "added 1" in msg
            assert "auto-tagged 1" in msg
            assert app.query_one("#archive-paste", tui_mod.TextArea).text == ""

    asyncio.run(_run())
    assert len(post_calls) == 1
    url, body = post_calls[0]
    assert url.endswith("/archive/entries/bulk")
    assert body["entries"] == [{"kind": "url", "value": "https://bunkr.si/a/xyz"}]
    assert body["auto_tag"] is True


def test_add_archive_urls_requires_a_real_url():
    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#archive-paste", tui_mod.TextArea).text = "not a url at all"
            app.action_add_archive_urls()
            await pilot.pause()
            assert app.query_one("#archive-msg", Static).has_class("error")

    asyncio.run(_run())


def test_autotag_missing_archive_calls_bulk_endpoint(monkeypatch):
    post_calls = []

    def _fake_post(url, **k):
        post_calls.append((url, k.get("json")))
        return _FakeResponse(200, {"enriched": 3, "skipped": 1})

    monkeypatch.setattr(tui_mod.httpx, "post", _fake_post)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_autotag_missing_archive()
            await pilot.pause()
            assert "auto-tagged 3" in str(app.query_one("#archive-msg", Static).content)

    asyncio.run(_run())
    assert len(post_calls) == 1
    url, body = post_calls[0]
    assert url.endswith("/archive/entries/bulk/auto-tag")
    assert body == {"missing_only": True, "limit": 24}


def test_copy_archive_formatted_pipe_style(monkeypatch):
    monkeypatch.setattr(
        tui_mod.httpx, "get",
        lambda url, **k: _FakeResponse(200, {"items": [_archive_row()]}) if "/archive/" in url else _FakeResponse(200, []),
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_copy_archive_formatted()
            await pilot.pause()
            assert app._clipboard == "A cool gallery | https://example.com/g/1"

    asyncio.run(_run())


def test_copy_archive_formatted_all_four_shapes(monkeypatch):
    monkeypatch.setattr(
        tui_mod.httpx, "get",
        lambda url, **k: _FakeResponse(200, {"items": [_archive_row()]}) if "/archive/" in url else _FakeResponse(200, []),
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            expected = {
                "pipe": "A cool gallery | https://example.com/g/1",
                "title": "A cool gallery",
                "url": "https://example.com/g/1",
                "rich": "[A cool gallery](https://example.com/g/1)",
            }
            for fmt, want in expected.items():
                app.query_one("#archive-format", tui_mod.Input).value = fmt
                app.action_copy_archive_formatted()
                await pilot.pause()
                assert app._clipboard == want, fmt

    asyncio.run(_run())


def test_copy_archive_formatted_rejects_unknown_format(monkeypatch):
    monkeypatch.setattr(
        tui_mod.httpx, "get",
        lambda url, **k: _FakeResponse(200, {"items": [_archive_row()]}) if "/archive/" in url else _FakeResponse(200, []),
    )

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#archive-format", tui_mod.Input).value = "bogus"
            app.action_copy_archive_formatted()
            await pilot.pause()
            assert app.query_one("#archive-msg", Static).has_class("error")

    asyncio.run(_run())


def test_scan_missing_script_shows_message(monkeypatch):
    monkeypatch.setattr(tui_mod, "_semantic_scan_script", lambda: None)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_run_selftest()
            await pilot.pause()
            status = str(app.query_one("#scan-status", Static).content)
            assert "not found" in status

    asyncio.run(_run())


def test_scan_runs_stub_script_and_shows_pass(tmp_path, monkeypatch):
    fake = tmp_path / "fake_semantic_scan.py"
    fake.write_text(
        "import sys\n"
        "print('PASS' if '--self-test' in sys.argv else '{}')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tui_mod, "_semantic_scan_script", lambda: fake)

    async def _run():
        app = OperatorTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_run_selftest()
            for _ in range(60):
                await pilot.pause(0.05)
                if "PASS" in str(app.query_one("#scan-status", Static).content):
                    break
            assert "PASS" in str(app.query_one("#scan-status", Static).content)

    asyncio.run(_run())


def test_banner_is_always_one_of_the_rotation_set():
    for _ in range(10):
        app = OperatorTuiApp()
        assert app._banner in tui_mod._BANNERS
