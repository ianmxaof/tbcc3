"""RSS/Atom research scanner (app/services/research_scanner.py): fetch fault
isolation, SQLite dedupe, lane-scoped match-prompt building, and JSON-reply
parsing. No real network — httpx.get and the LLM fallback call are
monkeypatched; every test points TBCC_RESEARCH_SCANNER_DB at a throwaway
tmp_path file."""

from __future__ import annotations

import json

import pytest

from app.services import research_scanner as scanner


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_RESEARCH_SCANNER_DB", str(tmp_path / "research_scanner_test.sqlite3"))


class _FakeResponse:
    def __init__(self, status: int, content: bytes):
        self.status_code = status
        self.content = content
        self.is_success = 200 <= status < 300

    def __bool__(self):
        return self.is_success


_ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:example,2026:item-1</id>
    <title>Groq ships a new free-tier model</title>
    <link href="https://example.com/item-1"/>
    <summary>Details about the new model.</summary>
  </entry>
  <entry>
    <id>tag:example,2026:item-2</id>
    <title>Unrelated patch notes</title>
    <link href="https://example.com/item-2"/>
    <summary>Nothing to do with TBCC.</summary>
  </entry>
</feed>
"""


def _source(id_="github-test", lane="dev"):
    return scanner.FeedSource(id=id_, url="https://example.com/feed.atom", label="Test feed", lane=lane)


def test_load_sources_reads_real_config():
    sources = scanner.load_sources()
    assert len(sources) == 21
    assert all(s.lane in ("dev", "growth", "content") for s in sources)
    ids = [s.id for s in sources]
    assert len(ids) == len(set(ids))  # no duplicate ids


def test_fetch_source_parses_entries(monkeypatch):
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    result = scanner.fetch_source(_source())
    assert result["ok"] is True
    assert len(result["entries"]) == 2
    assert result["entries"][0]["item_id"] == "tag:example,2026:item-1"
    assert "Groq" in result["entries"][0]["title"]


def test_fetch_source_429_is_soft_failure(monkeypatch):
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(429, b""))
    result = scanner.fetch_source(_source())
    assert result["ok"] is False
    assert "429" in result["error"]


def test_fetch_source_network_error_isolated(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(scanner.httpx, "get", _boom)
    result = scanner.fetch_source(_source())
    assert result["ok"] is False
    assert "connection reset" in result["error"]


def test_fetch_all_sources_one_bad_does_not_block_others(monkeypatch):
    calls = []

    def _fake_get(url, **kwargs):
        calls.append(url)
        if "bad" in url:
            return _FakeResponse(500, b"")
        return _FakeResponse(200, _ATOM)

    monkeypatch.setattr(scanner.httpx, "get", _fake_get)
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)
    sources = [
        scanner.FeedSource(id="a", url="https://example.com/bad", label="A", lane="dev"),
        scanner.FeedSource(id="b", url="https://example.com/good", label="B", lane="dev"),
    ]
    results = scanner.fetch_all_sources(sources)
    assert results[0]["ok"] is False
    assert results[1]["ok"] is True
    assert len(calls) == 2


def test_fetch_all_sources_uses_longer_delay_for_reddit(monkeypatch):
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    sleeps = []
    monkeypatch.setattr(scanner.time, "sleep", lambda s: sleeps.append(s))
    sources = [
        scanner.FeedSource(id="a", url="https://github.com/x/y/releases.atom", label="A", lane="dev"),
        scanner.FeedSource(id="b", url="https://www.reddit.com/r/foo/.rss", label="B", lane="dev"),
        scanner.FeedSource(id="c", url="https://github.com/x/z/releases.atom", label="C", lane="dev"),
    ]
    scanner.fetch_all_sources(sources)
    # no sleep before the first fetch; reddit fetch gets the long delay, the
    # github fetch right after it gets the short baseline again
    assert sleeps == [scanner._REDDIT_FETCH_DELAY_SECONDS, scanner._FETCH_DELAY_SECONDS]


def test_mark_seen_dedupes():
    assert scanner.mark_seen("src", "item-1", title="t", link="l") is True
    assert scanner.mark_seen("src", "item-1", title="t", link="l") is False
    assert scanner.mark_seen("src", "item-2", title="t2", link="l2") is True


def test_mark_seen_dry_run_never_writes():
    assert scanner.mark_seen("src", "item-1", dry_run=True) is True
    # still "new" on a second dry-run call since nothing was persisted
    assert scanner.mark_seen("src", "item-1", dry_run=True) is True
    assert scanner.mark_seen("src", "item-1", dry_run=False) is True
    assert scanner.mark_seen("src", "item-1", dry_run=True) is False


def test_dedupe_new_items_carries_lane_and_label():
    sources_by_id = {"github-test": _source(lane="growth")}
    fetch_results = [
        {
            "source_id": "github-test",
            "ok": True,
            "entries": [{"item_id": "x1", "title": "T", "link": "L", "summary": "S"}],
        }
    ]
    new_items = scanner.dedupe_new_items(fetch_results, sources_by_id)
    assert len(new_items) == 1
    assert new_items[0]["lane"] == "growth"
    assert new_items[0]["source_label"] == "Test feed"

    # second call: nothing new
    assert scanner.dedupe_new_items(fetch_results, sources_by_id) == []


def test_dedupe_new_items_skips_failed_sources():
    fetch_results = [{"source_id": "x", "ok": False, "error": "boom"}]
    assert scanner.dedupe_new_items(fetch_results, {}) == []


def test_build_match_prompt_only_uses_dev_lane():
    items = [
        {"item_id": "1", "title": "Dev thing", "link": "l1", "source_label": "S1", "lane": "dev"},
        {"item_id": "2", "title": "Growth thing", "link": "l2", "source_label": "S2", "lane": "growth"},
        {"item_id": "3", "title": "TG content", "link": "l3", "source_label": "S3", "lane": "content"},
    ]
    prompt = scanner.build_match_prompt(items)
    assert prompt is not None
    system, user = prompt
    assert "Dev thing" in user
    assert "Growth thing" not in user
    assert "TG content" not in user


def test_build_match_prompt_none_when_no_dev_items():
    items = [{"item_id": "2", "title": "Growth thing", "link": "l2", "source_label": "S2", "lane": "growth"}]
    assert scanner.build_match_prompt(items) is None


def test_sprint_state_context_pulls_real_sections():
    ctx = scanner._sprint_state_context()
    assert "In flight" in ctx or ctx == ""  # empty only if SPRINT_STATE.md genuinely missing
    if ctx:
        assert "Deferred" not in ctx  # explicitly excluded — "don't ladder without why now"


def test_parse_match_reply_plain_json():
    reply = '[{"item_id": "1", "target": "Foo", "why": "bar"}]'
    out = scanner.parse_match_reply(reply)
    assert out == [{"item_id": "1", "target": "Foo", "why": "bar"}]


def test_parse_match_reply_strips_code_fence():
    reply = '```json\n[{"item_id": "1", "target": "Foo", "why": "bar"}]\n```'
    out = scanner.parse_match_reply(reply)
    assert out == [{"item_id": "1", "target": "Foo", "why": "bar"}]


def test_parse_match_reply_empty_array():
    assert scanner.parse_match_reply("[]") == []


def test_parse_match_reply_malformed_fails_open():
    assert scanner.parse_match_reply("not json at all") == []
    assert scanner.parse_match_reply("") == []
    assert scanner.parse_match_reply('{"not": "a list"}') == []


def test_parse_match_reply_drops_rows_missing_required_fields():
    reply = json.dumps([{"item_id": "1"}, {"target": "no id"}, {"item_id": "2", "target": "ok"}])
    out = scanner.parse_match_reply(reply)
    assert out == [{"item_id": "2", "target": "ok", "why": ""}]


def test_run_scan_seed_mode_skips_match_pass(monkeypatch):
    monkeypatch.setattr(scanner, "load_sources", lambda: [_source()])
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)

    report = scanner.run_scan(seed=True)
    assert report["seeded"] is True
    assert report["new_items_total"] == 2
    assert report["matches"] == []
    # seeded twice in a row: second run sees 0 new (dedupe persisted)
    report2 = scanner.run_scan(seed=True)
    assert report2["new_items_total"] == 0


def test_run_scan_calls_fallback_chain_and_records_matches(monkeypatch):
    monkeypatch.setattr(scanner, "load_sources", lambda: [_source()])
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)

    calls = []

    async def _fake_fallback(messages, *, primary, max_tokens, temperature, timeout):
        calls.append(messages)
        return json.dumps([{"item_id": "tag:example,2026:item-1", "target": "LLM router", "why": "new free tier"}])

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", _fake_fallback)

    report = scanner.run_scan(seed=False)
    assert len(calls) == 1
    assert report["new_items_total"] == 2
    assert len(report["matches"]) == 1
    assert report["matches"][0]["target"] == "LLM router"

    with scanner.closing(scanner._connect()) as conn:
        row = conn.execute("SELECT * FROM matches").fetchone()
    assert row is not None
    assert row["target"] == "LLM router"


def test_run_scan_dry_run_persists_nothing(monkeypatch):
    monkeypatch.setattr(scanner, "load_sources", lambda: [_source()])
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)

    async def _fake_fallback(messages, *, primary, max_tokens, temperature, timeout):
        return json.dumps([{"item_id": "tag:example,2026:item-1", "target": "X", "why": "y"}])

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", _fake_fallback)

    report = scanner.run_scan(dry_run=True)
    assert report["new_items_total"] == 2
    assert len(report["matches"]) == 1

    # nothing persisted — a real run afterward sees the same items as new again
    report2 = scanner.run_scan(dry_run=True)
    assert report2["new_items_total"] == 2

    with scanner.closing(scanner._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM seen_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0


def test_run_scan_match_failure_reported_not_raised(monkeypatch):
    monkeypatch.setattr(scanner, "load_sources", lambda: [_source()])
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)

    async def _fake_fallback(*a, **k):
        raise RuntimeError("all providers refused")

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", _fake_fallback)

    report = scanner.run_scan()
    assert report["ok"] is True
    assert report["matches"] == []
    assert "all providers refused" in report["match_error"]


def test_run_scan_growth_and_content_lanes_never_reach_the_match_prompt(monkeypatch):
    sources = [_source(id_="a", lane="growth"), _source(id_="b", lane="content")]
    monkeypatch.setattr(scanner, "load_sources", lambda: sources)
    monkeypatch.setattr(scanner.httpx, "get", lambda *a, **k: _FakeResponse(200, _ATOM))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)

    called = {"n": 0}

    async def _fake_fallback(*a, **k):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", _fake_fallback)

    report = scanner.run_scan()
    assert called["n"] == 0  # no dev-lane items -> no LLM call at all
    assert report["new_items_total"] == 4  # 2 sources x 2 entries each
    assert len(report["other_signal"]) == 4


_SEED_SOURCES_JSON = """{
  "_comment": "test fixture",
  "sources": [
    {"id": "seed-a", "url": "https://example.com/seed-a.atom", "label": "Seed A", "lane": "dev"}
  ]
}
"""


@pytest.fixture
def _sources_file(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    path.write_text(_SEED_SOURCES_JSON, encoding="utf-8")
    monkeypatch.setenv("TBCC_RESEARCH_SCANNER_SOURCES", str(path))
    return path


def test_list_sources_reads_seed_file(_sources_file):
    rows = scanner.list_sources()
    assert rows == [{"id": "seed-a", "url": "https://example.com/seed-a.atom", "label": "Seed A", "lane": "dev"}]


def test_add_source_appends_and_is_loadable(_sources_file):
    result = scanner.add_source(source_id="new-b", url="https://example.com/new-b.atom", label="New B", lane="growth")
    assert result == {"id": "new-b", "url": "https://example.com/new-b.atom", "label": "New B", "lane": "growth"}

    rows = scanner.list_sources()
    assert [r["id"] for r in rows] == ["seed-a", "new-b"]

    # round-trips through load_sources() (FeedSource dataclass), not just list_sources()
    sources = scanner.load_sources()
    assert [s.id for s in sources] == ["seed-a", "new-b"]

    # original entry + JSON structure untouched
    payload = json.loads(_sources_file.read_text(encoding="utf-8"))
    assert payload["_comment"] == "test fixture"
    assert payload["sources"][0]["id"] == "seed-a"


def test_add_source_rejects_duplicate_id(_sources_file):
    with pytest.raises(ValueError, match="already registered"):
        scanner.add_source(source_id="seed-a", url="https://example.com/different.atom", label="Dup", lane="dev")
    assert len(scanner.list_sources()) == 1


def test_add_source_rejects_duplicate_url(_sources_file):
    with pytest.raises(ValueError, match="already registered"):
        scanner.add_source(source_id="different-id", url="https://example.com/seed-a.atom", label="Dup", lane="dev")
    assert len(scanner.list_sources()) == 1


def test_add_source_rejects_invalid_lane(_sources_file):
    with pytest.raises(ValueError, match="lane must be one of"):
        scanner.add_source(source_id="bad-lane", url="https://example.com/bad.atom", label="Bad", lane="nope")
    assert len(scanner.list_sources()) == 1


def test_add_source_rejects_missing_fields(_sources_file):
    with pytest.raises(ValueError, match="id required"):
        scanner.add_source(source_id="", url="https://example.com/x.atom", label="X", lane="dev")
    with pytest.raises(ValueError, match="url required"):
        scanner.add_source(source_id="x", url="", label="X", lane="dev")
    with pytest.raises(ValueError, match="label required"):
        scanner.add_source(source_id="x", url="https://example.com/x.atom", label="", lane="dev")
