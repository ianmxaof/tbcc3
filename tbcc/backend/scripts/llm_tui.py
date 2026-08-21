"""Interactive terminal viewer over the local LLM model/provider index
(app/services/llm_model_index.py). Devops-only — requires `textual`
(tbcc/backend/requirements-dev.txt, not shipped to the island).

Run via: py -3.13 scripts/tbcc_cli.py llm tui
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

from app.services import llm_model_index as idx

_COLUMNS = (
    "Provider",
    "Model",
    "Ctx",
    "Owner",
    "Stale",
    "Exhausted",
    "Usage left",
    "Fetched",
)


def _fmt_row(row: dict) -> tuple[str, ...]:
    ctx = f"{row['context_length']:,}" if row["context_length"] else "—"
    usage = "—"
    if row["usage_remaining"] is not None:
        limit = row["usage_limit"]
        usage = f"{row['usage_remaining']:,.2f}" + (f" / {limit:,.2f}" if limit is not None else "")
    fetched = (row["fetched_at"] or "")[:19].replace("T", " ")
    return (
        row["provider"],
        row["model_id"],
        ctx,
        row["owned_by"] or "—",
        "yes" if row["stale"] else "",
        "yes" if row["exhausted"] else "",
        usage,
        fetched,
    )


class LlmModelIndexApp(App):
    """Master collection index of every model TBCC can reach, at a glance."""

    CSS = """
    #status { padding: 0 1; color: $text-muted; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh (hits every provider)"),
        Binding("n", "advance", "Cycle sticky -> next"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Vertical(
            Static("", id="status"),
            DataTable(id="table", zebra_stripes=True, cursor_type="row"),
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*_COLUMNS)
        self._reload()

    def _status_text(self) -> str:
        sticky = idx.get_sticky()
        sticky_s = f"sticky: {sticky['provider']}" if sticky and sticky.get("provider") else "sticky: (none)"
        return f"{sticky_s}   |   [r] refresh   [n] cycle sticky   [q] quit"

    def _reload(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for row in idx.list_models():
            table.add_row(*_fmt_row(row))
        self.query_one("#status", Static).update(self._status_text())

    def action_advance(self) -> None:
        nxt = idx.advance_to_next()
        self.query_one("#status", Static).update(
            f"sticky -> {nxt['provider']}" if nxt else "no unexhausted provider available"
        )

    def action_refresh(self) -> None:
        self.query_one("#status", Static).update("refreshing... (hitting every provider's /models)")
        self.run_worker(self._do_refresh, thread=True, exclusive=True)

    def _do_refresh(self) -> None:
        idx.refresh_all_providers()
        self.call_from_thread(self._reload)


def main() -> int:
    LlmModelIndexApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
