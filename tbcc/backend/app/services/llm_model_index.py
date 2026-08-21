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
    is_openrouter_free_model,
    resolve_text_llm_runtime,
)
from app.services.llm_provider_fallback import DEFAULT_CHAIN

FailureKind = Literal["quota", "model_not_found", "transient"]

# Credit/billing exhaustion resets on the provider's own cycle (assume ~daily);
# a bare rate limit is usually per-minute — penalizing it for 24h like a real
# credit exhaustion would blacklist a provider over one burst of calls.
_RATE_LIMIT_HINTS = ("rate_limit_exceeded", "rate limit")
_CREDIT_HINTS = (
    "insufficient_quota",
    "insufficient_user_quota",
    "quota_exceeded",
    "out of credits",
    "exceeded your current quota",
    "billing",
)
_QUOTA_HINTS = _RATE_LIMIT_HINTS + _CREDIT_HINTS

_BUILTIN_PROVIDERS = (*DEFAULT_CHAIN, "openai")

# Heuristic only — matches the operator's own vocabulary for the opt-in
# --prefer-uncensored lane. Off by default: most devops calls just need a
# working model, not this (see module docstring / pick_best_model_for_provider).
_UNCENSORED_HINTS = ("dolphin", "hermes", "abliterat", "uncensor", "heretic")


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
        CREATE TABLE IF NOT EXISTS credentials (
            provider TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            base_url TEXT,
            added_at TEXT NOT NULL
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


def set_credential(provider: str, api_key: str, base_url: str | None = None) -> None:
    """Store a key for `provider` — a built-in (overrides its env var inside the
    rotator only; production paths never read this table) or a wholly new
    custom/HuggingFace-style endpoint (base_url required, since there's no
    hardcoded default to fall back on). Same plaintext-local-file posture as
    tbcc/.env: this file lives in tbcc/.tbcc-run/, gitignored, never printed."""
    now = _now_iso()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO credentials (provider, api_key, base_url, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, base_url=excluded.base_url, "
            "added_at=excluded.added_at",
            (provider, api_key, base_url, now),
        )
        conn.commit()


def remove_credential(provider: str) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM credentials WHERE provider = ?", (provider,))
        conn.commit()
        return cur.rowcount > 0


def _get_credential(provider: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT provider, api_key, base_url FROM credentials WHERE provider = ?", (provider,)
        ).fetchone()
    return dict(row) if row else None


def list_credentials() -> list[dict[str, Any]]:
    """provider/base_url/added_at only — api_key is deliberately never selected
    here so it can never end up in `llm keys list` output or a --json dump."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT provider, base_url, added_at FROM credentials ORDER BY provider"
        ).fetchall()
    return [dict(r) for r in rows]


def custom_provider_ids() -> tuple[str, ...]:
    """Provider ids registered purely via `llm keys add <id> --base-url ...` —
    not one of the 13 built-ins llm_completions.py already knows how to resolve."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT provider FROM credentials WHERE base_url IS NOT NULL"
        ).fetchall()
    return tuple(r[0] for r in rows if r[0] not in _BUILTIN_PROVIDERS)


def all_provider_ids() -> tuple[str, ...]:
    return (*_BUILTIN_PROVIDERS, *custom_provider_ids())


def is_builtin_provider(provider: str) -> bool:
    return provider in _BUILTIN_PROVIDERS


def key_source(provider: str) -> Literal["stored", "env", "none"]:
    if _get_credential(provider) is not None:
        return "stored"
    if provider in _BUILTIN_PROVIDERS:
        try:
            resolve_text_llm_runtime(provider=provider)
            return "env"
        except RuntimeError:
            return "none"
    return "none"


def resolve_runtime_for_rotator(provider: str, model: str | None = None) -> TextLlmRuntime | None:
    """The rotator's own resolver — distinct from llm_completions.resolve_text_llm_runtime,
    which only knows the 13 built-ins and only reads env vars. This one also checks
    stored credentials (which win over env inside the rotator, since adding one via
    `llm keys add` is a more recent, explicit operator action) and constructs a
    TextLlmRuntime directly for custom/registered providers that resolve_text_llm_runtime
    has never heard of."""
    cred = _get_credential(provider)
    if cred:
        if cred.get("base_url"):
            return TextLlmRuntime(
                provider=provider, api_key=cred["api_key"], model=model or "", base_url=cred["base_url"]
            )
        try:
            return resolve_text_llm_runtime(provider=provider, model=model, api_key=cred["api_key"])
        except RuntimeError:
            return None
    if provider in _BUILTIN_PROVIDERS:
        try:
            return resolve_text_llm_runtime(provider=provider, model=model)
        except RuntimeError:
            return None
    return None


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


def _quota_reset_window(exc: BaseException) -> timedelta:
    msg = str(exc).lower()
    if any(hint in msg for hint in _RATE_LIMIT_HINTS) and not any(hint in msg for hint in _CREDIT_HINTS):
        return timedelta(minutes=5)
    if any(hint in msg for hint in _CREDIT_HINTS):
        return timedelta(hours=24)
    return timedelta(hours=1)  # bare 429, no body detail to go on


def record_failure(provider: str, model: str | None, exc: BaseException) -> FailureKind:
    kind = classify_failure(exc)
    now = _now_iso()
    with closing(_connect()) as conn:
        if kind == "quota":
            reset = _now() + _quota_reset_window(exc)
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
    rt = resolve_runtime_for_rotator(provider)
    if rt is None:
        with closing(_connect()) as conn:
            _upsert_provider_state(conn, provider, configured=0, last_refreshed_at=now)
            conn.commit()
        return {"provider": provider, "configured": False, "ok": False, "error": "not configured (no env or stored key)"}

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
    out = [refresh_provider_models(pid, timeout=timeout) for pid in all_provider_ids()]
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


def clear_exhaustion(provider: str) -> None:
    with closing(_connect()) as conn:
        _upsert_provider_state(conn, provider, exhausted_until=None, exhausted_reason=None)
        conn.commit()


def provider_status(provider: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM provider_state WHERE provider = ?", (provider,)).fetchone()
        model_count = conn.execute(
            "SELECT COUNT(*) FROM models WHERE provider = ? AND stale = 0", (provider,)
        ).fetchone()[0]
    d = dict(row) if row else {"provider": provider}
    d["exhausted"] = is_exhausted(provider)
    d["model_count"] = model_count
    d["key_source"] = key_source(provider)
    return d


def all_provider_status() -> list[dict[str, Any]]:
    return [provider_status(pid) for pid in all_provider_ids()]


def rank_providers_for_cycle(*, exclude: str | None = None) -> list[dict[str, Any]]:
    """Primary signal: skip exhausted providers and anything not resolvable right
    now (checked live via resolve_runtime_for_rotator — covers env vars, stored
    keys, and custom providers — not the possibly-stale `configured` column, so
    a provider whose key was added/removed since the last `llm refresh` is still
    handled correctly). Secondary: providers with a known positive
    usage_remaining (currently only OpenRouter exposes one — CometAPI's quota
    fetcher lives outside this fallback chain) sort first by remaining amount;
    a provider reporting <= 0 remaining is treated as exhausted, not ranked
    last. Everyone else keeps DEFAULT_CHAIN+custom-registration order as an
    'unknown, not yet observed exhausted' tier — this is the primary lane in
    practice, not the numeric one, and is a plain tiebreak, not a preference
    (DEFAULT_CHAIN's uncensored-first comment is about the secretary bot's own
    production chain, not this rotator — see pick_best_model_for_provider for
    where an uncensored preference is actually opt-in here)."""
    with closing(_connect()) as conn:
        rows = {r["provider"]: dict(r) for r in conn.execute("SELECT * FROM provider_state")}
    numeric: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for order, pid in enumerate(all_provider_ids()):
        if pid == exclude:
            continue
        if is_exhausted(pid):
            continue
        if resolve_runtime_for_rotator(pid) is None:
            continue
        usage_remaining = rows.get(pid, {}).get("usage_remaining")
        if usage_remaining is not None and usage_remaining <= 0:
            continue
        entry = {"provider": pid, "usage_remaining": usage_remaining, "order": order}
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


def _extract_context_length(raw: dict[str, Any]) -> int | None:
    """Best-effort — /v1/models shapes vary a lot per provider (confirmed via a
    real refresh: OpenRouter/Groq put it at top level under two different key
    names, DeepInfra nests it under metadata and is often null, NVIDIA/Cerebras
    don't expose it at all)."""
    for key in ("context_length", "context_window", "max_output_length"):
        val = raw.get(key)
        if isinstance(val, int) and val > 0:
            return val
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        val = meta.get("context_length")
        if isinstance(val, int) and val > 0:
            return val
    return None


def _extract_modality(raw: dict[str, Any]) -> str:
    """Best-effort task/modality guess. Defaults to 'text' — every provider this
    project talks to today (Groq/Mistral/NVIDIA/Cerebras/etc.) is a pure
    chat/text-completion host with no modality field in /v1/models at all, so
    'unknown' would be misleading; 'text' is the honest default for them."""
    arch = raw.get("architecture")
    if isinstance(arch, dict):
        inputs = arch.get("input_modalities") or []
        outputs = arch.get("output_modalities") or []
        if inputs or outputs:
            return f"{'+'.join(inputs) or '?'}->{'+'.join(outputs) or '?'}"
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        tags = meta.get("tags")
        if isinstance(tags, list) and tags:
            return str(tags[0])
    return "text"


def _extract_pricing(raw: dict[str, Any]) -> tuple[float, float] | None:
    """($ per million input tokens, $ per million output tokens), only when the
    provider uses the standard per-token `prompt`/`completion` pricing keys
    (OpenRouter, some Groq models). Deliberately does NOT interpret DeepInfra's
    metadata.pricing — its shape varies by model type (e.g. input_characters
    for TTS is a different unit entirely) and treating it as token pricing
    would be a wrong number, not just a missing one."""
    price = raw.get("pricing")
    if not isinstance(price, dict):
        return None
    try:
        prompt = float(price.get("prompt"))
        completion = float(price.get("completion"))
    except (TypeError, ValueError):
        return None
    return prompt * 1_000_000, completion * 1_000_000


def _extract_is_free(model_id: str, pricing: tuple[float, float] | None) -> bool:
    if is_openrouter_free_model(model_id):
        return True
    if pricing is not None and pricing[0] <= 0 and pricing[1] <= 0:
        return True
    return False


def _looks_uncensored(model_id: str) -> bool:
    mid = model_id.lower()
    return any(hint in mid for hint in _UNCENSORED_HINTS)


def list_models(provider: str | None = None) -> list[dict[str, Any]]:
    """Master model list joined with provider exhaustion/usage state, for the TUI
    and `llm models`. One row per (provider, model_id)."""
    with closing(_connect()) as conn:
        if provider:
            rows = conn.execute(
                "SELECT * FROM models WHERE provider = ? ORDER BY model_id", (provider,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM models ORDER BY provider, model_id").fetchall()
        state_rows = {r["provider"]: dict(r) for r in conn.execute("SELECT * FROM provider_state")}

    out: list[dict[str, Any]] = []
    for row in rows:
        raw = json.loads(row["raw_json"] or "{}")
        st = state_rows.get(row["provider"], {})
        pricing = _extract_pricing(raw)
        out.append(
            {
                "provider": row["provider"],
                "model_id": row["model_id"],
                "owned_by": raw.get("owned_by") or raw.get("root"),
                "context_length": _extract_context_length(raw),
                "modality": _extract_modality(raw),
                "price_in_per_m": pricing[0] if pricing else None,
                "price_out_per_m": pricing[1] if pricing else None,
                "is_free": _extract_is_free(row["model_id"], pricing),
                "stale": bool(row["stale"]),
                "fetched_at": row["fetched_at"],
                "exhausted": is_exhausted(row["provider"]),
                "usage_remaining": st.get("usage_remaining"),
                "usage_limit": st.get("usage_limit"),
            }
        )
    return out


def pick_best_model_for_provider(
    provider: str, *, task: str = "text", prefer_uncensored: bool = False
) -> str | None:
    """Which specific model to call for `provider`, given its catalog (if
    refreshed). Default preference is free-first then cheapest-per-million —
    NOT censorship: this project's own fallback chain (DEFAULT_CHAIN) is
    already uncensored-first for the secretary bot's NSFW tolerance, but that's
    a production-bot decision, not a general devops default. Returns None
    (caller keeps the provider's ordinary configured default) when the catalog
    has nothing usable — most providers (Groq/Mistral/NVIDIA/Cerebras) expose
    no pricing at all, so this quietly no-ops for them rather than guessing."""
    rows = [r for r in list_models(provider) if not r["stale"]]
    if not rows:
        return None
    task_matches = [r for r in rows if r["modality"] == task]
    candidates = task_matches or rows
    if prefer_uncensored:
        uncensored = [r for r in candidates if _looks_uncensored(r["model_id"])]
        if uncensored:
            candidates = uncensored
    priced = [r for r in candidates if r["is_free"] or r["price_in_per_m"] is not None]
    if not priced:
        return None

    def _sort_key(r: dict[str, Any]) -> tuple[int, float]:
        if r["is_free"]:
            return (0, 0.0)
        return (1, r["price_in_per_m"] or float("inf"))

    priced.sort(key=_sort_key)
    return priced[0]["model_id"]
