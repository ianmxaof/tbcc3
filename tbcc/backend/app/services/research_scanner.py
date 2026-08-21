"""RSS/Atom research scanner — fetches external dev-tooling/growth signal and
cross-references new dev-lane items against SPRINT_STATE.md's open work using
TBCC's own LLM fallback chain (complete_chat_text_with_fallback — the same
stateless function `tbcc_cli.py ask` uses, never the sticky `llm ask` cursor,
so an unattended cron run can't repoint the operator's interactive rotator).

Local-only: dedupe/match store lives in tbcc/.tbcc-run/ (gitignored), same
convention as llm_model_index.py. Delivered through a Hermes local skill
(tbcc/docs/hermes-skills/tbcc-research-scanner/), not Celery/island — this is
operator research signal, not a revenue metric (cloud-only-money doctrine
keeps unrelated cron/secrets off the paid VPS).

Reviewed by Cursor 2026-08-21 before build (RC1-RC6, all confirmed/adjusted).
Only `lane: "dev"` items go through the LLM match pass — growth/content lane
items are still fetched, deduped, and reported, just not matched against
SPRINT_STATE yet (per review: r/DailyTelegramSexting is a poor match-prompt
fit; growth subs share the pipeline until match noise justifies a split).
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import httpx

_USER_AGENT = "Mozilla/5.0 (compatible; tbcc-research-scanner/0.1; +https://api.powercore.app)"
# Reddit's r/<sub>/.rss rate-limits hard and it isn't just per-request spacing:
# two live 21-source runs (2026-08-21) measured a flat 3s delay 429ing 10 of
# 11 reddit.com sources, and a 20s delay still only cleared 6 of 15 — better,
# but well short of reliable coverage for 15 subs in one run. GitHub/HN never
# 429'd once at any delay, so the delay stays domain-aware (short baseline
# everywhere, 20s before reddit.com) rather than punishing every source for
# Reddit's limit. This is accepted as-is for v1: a source that still 429s is
# a soft failure (see fetch_source), retried automatically on the next
# scheduled run, so coverage self-heals across days even though any single
# day's Reddit signal is partial. If reliable same-day Reddit coverage
# matters later, that's a real case for routing reddit.com sources through
# RSSHub specifically — deferred, not attempted here.
_FETCH_DELAY_SECONDS = 2.0
_REDDIT_FETCH_DELAY_SECONDS = 20.0
_SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "research_scanner_sources.json"
_SPRINT_STATE_PATH = Path(__file__).resolve().parents[3] / "docs" / "SPRINT_STATE.md"


@dataclass(frozen=True)
class FeedSource:
    id: str
    url: str
    label: str
    lane: str


def load_sources() -> list[FeedSource]:
    data = json.loads(_SOURCES_PATH.read_text(encoding="utf-8"))
    return [FeedSource(id=s["id"], url=s["url"], label=s["label"], lane=s["lane"]) for s in data["sources"]]


def _db_path() -> Path:
    override = (os.getenv("TBCC_RESEARCH_SCANNER_DB") or "").strip()
    if override:
        return Path(override)
    # this file: tbcc/backend/app/services/research_scanner.py -> tbcc/.tbcc-run/
    tbcc_root = Path(__file__).resolve().parents[3]
    return tbcc_root / ".tbcc-run" / "research_scanner.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS seen_items (
            source_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            title TEXT,
            link TEXT,
            first_seen TEXT NOT NULL,
            PRIMARY KEY (source_id, item_id)
        );
        CREATE TABLE IF NOT EXISTS matches (
            source_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            matched_at TEXT NOT NULL,
            target TEXT,
            why TEXT,
            PRIMARY KEY (source_id, item_id)
        );
        """
    )
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry_id(entry: dict) -> str:
    return str(entry.get("id") or entry.get("link") or entry.get("title") or "").strip()


def fetch_source(source: FeedSource, *, timeout: float = 20.0) -> dict[str, Any]:
    """One source, fully fault-isolated — a bad/rate-limited feed never blocks
    the rest of the run; it's just retried on the next scheduled run."""
    try:
        r = httpx.get(
            source.url,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
    except Exception as e:  # noqa: BLE001 — fault-isolate one source from the rest of the run
        return {"source_id": source.id, "ok": False, "error": str(e)[:300]}

    if r.status_code == 429:
        return {"source_id": source.id, "ok": False, "error": "429 rate limited — retry next run"}
    if not r.is_success:
        return {"source_id": source.id, "ok": False, "error": f"HTTP {r.status_code}"}

    parsed = feedparser.parse(r.content)
    entries: list[dict[str, str]] = []
    for e in parsed.get("entries") or []:
        eid = _entry_id(e)
        if not eid:
            continue
        entries.append(
            {
                "item_id": eid,
                "title": str(e.get("title") or "").strip(),
                "link": str(e.get("link") or "").strip(),
                "summary": str(e.get("summary") or "").strip()[:600],
            }
        )
    return {"source_id": source.id, "ok": True, "entries": entries}


def _is_reddit(url: str) -> bool:
    return "reddit.com" in url


def fetch_all_sources(sources: list[FeedSource] | None = None, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    out = []
    for i, source in enumerate(sources or load_sources()):
        if i > 0:
            time.sleep(_REDDIT_FETCH_DELAY_SECONDS if _is_reddit(source.url) else _FETCH_DELAY_SECONDS)
        out.append(fetch_source(source, timeout=timeout))
    return out


def mark_seen(source_id: str, item_id: str, *, title: str = "", link: str = "", dry_run: bool = False) -> bool:
    """Returns True when this item is genuinely new. dry_run never writes —
    used to preview a run without mutating the dedupe store."""
    with closing(_connect()) as conn:
        if dry_run:
            row = conn.execute(
                "SELECT 1 FROM seen_items WHERE source_id = ? AND item_id = ?", (source_id, item_id)
            ).fetchone()
            return row is None
        cur = conn.execute(
            "INSERT OR IGNORE INTO seen_items (source_id, item_id, title, link, first_seen) VALUES (?, ?, ?, ?, ?)",
            (source_id, item_id, title, link, _now_iso()),
        )
        conn.commit()
        return cur.rowcount > 0


def dedupe_new_items(
    fetch_results: list[dict[str, Any]],
    sources_by_id: dict[str, FeedSource],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Marks every fetched entry seen (unless dry_run); returns only the
    genuinely-new ones, each carrying its source's lane and label."""
    new_items: list[dict[str, Any]] = []
    for result in fetch_results:
        if not result.get("ok"):
            continue
        source = sources_by_id.get(result["source_id"])
        lane = source.lane if source else "dev"
        label = source.label if source else result["source_id"]
        for entry in result.get("entries") or []:
            is_new = mark_seen(
                result["source_id"], entry["item_id"], title=entry["title"], link=entry["link"], dry_run=dry_run
            )
            if is_new:
                new_items.append({**entry, "source_id": result["source_id"], "source_label": label, "lane": lane})
    return new_items


def record_match(source_id: str, item_id: str, *, target: str, why: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO matches (source_id, item_id, matched_at, target, why) VALUES (?, ?, ?, ?, ?)",
            (source_id, item_id, _now_iso(), target, why),
        )
        conn.commit()


def _sprint_state_context(*, max_chars: int = 6000) -> str:
    """In-flight + Blocked-on + Do-not-touch sections only — Deferred is
    explicitly 'don't ladder without why now', not open work to match against."""
    try:
        text = _SPRINT_STATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    sections = []
    for heading in ("## In flight", "## Blocked on", "## Do not touch"):
        start = text.find(heading)
        if start == -1:
            continue
        end = text.find("\n## ", start + len(heading))
        sections.append(text[start : end if end != -1 else len(text)])
    return "\n\n".join(sections)[:max_chars]


def build_match_prompt(new_items: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(system, user) for one batched fallback-chain call — only dev-lane items
    are matched against SPRINT_STATE. Returns None when there's nothing to match."""
    dev_items = [it for it in new_items if it.get("lane") == "dev"]
    if not dev_items:
        return None
    context = _sprint_state_context()
    system = (
        "You are a research-signal matcher for the TBCC/AOF engineering project. "
        "You are given (1) a snapshot of the project's current open work and "
        "(2) a list of new items from external feeds (GitHub releases, dev-tooling "
        "news, free-API trackers). For each feed item that plausibly helps solve, "
        "unblock, or informs an OPEN item, output one match. Do not force matches "
        "— most items will have none. Output ONLY a JSON array, no prose, no "
        'markdown fences. Each element: {"item_id": <the item_id given>, "target": '
        '<short name of the open item it relates to>, "why": <one sentence>}. '
        "Output [] if nothing matches."
    )
    lines = [f"OPEN WORK:\n{context}\n\nNEW FEED ITEMS:"]
    for it in dev_items:
        lines.append(f"- item_id={it['item_id']} | {it['source_label']} | {it['title']} | {it['link']}")
    return system, "\n".join(lines)


def parse_match_reply(reply: str) -> list[dict[str, str]]:
    """Strips ``` fences if present, then parses the model's JSON array. Never
    raises — a malformed reply just yields no matches (fail open, not fail
    loud, for an unattended cron job)."""
    text = (reply or "").strip()
    if text.startswith("```"):
        text = text[3:]
        if text.strip().lower().startswith("json"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        target = str(row.get("target") or "").strip()
        why = str(row.get("why") or "").strip()
        if item_id and target:
            out.append({"item_id": item_id, "target": target, "why": why})
    return out


def run_scan(
    *,
    seed: bool = False,
    dry_run: bool = False,
    fetch_timeout: float = 20.0,
    ask_timeout: float = 90.0,
) -> dict[str, Any]:
    sources = load_sources()
    sources_by_id = {s.id: s for s in sources}
    fetch_results = fetch_all_sources(sources, timeout=fetch_timeout)
    new_items = dedupe_new_items(fetch_results, sources_by_id, dry_run=dry_run)

    report: dict[str, Any] = {
        "ok": True,
        "generated_at": _now_iso(),
        "seeded": seed,
        "dry_run": dry_run,
        "sources": [
            {"source_id": r["source_id"], "ok": r["ok"], "error": r.get("error")} for r in fetch_results
        ],
        "new_items_total": len(new_items),
        "matches": [],
        "other_signal": [],
    }

    if seed:
        return report

    dev_new = [it for it in new_items if it["lane"] == "dev"]
    other_new = [it for it in new_items if it["lane"] != "dev"]
    report["other_signal"] = [
        {"source_label": it["source_label"], "title": it["title"], "link": it["link"], "lane": it["lane"]}
        for it in other_new
    ][:20]

    prompt = build_match_prompt(new_items)
    if not dev_new or prompt is None:
        return report
    system, user = prompt

    try:
        from app.services.llm_provider_fallback import complete_chat_text_with_fallback

        reply = asyncio.run(
            complete_chat_text_with_fallback(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                primary=None,
                max_tokens=1200,
                temperature=0.2,
                timeout=ask_timeout,
            )
        )
    except Exception as e:
        report["match_error"] = str(e)[:300]
        return report

    matched = parse_match_reply(reply)
    by_id = {it["item_id"]: it for it in dev_new}
    matches_out = []
    for m in matched:
        it = by_id.get(m["item_id"])
        if not it:
            continue
        if not dry_run:
            record_match(it["source_id"], it["item_id"], target=m["target"], why=m["why"])
        matches_out.append(
            {
                "source_label": it["source_label"],
                "title": it["title"],
                "link": it["link"],
                "target": m["target"],
                "why": m["why"],
            }
        )
    report["matches"] = matches_out
    return report
