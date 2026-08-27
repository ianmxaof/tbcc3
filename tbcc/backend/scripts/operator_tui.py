"""Unified operator terminal — one persistent Textual app over the pieces
that used to be separate one-shot CLI/API calls: the LLM model/provider
index, API Pocket key registration (writes tbcc/.env + Windows Credential
Manager) with an instant test-call, affiliate-link upload, and the
semantic-deception scanner. Devops-only — requires `textual`
(tbcc/backend/requirements-dev.txt, not shipped to the island).

Meant to be launched once and left open: pull it into focus whenever you
paste a fresh API key, want to add an affiliate link, or need to semantically
scan a path/URL — instead of remembering four separate CLI invocations.

Sized for a fixed small terminal (default target: 62x28) — the main layout
never scrolls; only the lists (models/keys/affiliate) get their own internal
scrollbar when they overflow, same as any DataTable does natively. Long cell
text is truncated with "..." to fit its column; hover a row (or select it)
to see the untruncated value.

Run via: py -3.13 scripts/tbcc_cli.py operator tui
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal
from textual.widgets import Button, DataTable, Footer, Input, Log, Select, Static, TabbedContent, TabPane, TextArea

from app.api.tools_slots import register_slot_from_paste
from app.services import llm_model_index as idx
from app.services.api_slot_registry import call_slot, list_slots
from app.services.research_scanner import add_source, list_sources
from scripts.llm_tui import _fmt_row as _fmt_model_row

# (label, column width) — kept in the same order _fmt_model_row returns cells.
# Provider+Model alone sum to 40, comfortably under a 62-col terminal, so the
# model name is fully visible without horizontal scroll; the remaining
# columns are still reachable via the table's own scrollbar.
_MODEL_COL_SPEC: tuple[tuple[str, int], ...] = (
    ("Provider", 10), ("Model", 30), ("Ctx", 8), ("Owner", 12),
    ("Stale", 6), ("Exhausted", 10), ("Usage left", 14), ("Fetched", 16),
)
_KEY_COL_SPEC: tuple[tuple[str, int], ...] = (
    ("Id", 12), ("Category", 12), ("Auth env key", 22), ("Base URL", 24),
)
_AFF_COL_SPEC: tuple[tuple[str, int], ...] = (
    ("Id", 6), ("Label", 18), ("URL", 26), ("Payout", 10), ("Priority", 10), ("Active", 8),
)
_RSS_COL_SPEC: tuple[tuple[str, int], ...] = (
    ("Id", 12), ("Label", 14), ("Lane", 8), ("URL", 24),
)
_RSS_LANES: tuple[str, ...] = ("dev", "growth", "content")
_ARCHIVE_COL_SPEC: tuple[tuple[str, int], ...] = (
    ("Kind", 5), ("Title", 20), ("URL", 22), ("Tags", 10),
)
_ARCHIVE_FORMATS: frozenset[str] = frozenset({"pipe", "title", "url", "rich"})


def _truncate(value: object, width: int) -> str:
    """Cap a cell's display text at `width` columns, marking the cut with
    "..." — used instead of letting a DataTable column auto-grow to the
    widest cell (that's what used to force the window to full screen to
    read a long model id)."""
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


class TruncatingDataTable(DataTable):
    """DataTable whose cells may be pre-truncated to a fixed column width.
    Tracks each row's untruncated "primary" value (model id / base URL /
    affiliate URL) so a mouse hover shows it as a tooltip, and pane Copy
    buttons can pull the same value onto the clipboard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._full_text: dict[str, str] = {}

    def set_full_text(self, row_key: object, text: str) -> None:
        self._full_text[str(row_key)] = text

    def get_full_text(self, row_key: object) -> str | None:
        return None if row_key is None else self._full_text.get(str(row_key))

    def clear(self, columns: bool = False) -> "TruncatingDataTable":
        self._full_text.clear()
        return super().clear(columns=columns)

    def watch_hover_coordinate(self, old, value) -> None:  # noqa: ANN001 — Coordinate, matches base signature
        super().watch_hover_coordinate(old, value)
        try:
            cell_key = self.coordinate_to_cell_key(value)
        except Exception:  # noqa: BLE001 — no cell under the cursor (empty table, out of bounds)
            self.tooltip = None
            return
        self.tooltip = self.get_full_text(cell_key.row_key.value)


class AskPromptTextArea(TextArea):
    """Multi-line prompt box — Enter stays a newline (a real prompt can be
    multi-line), Ctrl+Enter submits. Also bound to ctrl+j: most terminals
    (including Windows Terminal, historically) send the same byte for
    Ctrl+Enter and Ctrl+J, so binding only "ctrl+enter" risks silently doing
    nothing on terminals that don't disambiguate the two. The Ask button is
    the always-works fallback regardless of what a given terminal sends."""

    BINDINGS = [
        Binding("ctrl+enter", "submit_ask", "Send", show=False),
        Binding("ctrl+j", "submit_ask", "Send", show=False),
    ]

    def action_submit_ask(self) -> None:
        self.app.action_run_ask()


def _semantic_scan_script() -> Path | None:
    override = (os.getenv("TBCC_SEMANTIC_SCAN_PATH") or "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None
    default = Path.home() / ".cursor" / "skills" / "semantic-deception-detector" / "scripts" / "semantic_scan.py"
    return default if default.is_file() else None


def _island_api_base() -> str:
    """Shared base URL for anything backed by revenue-primary data on the
    island's Postgres, not reachable from a PC-local DB connection (see
    REVENUE_ISLAND.md: "Home Docker Postgres = local/dev only... Island
    Postgres = revenue primary"). Goes through the island's public API —
    same surface the extension and dashboard already use — never a direct
    DB connection, matching CLAUDE.md's cloud-only-runtime policy. Used by
    both the Affiliate links pane and the Archive pane."""
    return (os.getenv("TBCC_API_PUBLIC_URL") or "https://api.powercore.app").rstrip("/")


def _list_affiliate_rows() -> list[dict]:
    r = httpx.get(
        f"{_island_api_base()}/promo-affiliate-links/",
        params={"active_only": "false", "sort": "priority_asc"},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


def _list_archive_rows(query: str = "") -> list[dict]:
    r = httpx.get(
        f"{_island_api_base()}/archive/entries",
        params={"q": query or None, "page_size": 50, "sort": "added_at", "order": "desc"},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json().get("items", [])


_BANNERS: tuple[str, ...] = (
    r""" _________  __________    _______   ____
/_  __/ _ )/ ___/ ___/___/ ___/ /  /  _/
 / / / _  / /__/ /__/___/ /__/ /___/ /
/_/ /____/\___/\___/    \___/____/___/""",
    r"""  _______ _______  _______ _______        _______ ___     ___
 |       |   _   \|   _   |   _   |______|   _   |   |   |   |
 |.|   | |.  1   /|.  1___|.  1___|______|.  1___|.  |   |.  |
 `-|.  |-|.  _   \|.  |___|.  |___       |.  |___|.  |___|.  |
   |:  | |:  1    |:  1   |:  1   |      |:  1   |:  1   |:  |
   |::.| |::.. .  |::.. . |::.. . |      |::.. . |::.. . |::.|
   `---' `-------'`-------`-------'      `-------`-------`---'""",
    r"""  ___________  _____  _____       _____  _     _____
|_   _| ___ \/  __ \/  __ \     /  __ \| |   |_   _|
  | | | |_/ /| /  \/| /  \/_____| /  \/| |     | |
  | | | ___ \| |    | |  |______| |    | |     | |
  | | | |_/ /| \__/\| \__/\     | \__/\| |_____| |_
  \_/ \____/  \____/ \____/      \____/\_____/\___/""",
    r"""_______  ______   ______  ______ - ______  _       _____
  | |   | |  | \ | |     | |      | |     | |       | |
  | |   | |--| < | |     | |      | |     | |   _   | |
  |_|   |_|__|_/ |_|____ |_|____  |_|____ |_|__|_| _|_|_""",
    r""" _______ ______  _______ _______ _______ _       _
(_______|____  \(_______|_______|_______|_)     | |
    _    ____)  )_       _ _____ _       _      | |
   | |  |  __  (| |     | (_____) |     | |     | |
   | |  | |__)  ) |_____| |_____| |_____| |_____| |
   |_|  |______/ \______)\______)\______)_______)_|""",
)


class OperatorTuiApp(App):
    """Tabbed front door over the LLM index, API Pocket, affiliate links,
    and the semantic-deception scanner."""

    CSS = """
    Screen { overflow-x: hidden; }
    #banner { width: auto; height: 4; overflow: hidden; color: $accent; text-style: bold; padding: 0; margin: 0; }
    TabbedContent { height: 1fr; }
    ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; padding: 0; }
    DataTable { height: 1fr; margin-bottom: 0; }
    #keys-paste, #scan-log { height: 3; }
    Static.msg { padding: 0 1; color: $text-muted; }
    Static.msg.error { color: $error; }
    .form-row { height: auto; }
    .form-row Input { width: 1fr; margin-right: 1; }

    * { scrollbar-size-vertical: 1; }
    """

    BINDINGS = [Binding("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._banner = random.choice(_BANNERS)
        self._selected_slot_id: str | None = None
        self._selected_model_id: str | None = None
        self._selected_affiliate_id: int | None = None
        self._scan_args: tuple[str, bool] = ("", False)
        self._ask_prompt: str = ""
        self._last_ask_reply: str = ""
        self._pending_verify_provider: str = ""
        self._archive_rows_cache: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        yield Center(Static(self._banner, id="banner"))
        with TabbedContent():
            with TabPane("Ask", id="pane-ask"):
                yield AskPromptTextArea(id="ask-prompt")
                with Horizontal(classes="form-row"):
                    yield Button("Ask", id="ask-run", variant="primary", compact=True)
                    yield Button("Copy reply", id="ask-copy", compact=True)
                yield Static("", id="ask-status", classes="msg")
                yield Log(id="ask-log")
            with TabPane("Models", id="pane-models"):
                yield TruncatingDataTable(id="models-table", zebra_stripes=True, cursor_type="row")
                yield Static("", id="models-status", classes="msg")
                with Horizontal(classes="form-row"):
                    yield Button("Refresh", id="models-refresh", compact=True)
                    yield Button("Next sticky", id="models-next", compact=True)
                    yield Button("Copy", id="models-copy", compact=True)
            with TabPane("Keys", id="pane-keys"):
                yield TruncatingDataTable(id="keys-table", zebra_stripes=True, cursor_type="row")
                yield TextArea(id="keys-paste")
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="Id (optional)", id="keys-id", compact=True)
                    yield Input(placeholder="Auth env key (optional)", id="keys-auth-env-key", compact=True)
                yield Input(
                    placeholder="Endpoint (base URL or full path — pastebin.com/api/api_post.php OK)",
                    id="keys-endpoint",
                    compact=True,
                )
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="Test method (optional, e.g. POST)", id="keys-test-method", compact=True)
                    yield Input(placeholder="Test path (optional, e.g. /api/api_post.php)", id="keys-test-path", compact=True)
                with Horizontal(classes="form-row"):
                    yield Button("Register", id="keys-register", variant="primary", compact=True)
                    yield Button("Test selected", id="keys-test", compact=True)
                    yield Button("Remove selected", id="keys-remove", compact=True)
                yield Static(
                    "Paste key (+ optional endpoint). Arrow onto a row then Test. "
                    "Pastebin: Id=pastebin, Auth=TBCC_PASTEBIN_API_DEV_KEY, Endpoint=https://pastebin.com/api/api_post.php · "
                    "Moonshot/Kimi: Id=moonshot, Auth=TBCC_MOONSHOT_API_KEY, Endpoint=https://api.moonshot.ai/v1 "
                    "(see tbcc/docs/KIMI_ROTATOR_SETUP.md)",
                    id="keys-msg",
                    classes="msg",
                )
            with TabPane("Affiliate", id="pane-affiliate"):
                yield TruncatingDataTable(id="aff-table", zebra_stripes=True, cursor_type="row")
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="Label", id="aff-label", compact=True)
                    yield Input(placeholder="URL", id="aff-url", compact=True)
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="payout_kind", id="aff-payout", value="other", compact=True)
                    yield Input(placeholder="priority_tier", id="aff-priority", value="10", compact=True)
                    yield Input(placeholder="placements (csv)", id="aff-placements", value="manual_only", compact=True)
                with Horizontal(classes="form-row"):
                    yield Button("Add link", id="aff-add", variant="primary", compact=True)
                    yield Button("Copy URL", id="aff-copy", compact=True)
                yield Static("", id="aff-msg", classes="msg")
            with TabPane("Scan", id="pane-scan"):
                yield Input(placeholder="Local path or URL", id="scan-target", compact=True)
                with Horizontal(classes="form-row"):
                    yield Button("Scan", id="scan-run", variant="primary", compact=True)
                    yield Button("Self-test", id="scan-selftest", compact=True)
                yield Static("", id="scan-status", classes="msg")
                yield Log(id="scan-log")
            with TabPane("RSS", id="pane-rss"):
                yield TruncatingDataTable(id="rss-table", zebra_stripes=True, cursor_type="row")
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="id (kebab-case)", id="rss-id", compact=True)
                    yield Input(placeholder="label", id="rss-label", compact=True)
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="feed URL (RSS/Atom XML)", id="rss-url", compact=True)
                    yield Select(
                        [(lane, lane) for lane in _RSS_LANES], value="dev", id="rss-lane", compact=True, allow_blank=False
                    )
                yield Button("Add feed", id="rss-add", variant="primary", compact=True)
                yield Static(
                    "Any RSS/Atom XML URL works — GitHub .../releases.atom, a subreddit's .rss, hnrss.org queries.",
                    id="rss-msg", classes="msg",
                )
            with TabPane("Archive", id="pane-archive"):
                yield TruncatingDataTable(id="archive-table", zebra_stripes=True, cursor_type="row")
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="Search (url/tag/title)", id="archive-search", compact=True)
                    yield Button("Search", id="archive-search-btn", compact=True)
                yield TextArea(id="archive-paste")
                with Horizontal(classes="form-row"):
                    yield Button("Add + auto-tag", id="archive-add", variant="primary", compact=True)
                    yield Button("Auto-tag missing", id="archive-autotag", compact=True)
                with Horizontal(classes="form-row"):
                    yield Input(placeholder="Format: pipe/title/url/rich (default pipe)", id="archive-format", compact=True)
                    yield Button("Copy shown", id="archive-copy", compact=True)
                yield Static("Paste URLs (one per line) to add. \"pipe\" = OneTab-style Title | URL.", id="archive-msg", classes="msg")
        yield Footer()

    def on_mount(self) -> None:
        for label, width in _MODEL_COL_SPEC:
            self.query_one("#models-table", DataTable).add_column(label, width=width)
        for label, width in _KEY_COL_SPEC:
            self.query_one("#keys-table", DataTable).add_column(label, width=width)
        for label, width in _AFF_COL_SPEC:
            self.query_one("#aff-table", DataTable).add_column(label, width=width)
        for label, width in _RSS_COL_SPEC:
            self.query_one("#rss-table", DataTable).add_column(label, width=width)
        for label, width in _ARCHIVE_COL_SPEC:
            self.query_one("#archive-table", DataTable).add_column(label, width=width)
        self._reload_models()
        self._reload_keys()
        self._reload_research()
        self._reload_affiliates()
        self._reload_archive()

    # ---- Ask pane (llm_model_index.ask_with_rotation) --------------------

    def action_run_ask(self) -> None:
        prompt = self.query_one("#ask-prompt", TextArea).text.strip()
        if not prompt:
            self.query_one("#ask-status", Static).update("Enter a prompt first.")
            return
        self._ask_prompt = prompt
        self.query_one("#ask-status", Static).update("asking...")
        self.run_worker(self._do_ask, thread=True, exclusive=True)

    def _do_ask(self) -> None:
        result = idx.ask_with_rotation(self._ask_prompt)
        self.call_from_thread(self._show_ask_result, result)

    def _show_ask_result(self, result: dict) -> None:
        log = self.query_one("#ask-log", Log)
        log.clear()
        for notice in result.get("notices") or []:
            log.write_line(notice)
        if result.get("ok"):
            self._last_ask_reply = result.get("reply") or ""
            self.query_one("#ask-status", Static).update(f"{result['provider']}/{result['model']}")
            log.write_lines(self._last_ask_reply.splitlines())
        else:
            self._last_ask_reply = ""
            self.query_one("#ask-status", Static).update(f"error: {result.get('error')}")

    def action_copy_ask_reply(self) -> None:
        if not self._last_ask_reply:
            self.query_one("#ask-status", Static).update("No reply to copy yet.")
            return
        self.copy_to_clipboard(self._last_ask_reply)
        self.query_one("#ask-status", Static).update("copied reply to clipboard")

    # ---- Models pane ----------------------------------------------------

    def _models_status_text(self) -> str:
        sticky = idx.get_sticky()
        sticky_s = f"sticky: {sticky['provider']}" if sticky and sticky.get("provider") else "sticky: (none)"
        return sticky_s

    def _reload_models(self) -> None:
        table = self.query_one("#models-table", TruncatingDataTable)
        table.clear()
        for row in idx.list_models():
            full_id = f"{row['provider']}/{row['model_id']}"
            formatted = _fmt_model_row(row)
            cells = [_truncate(v, w) for v, (_, w) in zip(formatted, _MODEL_COL_SPEC)]
            table.add_row(*cells, key=full_id)
            table.set_full_text(full_id, full_id)
        self.query_one("#models-status", Static).update(self._models_status_text())

    def action_refresh_models(self) -> None:
        self.query_one("#models-status", Static).update("refreshing... (hitting every provider's /models)")
        self.run_worker(self._do_refresh_models, thread=True, exclusive=True)

    def _do_refresh_models(self) -> None:
        idx.refresh_all_providers()
        self.call_from_thread(self._reload_models)

    def action_copy_model(self) -> None:
        if not self._selected_model_id:
            self.query_one("#models-status", Static).update("Select a model row first.")
            return
        self.copy_to_clipboard(self._selected_model_id)
        self.query_one("#models-status", Static).update(f"copied: {self._selected_model_id}")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # Cursor highlight must update selection — Keys previously only set
        # `_selected_slot_id` on RowSelected (Enter), so arrowing onto pastebin
        # still Test-selected the prior row (e.g. broken tbcc-generic).
        if event.data_table.id == "keys-table" and event.row_key.value is not None:
            self._selected_slot_id = str(event.row_key.value)
            return
        if event.data_table.id == "aff-table" and event.row_key.value is not None:
            self._selected_affiliate_id = int(event.row_key.value)
            return
        if event.data_table.id == "models-table":
            if event.row_key.value is not None:
                self._selected_model_id = str(event.row_key.value)
            full = event.data_table.get_full_text(event.row_key.value)
            if full:
                self.query_one("#models-status", Static).update(f"{self._models_status_text()}   |   {full}")

    # ---- Keys / API Pocket pane -----------------------------------------

    def _reload_keys(self) -> None:
        table = self.query_one("#keys-table", TruncatingDataTable)
        table.clear()
        for slot in list_slots():
            base_url = slot.get("base_url") or "—"
            raw = (slot["id"], slot["category"], slot["auth_env_key"], base_url)
            cells = [_truncate(v, w) for v, (_, w) in zip(raw, _KEY_COL_SPEC)]
            table.add_row(*cells, key=slot["id"])
            table.set_full_text(slot["id"], base_url)

    def _set_keys_msg(self, text: str, *, error: bool = False) -> None:
        msg = self.query_one("#keys-msg", Static)
        msg.set_class(error, "error")
        msg.update(text)

    def action_register_key(self) -> None:
        text = self.query_one("#keys-paste", TextArea).text.strip()
        if not text:
            self._set_keys_msg("Paste a key/curl/URL first.", error=True)
            return
        slot_id = self.query_one("#keys-id", Input).value.strip()
        endpoint = self.query_one("#keys-endpoint", Input).value.strip() or None
        auth_env_key = self.query_one("#keys-auth-env-key", Input).value.strip() or None
        try:
            # category is never a manual field — classify_category only ever
            # emits "llm" or "generic-rest" (always lowercase, always one of
            # two values), so letting it stay fully auto-detected is what
            # keeps the slot list uniform, not adding a free-text override.
            result = register_slot_from_paste(text, id=slot_id, base_url=endpoint, auth_env_key=auth_env_key)
        except (ValueError, FileNotFoundError) as e:
            self._set_keys_msg(f"register failed: {e}", error=True)
            return
        self.query_one("#keys-paste", TextArea).text = ""
        for fid in ("#keys-id", "#keys-endpoint", "#keys-auth-env-key"):
            self.query_one(fid, Input).value = ""
        self._reload_keys()
        backed_up = "yes" if result.get("backed_up_credential_manager") else "no (non-Windows or cmdkey failed)"

        if result.get("llm_provider_registered"):
            self._set_keys_msg(f"registered {result['id']} — CredMan backup: {backed_up} — testing + pulling models...")
            self._pending_verify_provider = result["id"]
            self.run_worker(self._do_verify_llm_provider, thread=True, exclusive=True)
        else:
            self._set_keys_msg(f"registered {result['id']} ({result['key']}) — CredMan backup: {backed_up}")

    def _do_verify_llm_provider(self) -> None:
        provider_id = self._pending_verify_provider
        result = idx.refresh_provider_models(provider_id)
        self.call_from_thread(self._show_llm_verify_result, provider_id, result)

    def _show_llm_verify_result(self, provider_id: str, result: dict) -> None:
        self._reload_models()
        if result.get("ok"):
            self._set_keys_msg(f"{provider_id}: key verified, {result.get('model_count', 0)} models pulled — see Models tab")
        else:
            self._set_keys_msg(f"{provider_id}: registered, but verify failed: {result.get('error')}", error=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter-to-advance for the Keys pane's small fields — paste box stays
        multi-line (curl blobs need real newlines) so this only covers Id ->
        Auth env key -> Endpoint -> Register (+ auto-verify for LLM slots)."""
        chain = {"keys-id": "keys-auth-env-key", "keys-auth-env-key": "keys-endpoint"}
        widget_id = event.input.id or ""
        if widget_id in chain:
            self.query_one(f"#{chain[widget_id]}", Input).focus()
        elif widget_id == "keys-endpoint":
            self.action_register_key()
        elif widget_id == "archive-search":
            self.action_search_archive()

    def action_test_key(self) -> None:
        if not self._selected_slot_id:
            self._set_keys_msg("Arrow onto a slot row first (highlight = selected).", error=True)
            return
        sid = self._selected_slot_id
        # A freshly-registered generic-rest slot has no known request shape
        # (method/path) — the key alone never reveals that, same reason
        # category can't be inferred from it either (see the Keys pane's own
        # docs question this answers: an API key carries no metadata about
        # what the API does). These are ad-hoc per-test overrides, same as
        # `slots call --method --path` on the CLI — blank means "use whatever
        # the slot has stored." Pastebin preset stores POST + /api/api_post.php.
        method = self.query_one("#keys-test-method", Input).value.strip() or None
        path = self.query_one("#keys-test-path", Input).value.strip() or None
        result = call_slot(sid, method=method, path=path)
        prefix = f"[{sid}] "
        self._set_keys_msg(prefix + json.dumps(result)[:480], error=not result.get("ok"))

    def action_remove_key(self) -> None:
        if not self._selected_slot_id:
            self._set_keys_msg("Arrow onto a slot row to remove.", error=True)
            return
        from app.services.api_slot_registry import remove_slot

        sid = self._selected_slot_id
        if not remove_slot(sid):
            self._set_keys_msg(f"remove failed: {sid!r} not found", error=True)
            return
        self._selected_slot_id = None
        self._reload_keys()
        self._set_keys_msg(f"removed slot {sid}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "keys-table":
            self._selected_slot_id = str(event.row_key.value) if event.row_key.value is not None else None
        elif event.data_table.id == "aff-table":
            self._selected_affiliate_id = int(event.row_key.value) if event.row_key.value is not None else None
        elif event.data_table.id == "models-table":
            self._selected_model_id = str(event.row_key.value) if event.row_key.value is not None else None

    # ---- Affiliate links pane -------------------------------------------

    def _reload_affiliates(self) -> None:
        table = self.query_one("#aff-table", TruncatingDataTable)
        table.clear()
        try:
            rows = _list_affiliate_rows()
        except Exception as e:  # noqa: BLE001 — one pane's outage must not take down the whole app
            self._set_aff_msg(f"island API unreachable: {e}"[:300], error=True)
            return
        for row in rows:
            raw = (
                str(row["id"]), row["label"], row["url"], row["payout_kind"],
                str(row["priority_tier"]), "yes" if row["active"] else "no",
            )
            cells = [_truncate(v, w) for v, (_, w) in zip(raw, _AFF_COL_SPEC)]
            table.add_row(*cells, key=str(row["id"]))
            table.set_full_text(str(row["id"]), row["url"])

    def _set_aff_msg(self, text: str, *, error: bool = False) -> None:
        msg = self.query_one("#aff-msg", Static)
        msg.set_class(error, "error")
        msg.update(text)

    def action_add_affiliate(self) -> None:
        label = self.query_one("#aff-label", Input).value.strip()
        url = self.query_one("#aff-url", Input).value.strip()
        payout_kind = self.query_one("#aff-payout", Input).value.strip() or "other"
        priority_raw = self.query_one("#aff-priority", Input).value.strip() or "10"
        placements = [p.strip() for p in self.query_one("#aff-placements", Input).value.split(",") if p.strip()]

        if not label or not url:
            self._set_aff_msg("Label and URL are required.", error=True)
            return
        try:
            priority_tier = int(priority_raw)
        except ValueError:
            self._set_aff_msg("priority_tier must be an integer.", error=True)
            return

        payload = {
            "label": label, "url": url, "payout_kind": payout_kind, "priority_tier": priority_tier,
            "placements": placements or ["manual_only"],
        }
        try:
            r = httpx.post(f"{_island_api_base()}/promo-affiliate-links/", json=payload, timeout=15.0)
        except httpx.HTTPError as e:
            self._set_aff_msg(f"island API unreachable: {e}"[:300], error=True)
            return

        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except Exception:  # noqa: BLE001 — non-JSON error body
                detail = r.text
            self._set_aff_msg(f"rejected: {detail}"[:300], error=True)
            return

        for fid in ("#aff-label", "#aff-url"):
            self.query_one(fid, Input).value = ""
        self._reload_affiliates()
        self._set_aff_msg(f"added {label!r}")

    def action_copy_affiliate_url(self) -> None:
        if self._selected_affiliate_id is None:
            self._set_aff_msg("Select a link row first.", error=True)
            return
        table = self.query_one("#aff-table", TruncatingDataTable)
        full = table.get_full_text(self._selected_affiliate_id)
        if not full:
            self._set_aff_msg("No URL found for the selected row.", error=True)
            return
        self.copy_to_clipboard(full)
        self._set_aff_msg(f"copied: {full}")

    # ---- RSS feeds pane (research scanner sources) -----------------------

    def _reload_research(self) -> None:
        table = self.query_one("#rss-table", TruncatingDataTable)
        table.clear()
        try:
            rows = list_sources()
        except Exception as e:  # noqa: BLE001 — e.g. sources.json missing/malformed
            self._set_rss_msg(f"feed list unreadable: {e}"[:300], error=True)
            return
        for row in rows:
            raw = (row["id"], row["label"], row["lane"], row["url"])
            cells = [_truncate(v, w) for v, (_, w) in zip(raw, _RSS_COL_SPEC)]
            table.add_row(*cells, key=row["id"])
            table.set_full_text(row["id"], row["url"])

    def _set_rss_msg(self, text: str, *, error: bool = False) -> None:
        msg = self.query_one("#rss-msg", Static)
        msg.set_class(error, "error")
        msg.update(text)

    def action_add_feed(self) -> None:
        source_id = self.query_one("#rss-id", Input).value.strip()
        label = self.query_one("#rss-label", Input).value.strip()
        url = self.query_one("#rss-url", Input).value.strip()
        lane = self.query_one("#rss-lane", Select).value

        try:
            result = add_source(source_id=source_id, url=url, label=label, lane=str(lane))
        except ValueError as e:
            self._set_rss_msg(str(e), error=True)
            return

        for fid in ("#rss-id", "#rss-label", "#rss-url"):
            self.query_one(fid, Input).value = ""
        self._reload_research()
        self._set_rss_msg(f"added {result['id']!r} ({result['lane']}) — picked up on the next `research scan`")

    # ---- Archive pane (master capture archive, island-backed) -------------

    def _reload_archive(self, query: str = "") -> None:
        table = self.query_one("#archive-table", TruncatingDataTable)
        table.clear()
        self._archive_rows_cache.clear()
        try:
            rows = _list_archive_rows(query)
        except Exception as e:  # noqa: BLE001 — one pane's outage must not take down the whole app
            self._set_archive_msg(f"island API unreachable: {e}"[:300], error=True)
            return
        for row in rows:
            row_id = str(row.get("id"))
            title = row.get("summary") or ""
            raw = (row.get("kind", ""), title, row.get("value", ""), row.get("tags", ""))
            cells = [_truncate(v, w) for v, (_, w) in zip(raw, _ARCHIVE_COL_SPEC)]
            table.add_row(*cells, key=row_id)
            table.set_full_text(row_id, row.get("value", ""))
            self._archive_rows_cache[row_id] = row

    def _set_archive_msg(self, text: str, *, error: bool = False) -> None:
        msg = self.query_one("#archive-msg", Static)
        msg.set_class(error, "error")
        msg.update(text)

    def action_search_archive(self) -> None:
        query = self.query_one("#archive-search", Input).value.strip()
        self._reload_archive(query)
        self._set_archive_msg(f"{len(self._archive_rows_cache)} result(s)" if query else "showing recent entries")

    def action_add_archive_urls(self) -> None:
        text = self.query_one("#archive-paste", TextArea).text.strip()
        if not text:
            self._set_archive_msg("Paste one or more URLs first.", error=True)
            return
        urls = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("http://", "https://"))]
        if not urls:
            self._set_archive_msg("No http(s) URLs found in paste.", error=True)
            return
        payload = {"entries": [{"kind": "url", "value": u} for u in urls], "auto_tag": True}
        try:
            r = httpx.post(f"{_island_api_base()}/archive/entries/bulk", json=payload, timeout=30.0)
        except httpx.HTTPError as e:
            self._set_archive_msg(f"island API unreachable: {e}"[:300], error=True)
            return
        if r.status_code >= 400:
            self._set_archive_msg(f"rejected: {r.text[:200]}", error=True)
            return
        result = r.json()
        self.query_one("#archive-paste", TextArea).text = ""
        self._reload_archive()
        tagged = (result.get("auto_tag") or {}).get("enriched")
        tag_note = f", auto-tagged {tagged}" if tagged is not None else ""
        self._set_archive_msg(f"added {result.get('added', 0)} URL(s){tag_note}")

    def action_autotag_missing_archive(self) -> None:
        try:
            r = httpx.post(
                f"{_island_api_base()}/archive/entries/bulk/auto-tag",
                json={"missing_only": True, "limit": 24},
                timeout=45.0,
            )
        except httpx.HTTPError as e:
            self._set_archive_msg(f"island API unreachable: {e}"[:300], error=True)
            return
        if r.status_code >= 400:
            self._set_archive_msg(f"auto-tag failed: {r.text[:200]}", error=True)
            return
        result = r.json()
        self._reload_archive()
        self._set_archive_msg(f"auto-tagged {result.get('enriched', 0)} ({result.get('skipped', 0)} skipped)")

    def action_copy_archive_formatted(self) -> None:
        """OneTab-style export formats: "pipe" (Title | URL, OneTab's classic
        "copy all as text"), "title" (title only), "url" (bare URL), "rich"
        (Markdown link — the closest terminal-clipboard analog to OneTab's
        rich-text/HTML export, since a raw terminal can't carry real HTML)."""
        fmt = self.query_one("#archive-format", Input).value.strip().lower() or "pipe"
        if fmt not in _ARCHIVE_FORMATS:
            self._set_archive_msg(f"Unknown format {fmt!r} — use pipe/title/url/rich", error=True)
            return
        if not self._archive_rows_cache:
            self._set_archive_msg("Nothing to copy — search or add something first.", error=True)
            return
        lines: list[str] = []
        for row in self._archive_rows_cache.values():
            title = (row.get("summary") or "").strip()
            url = row.get("value") or ""
            if fmt == "pipe":
                lines.append(f"{title} | {url}" if title else url)
            elif fmt == "title":
                lines.append(title or url)
            elif fmt == "url":
                lines.append(url)
            else:  # rich
                lines.append(f"[{title or url}]({url})")
        self.copy_to_clipboard("\n".join(lines))
        self._set_archive_msg(f"copied {len(lines)} entries as {fmt!r}")

    # ---- Semantic scan pane ----------------------------------------------

    def action_run_scan(self) -> None:
        target = self.query_one("#scan-target", Input).value.strip()
        if not target:
            self.query_one("#scan-status", Static).update("Enter a path or URL first.")
            return
        self._start_scan(target, self_test=False)

    def action_run_selftest(self) -> None:
        self._start_scan("", self_test=True)

    def _start_scan(self, target: str, *, self_test: bool) -> None:
        script = _semantic_scan_script()
        if script is None:
            self.query_one("#scan-status", Static).update(
                "semantic_scan.py not found (set TBCC_SEMANTIC_SCAN_PATH or install the operator-cli skill)."
            )
            return
        self._scan_args = (target, self_test)
        self.query_one("#scan-status", Static).update("scanning...")
        self.run_worker(self._do_scan, thread=True, exclusive=True)

    def _do_scan(self) -> None:
        script = _semantic_scan_script()
        target, self_test = self._scan_args
        argv = ["--self-test"] if self_test else [target, "--json"]
        try:
            proc = subprocess.run(
                [sys.executable, str(script), *argv], capture_output=True, text=True, timeout=90, check=False
            )
            output = proc.stdout.strip()
            if not self_test:
                try:
                    output = json.dumps(json.loads(output), indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
            text = output or proc.stderr.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            status, text = "FAIL (timeout)", ""
        self.call_from_thread(self._show_scan_result, status, text)

    def _show_scan_result(self, status: str, text: str) -> None:
        self.query_one("#scan-status", Static).update(status)
        log = self.query_one("#scan-log", Log)
        log.clear()
        if text:
            log.write_lines(text.splitlines())

    # ---- dispatch ---------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "ask-run": self.action_run_ask,
            "ask-copy": self.action_copy_ask_reply,
            "models-refresh": self.action_refresh_models,
            "models-next": self._action_advance_sticky,
            "models-copy": self.action_copy_model,
            "keys-register": self.action_register_key,
            "keys-test": self.action_test_key,
            "keys-remove": self.action_remove_key,
            "aff-add": self.action_add_affiliate,
            "aff-copy": self.action_copy_affiliate_url,
            "scan-run": self.action_run_scan,
            "scan-selftest": self.action_run_selftest,
            "rss-add": self.action_add_feed,
            "archive-search-btn": self.action_search_archive,
            "archive-add": self.action_add_archive_urls,
            "archive-autotag": self.action_autotag_missing_archive,
            "archive-copy": self.action_copy_archive_formatted,
        }
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    def _action_advance_sticky(self) -> None:
        nxt = idx.advance_to_next()
        self.query_one("#models-status", Static).update(
            f"sticky -> {nxt['provider']}" if nxt else "no unexhausted provider available"
        )


def main() -> int:
    OperatorTuiApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
