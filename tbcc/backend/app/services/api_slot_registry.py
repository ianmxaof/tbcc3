"""PC-local registry of arbitrary REST API "slots" (API Pocket, Phase 0).

Operator loads a key (+ optional base URL) via clipboard or CLI; suggest_slot()
classifies it, add_slot() persists it to tbcc/.tbcc-run/api_slot_registry.sqlite3
(gitignored, same posture as llm_model_index.py), and call_slot() forwards a
generic HTTP request using stored auth — no per-vendor SDK codegen needed to
make a freshly-loaded key immediately callable.

Reuses tbcc_env_secret_store.suggest_env_key/normalize_env_key so the same
key gets the same env var name whether it lands here or in the plain .env
capture path.

PC-local only, like llm_model_index.py: this file lives outside the island's
runtime and is never reachable in production. call_slot() resolves auth from
the process environment (tbcc/.env, loaded by load_tbcc_dotenv() at CLI/API
startup) — this module never writes .env itself; callers that also want a
plain env-file copy go through tbcc_env_secret_store.write_env_secret()
explicitly.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from app.services.tbcc_env_secret_store import normalize_env_key, suggest_env_key

AuthStyle = Literal["bearer", "x-api-key", "query", "none"]
Category = Literal["llm", "text-format", "media", "generic-rest"]

_VALID_AUTH_STYLES = ("bearer", "x-api-key", "query", "none")

_LLM_ENV_HINTS = (
    "OPENROUTER", "GEMINI", "CEREBRAS", "NVIDIA", "MISTRAL", "GROQ",
    "OPENAI", "ANTHROPIC", "DEEPINFRA", "FEATHERLESS", "VENICE", "HUGGINGFACE",
)
_LLM_URL_HINTS = (
    "openrouter.ai", "openai.com", "anthropic.com", "cerebras.ai", "groq.com",
    "mistral.ai", "deepinfra.com", "huggingface.co",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    override = (os.getenv("TBCC_API_SLOT_DB") or "").strip()
    if override:
        return Path(override)
    # this file: tbcc/backend/app/services/api_slot_registry.py -> tbcc/.tbcc-run/
    tbcc_root = Path(__file__).resolve().parents[3]
    return tbcc_root / ".tbcc-run" / "api_slot_registry.sqlite3"


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
        CREATE TABLE IF NOT EXISTS slots (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            base_url TEXT,
            auth_env_key TEXT NOT NULL,
            auth_style TEXT NOT NULL DEFAULT 'bearer',
            openapi_url TEXT,
            method TEXT NOT NULL DEFAULT 'GET',
            path_template TEXT NOT NULL DEFAULT '',
            headers_json TEXT,
            added_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "slot"


def _slot_id_from_hint(base_url: str, auth_env_key: str) -> str:
    if base_url:
        host = urlparse(base_url).netloc or base_url
        host = re.sub(r"^www\.", "", host)
        first = host.split(".")[0] if host else ""
        if first:
            return _slugify(first)
    return _slugify(re.sub(r"_API(_KEY)?$", "", auth_env_key or ""))


def _unique_id(conn: sqlite3.Connection, base_id: str) -> str:
    candidate = base_id
    n = 2
    while conn.execute("SELECT 1 FROM slots WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base_id}-{n}"
        n += 1
    return candidate


def classify_category(*, auth_env_key: str = "", base_url: str = "") -> Category:
    key_u = (auth_env_key or "").upper()
    url_l = (base_url or "").lower()
    if any(h in key_u for h in _LLM_ENV_HINTS) or any(h in url_l for h in _LLM_URL_HINTS):
        return "llm"
    return "generic-rest"


def parse_slot_source(text: str) -> dict[str, str]:
    """Best-effort parse of pasted API onboarding material: a curl one-liner
    (-H 'Authorization: Bearer KEY' / '-H X-Api-Key: KEY' + a URL), multiline
    "{url}\\n{key}", or a bare key. Returns only the keys it actually found —
    callers fill gaps with suggest_env_key/classify_category."""
    raw = (text or "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out

    curl_url = re.search(r"curl\s+.*?['\"]?(https?://[^\s'\"]+)", raw, re.I | re.S)
    curl_key = re.search(
        r"-H\s+['\"]?(?:Authorization:\s*Bearer\s+([^\s'\"]+)|X-Api-Key:\s*([^\s'\"]+))",
        raw,
        re.I,
    )
    if curl_key:
        out["key"] = curl_key.group(1) or curl_key.group(2)
        if curl_url:
            out["url"] = curl_url.group(1)
        return out

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    urls = [ln for ln in lines if re.match(r"^https?://", ln, re.I)]
    non_urls = [ln for ln in lines if ln not in urls]
    if urls:
        out["url"] = urls[0]
    if non_urls:
        out["key"] = non_urls[0]
    elif lines:
        out["key"] = lines[0]
    return out


def _fallback_env_key(url: str) -> str:
    host = urlparse(url).netloc if url else ""
    host = re.sub(r"^www\.", "", host).split(".")[0] if host else ""
    label = host or "GENERIC"
    return normalize_env_key(f"TBCC_{label}_API_KEY")


def suggest_slot(text: str, *, page_url: str = "", id_override: str = "") -> dict[str, Any]:
    """Classify pasted text into a slot suggestion without persisting it."""
    parsed = parse_slot_source(text)
    key = parsed.get("key") or (text or "").strip()
    url = parsed.get("url") or ""
    auth_env_key = suggest_env_key(value=key, page_url=page_url or url) or _fallback_env_key(url)
    category = classify_category(auth_env_key=auth_env_key, base_url=url or page_url)
    slot_id = _slugify(id_override) if id_override else _slot_id_from_hint(url, auth_env_key)
    return {
        "id": slot_id,
        "category": category,
        "auth_env_key": auth_env_key,
        "base_url": url or None,
        "auth_style": "bearer",
    }


def _first_post_path(openapi_url: str, *, timeout: float = 10.0) -> tuple[str, str]:
    r = httpx.get(openapi_url, timeout=timeout)
    r.raise_for_status()
    spec = r.json()
    paths = spec.get("paths") or {}
    for path, ops in paths.items():
        if isinstance(ops, dict) and "post" in ops:
            return path, "POST"
    for path, ops in paths.items():
        if isinstance(ops, dict) and "get" in ops:
            return path, "GET"
    raise ValueError("no usable path in OpenAPI spec")


def add_slot(
    *,
    auth_env_key: str,
    slot_id: str = "",
    category: str = "generic-rest",
    base_url: str = "",
    auth_style: AuthStyle = "bearer",
    openapi_url: str = "",
    method: str = "GET",
    path_template: str = "",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    if auth_style not in _VALID_AUTH_STYLES:
        raise ValueError(f"auth_style must be one of {_VALID_AUTH_STYLES}")
    env_key = normalize_env_key(auth_env_key)
    if not env_key:
        raise ValueError("auth_env_key required")

    base_url_n = (base_url or "").rstrip("/")
    method_final = (method or "GET").upper()
    path_final = path_template or ""
    warning = None
    if openapi_url and not path_final:
        try:
            path_final, method_final = _first_post_path(openapi_url)
        except Exception as e:  # noqa: BLE001 — OpenAPI hint is optional, register anyway
            warning = f"openapi fetch failed: {e}"[:300]

    with closing(_connect()) as conn:
        base_id = _slugify(slot_id) if slot_id else _slot_id_from_hint(base_url_n, env_key)
        final_id = _unique_id(conn, base_id)
        conn.execute(
            "INSERT INTO slots (id, category, base_url, auth_env_key, auth_style, openapi_url, "
            "method, path_template, headers_json, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                final_id,
                category,
                base_url_n or None,
                env_key,
                auth_style,
                openapi_url or None,
                method_final,
                path_final,
                json.dumps(headers or {}),
                _now_iso(),
            ),
        )
        conn.commit()

    result = get_slot(final_id)
    assert result is not None
    if warning:
        result["warning"] = warning
    return result


def get_slot(slot_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    return dict(row) if row else None


def list_slots() -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM slots ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def remove_slot(slot_id: str) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()
        return cur.rowcount > 0


def call_slot(
    slot_id: str,
    *,
    body: Any = None,
    method: str | None = None,
    path: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    slot = get_slot(slot_id)
    if slot is None:
        return {"ok": False, "error": f"slot {slot_id!r} not found"}
    base_url = slot.get("base_url") or ""
    if not base_url:
        return {"ok": False, "error": f"slot {slot_id!r} has no base_url"}

    auth_env_key = slot["auth_env_key"]
    auth_style = slot.get("auth_style") or "bearer"
    api_key = os.getenv(auth_env_key, "")
    if auth_style != "none" and not api_key:
        return {"ok": False, "error": f"env var {auth_env_key} is not set"}

    method_final = (method or slot.get("method") or "GET").upper()
    path_final = path if path is not None else (slot.get("path_template") or "")
    url = base_url.rstrip("/") + path_final

    headers: dict[str, str] = json.loads(slot.get("headers_json") or "{}")
    params: dict[str, str] = {}
    if auth_style == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_style == "x-api-key":
        headers["X-Api-Key"] = api_key
    elif auth_style == "query":
        params["api_key"] = api_key

    try:
        r = httpx.request(
            method_final,
            url,
            headers=headers,
            params=params or None,
            json=body if body is not None else None,
            timeout=timeout,
        )
        try:
            payload = r.json()
        except ValueError:
            payload = r.text
        return {"ok": r.status_code < 400, "status": r.status_code, "body": payload}
    except httpx.HTTPError as e:
        return {"ok": False, "error": str(e)[:300]}
