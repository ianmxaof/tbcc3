"""Local, PC-only catalog of TBCC's configured LLM providers/models plus
usage/exhaustion tracking, for devops CLI use (`tbcc_cli.py llm ...`).

Scope: this SQLite file lives on the operator's machine (`tbcc/.tbcc-run/`,
gitignored) and is read/written only by the CLI. It is NOT used by
`/zeus/v1/ask` (app/api/zeus_llm.py) or the MCP `ask_llm` tool — those run
on the island where this file does not exist, and must stay stateless so an
agent calling them always gets the caller's explicit provider/model, never
whatever the operator last cycled to on their own PC.

Exhaustion classification is deliberately conservative (see classify_failure):
only an actual quota/rate-limit signal marks a provider exhausted. A 404
(dead/renamed model id) marks just that model stale, not the provider —
conflating the two would have silently blacklisted Groq and DeepInfra this
session over stale hardcoded defaults, not real exhaustion. Empty-content and
timeout failures (e.g. a reasoning model burning its budget on hidden
reasoning tokens before visible output) record nothing — they are not a
usage signal at all.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from app.services.llm_completions import (
    TextLlmRuntime,
    chat_completions_headers,
    resolve_text_llm_runtime,
)
from app.services.llm_provider_fallback import DEFAULT_CHAIN

FailureKind = Literal["quota", "model_not_found", "transient"]

_QUOTA_HINTS = (
    "insufficient_quota",
    "insufficient_user_quota",
    "quota_exceeded",
    "rate_limit_exceeded",
    "rate limit",
    "out of credits",
    "exceeded your current quota",
    "billing",
)

_ALL_PROVIDERS = (*DEFAULT_CHAIN, "openai")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _db_path() -> Path:
    override = (os.getenv("TBCC_LLM_INDEX_DB") or "").strip()
    if override:
        return Path(override)
    # this file: tbcc/backend/app/services/llm_model_index.py -> tbcc/.tbcc-run/
    tbcc_root = Path(__file__).resolve().parents[3]
    return tbcc_root / ".tbcc-run" / "llm_model_index.sqlite3"


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
        CREATE TABLE IF NOT EXISTS models (
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            raw_json TEXT,
            stale INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (provider, model_id)
        );
        CREATE TABLE IF NOT EXISTS provider_state (
            provider TEXT PRIMARY KEY,
            configured INTEGER,
            models_endpoint_ok INTEGER,
            models_error TEXT,
            exhausted_until TEXT,
            exhausted_reason TEXT,
            usage_remaining REAL,
            usage_limit REAL,
            usage_checked_at TEXT,
            last_refreshed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cursor (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            provider TEXT,
            model_id TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()


def _upsert_provider_state(conn: sqlite3.Connection, provider: str, **fields: Any) -> None:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
    conn.execute(
        f"INSERT INTO provider_state (provider, {cols}) VALUES (?, {placeholders}) "
        f"ON CONFLICT(provider) DO UPDATE SET {updates}",
        (provider, *fields.values()),
    )


def classify_failure(exc: BaseException) -> FailureKind:
    """quota -> mark provider exhausted; model_not_found -> mark just that model
    stale; transient (auth errors, empty content, timeouts) -> no state change."""
    msg = str(exc).lower()
    m = re.match(r"llm error (\d+):", msg)
    status = int(m.group(1)) if m else None
    if status == 404:
        return "model_not_found"
    if status == 429:
        return "quota"
    if status in (401, 403):
        return "transient"
    if any(hint in msg for hint in _QUOTA_HINTS):
        return "quota"
    return "transient"


def record_failure(provider: str, model: str | None, exc: BaseException) -> FailureKind:
    kind = classify_failure(exc)
    now = _now_iso()
    with closing(_connect()) as conn:
        if kind == "quota":
            reset = _now() + timedelta(hours=24)
            _upsert_provider_state(
                conn,
                provider,
                exhausted_until=reset.isoformat(),
                exhausted_reason=str(exc)[:300],
                last_refreshed_at=now,
            )
        elif kind == "model_not_found" and model:
            conn.execute(
                "UPDATE models SET stale = 1 WHERE provider = ? AND model_id = ?",
                (provider, model),
            )
        conn.commit()
    return kind


def _models_url(rt: TextLlmRuntime) -> str:
    base = (rt.base_url or "").rstrip("/")
    return f"{base}/models"


def refresh_provider_models(provider: str, *, timeout: float = 20.0) -> dict[str, Any]:
    now = _now_iso()
    try:
        rt = resolve_text_llm_runtime(provider=provider)
    except RuntimeError as e:
        with closing(_connect()) as conn:
            _upsert_provider_state(conn, provider, configured=0, last_refreshed_at=now)
            conn.commit()
        return {"provider": provider, "configured": False, "ok": False, "error": str(e)}

    result: dict[str, Any] = {"provider": provider, "configured": True}
    try:
        r = httpx.get(_models_url(rt), headers=chat_completions_headers(rt), timeout=timeout)
        r.raise_for_status()
        data = r.json()
        rows = data.get("data") if isinstance(data, dict) else data
        rows = rows if isinstance(rows, list) else []
        with closing(_connect()) as conn:
            for row in rows:
                mid = str((row or {}).get("id") or "").strip()
                if not mid:
                    continue
                conn.execute(
                    "INSERT INTO models (provider, model_id, raw_json, stale, fetched_at) "
                    "VALUES (?, ?, ?, 0, ?) "
                    "ON CONFLICT(provider, model_id) DO UPDATE SET "
                    "raw_json=excluded.raw_json, stale=0, fetched_at=excluded.fetched_at",
                    (provider, mid, json.dumps(row), now),
                )
            _upsert_provider_state(
                conn,
                provider,
                configured=1,
                models_endpoint_ok=1,
                models_error=None,
                last_refreshed_at=now,
            )
            conn.commit()
        result.update(ok=True, model_count=len(rows))
    except Exception as e:  # noqa: BLE001 — fault-isolate one provider from the rest of the refresh loop
        with closing(_connect()) as conn:
            _upsert_provider_state(
                conn,
                provider,
                configured=1,
                models_endpoint_ok=0,
                models_error=str(e)[:300],
                last_refreshed_at=now,
            )
            conn.commit()
        result.update(ok=False, error=str(e)[:300])
    return result


def _refresh_openrouter_usage(*, timeout: float = 20.0) -> None:
    try:
        rt = resolve_text_llm_runtime(provider="openrouter")
    except RuntimeError:
        return
    now = _now_iso()
    try:
        r = httpx.get(
            f"{(rt.base_url or '').rstrip('/')}/key",
            headers={"Authorization": f"Bearer {rt.api_key}"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = (r.json() or {}).get("data") or {}
        with closing(_connect()) as conn:
            _upsert_provider_state(
                conn,
                "openrouter",
                usage_remaining=data.get("limit_remaining"),
                usage_limit=data.get("limit"),
                usage_checked_at=now,
            )
            conn.commit()
    except Exception:
        pass


def refresh_all_providers(*, timeout: float = 20.0) -> list[dict[str, Any]]:
    out = [refresh_provider_models(pid, timeout=timeout) for pid in _ALL_PROVIDERS]
    _refresh_openrouter_usage(timeout=timeout)
    return out


def is_exhausted(provider: str) -> bool:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT exhausted_until FROM provider_state WHERE provider = ?", (provider,)
        ).fetchone()
    if not row or not row["exhausted_until"]:
        return False
    try:
        until = datetime.fromisoformat(row["exhausted_until"])
    except ValueError:
        return False
    return _now() < until


def provider_status(provider: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM provider_state WHERE provider = ?", (provider,)).fetchone()
        model_count = conn.execute(
            "SELECT COUNT(*) FROM models WHERE provider = ? AND stale = 0", (provider,)
        ).fetchone()[0]
    d = dict(row) if row else {"provider": provider}
    d["exhausted"] = is_exhausted(provider)
    d["model_count"] = model_count
    return d


def all_provider_status() -> list[dict[str, Any]]:
    return [provider_status(pid) for pid in _ALL_PROVIDERS]


def rank_providers_for_cycle(*, exclude: str | None = None) -> list[dict[str, Any]]:
    """Primary signal: skip exhausted providers entirely. Secondary: providers
    with a known numeric usage_remaining (currently only OpenRouter exposes
    one — CometAPI's quota fetcher lives outside this fallback chain) sort
    first by remaining amount; everyone else keeps DEFAULT_CHAIN order as an
    'unknown, not yet observed exhausted' tier — this is the primary lane in
    practice, not the numeric one."""
    with closing(_connect()) as conn:
        rows = {r["provider"]: dict(r) for r in conn.execute("SELECT * FROM provider_state")}
    numeric: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for idx, pid in enumerate(_ALL_PROVIDERS):
        if pid == exclude:
            continue
        st = rows.get(pid, {})
        if st.get("configured") == 0:
            continue
        if is_exhausted(pid):
            continue
        usage_remaining = st.get("usage_remaining")
        entry = {"provider": pid, "usage_remaining": usage_remaining, "order": idx}
        (numeric if usage_remaining is not None else unknown).append(entry)
    numeric.sort(key=lambda e: e["usage_remaining"], reverse=True)
    unknown.sort(key=lambda e: e["order"])
    return numeric + unknown


def get_sticky() -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT provider, model_id, updated_at FROM cursor WHERE id = 1").fetchone()
    return dict(row) if row else None


def set_sticky(provider: str, model_id: str | None) -> None:
    now = _now_iso()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO cursor (id, provider, model_id, updated_at) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET provider=excluded.provider, model_id=excluded.model_id, "
            "updated_at=excluded.updated_at",
            (provider, model_id, now),
        )
        conn.commit()


def advance_to_next() -> dict[str, Any] | None:
    current = get_sticky()
    exclude = current["provider"] if current else None
    ranked = rank_providers_for_cycle(exclude=exclude)
    if not ranked:
        return None
    nxt = ranked[0]
    set_sticky(nxt["provider"], None)
    return nxt
